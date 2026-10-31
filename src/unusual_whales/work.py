"""The data plugin's work (the role `data`): Unusual Whales' option chains,
option prints and off-exchange prints into the lake, converted at the edge,
through the SDK's `Wants` and its chain helpers (`meridian.roles.chains`).

**Wants** (W10.7), by dataset; each subject an `INS-` record whose ticker is
read from it (subjects.py), declined `not_covered` where it has none:

- `options`: the underlying's whole chain read (`/api/stock/{ticker}/
  option-contracts`, every page) and recorded against the want -- each
  series' terms as the listed-option template's fields, never minted and
  never resolved (rulings 559 to 561), its open interest dated the market
  day before today, its volume today's once the session has opened (both by
  the platform's US equity calendar); a standing want's chain read again
  every five minutes while the session is open. An index's chain is
  declined: its terms (European, cash-settled) are not stated.
- `option_trades` and `off_exchange`: the latest trading day's prints of
  the subject read once and recorded, within the range a want names; a
  range ending before that day is `beyond_history` (the REST tape serves the
  latest trading day alone; older days come as whole-day files, not read
  here). A standing want's prints read again every 30 seconds while the
  session is open (04:00 to 20:00 New York for off-exchange prints), each
  print recorded once, a cancelled one as the next version of its row.

**Each row once**: a series or a statistic is sent again only where it
changed; a print only where it is newer than the last read, or cancelled.

**The allowance** (0.1.1): standing wants' reads are paced so what is left
of the plan's allowance lasts until the API resets its count (api.Allowance):
each read's requests push the next standing read back by their share of the
time left; the reads due are taken oldest first. Wants asked now are never
paced; a tenth of the allowance is kept for them.

Each read that answered is its dataset's sign of life (`Wants.liveness`),
at most once a minute. **Its licences** (contract v20, W10.9): read on start
and each minute.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import meridian
from meridian.operations import (
    Eligibility,
    Money,
    ObservationMeta,
    QuoteAtTrade,
    SourceTime,
    SubjectRef,
    Trade,
    TradeAttributes,
)
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import chains as helpers
from meridian.roles.data import Wants, unconverted

from . import convert
from .api import PAGE, Api, ApiError
from .convert import NEW_YORK, NS, SOURCE, Conditions, Cursor, new_york_date
from .declared import (
    CHAIN_CADENCE_SECONDS,
    KEYS,
    OFF_EXCHANGE,
    OPTION_TRADES,
    OPTIONS,
    SERIES,
    STATISTIC,
    TAPE_CADENCE_SECONDS,
    TRADE,
    US_EQUITY_CALENDAR,
)
from .subjects import Calendar, Listing, Symbols

log = logging.getLogger(__name__)

#: The platform's listed-option template (ruling 617) and its version.
TEMPLATE_ID = "TPL-listed-option"
TEMPLATE_VERSION = "1"
CURRENCY = "USD"
AMERICAN = "EXERCISE_STYLE_AMERICAN"
PHYSICAL = "SETTLEMENT_METHOD_PHYSICAL"
#: What one standard contract delivers: 100 shares of its underlying.
STANDARD_SHARES = 100
#: When each tape is read for a standing want, New York: OPRA's session
#: (with its late prints), and the reporting facilities' day.
OPTIONS_HOURS = (dt.time(9, 30), dt.time(16, 15))
OFF_EXCHANGE_HOURS = (dt.time(4, 0), dt.time(20, 0))
#: A session's volume is today's once it has opened.
SESSION_OPENS = dt.time(9, 30)
#: The most calls one standing want's tape is read back in, a pass.
MOST_TAPE_CALLS = 10
#: A dataset's sign of life recorded at most this often, in seconds.
LIVENESS_EVERY_SECONDS = 60
#: How often the timetable looks for what is due, in seconds.
TICK_SECONDS = 5
#: How many rows' last sendings are remembered, to send only what changed.
REMEMBERED = 200_000
MS = 1_000_000

Plugin = Any  # meridian.Plugin, or the suite's Recorder: the SDK's typed operations


@dataclass
class Tapes:
    """How the standing wants' reading is going, for the Connection page."""

    passes: int = 0
    gaps: int = 0
    last_read_ns: int = 0
    error: str = ""


@dataclass
class Work:
    """The plugin's work against whatever operations it is given: the
    plugin's own when it runs, a recorder's in its tests."""

    plugin: Plugin
    api: Api
    clock_ns: Callable[[], int] = time.time_ns
    wants: Wants = field(init=False)
    symbols: Symbols = field(init=False)
    calendar: Calendar = field(init=False)
    tapes: Tapes = field(default_factory=Tapes)
    #: When each standing want's chain or tape was last read, by (key, subject).
    read_at: dict[tuple[str, str], int] = field(default_factory=dict)
    #: Where each tape's reading stands, by (key, ticker).
    cursors: dict[tuple[str, str], Cursor] = field(default_factory=dict)
    #: Each row's last sending, by (data type, dataset, row key).
    sent: OrderedDict[tuple[str, str, str], str] = field(default_factory=OrderedDict)
    alive_ns: dict[str, int] = field(default_factory=dict)
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    #: When the next standing read may be made, by the allowance's budget.
    paced_until_ns: int = 0

    def __post_init__(self) -> None:
        self.wants = Wants(self.plugin, KEYS, clock_ns=self.clock_ns)
        self.symbols = Symbols(self.plugin, self.clock_ns)
        self.calendar = Calendar(self.plugin, US_EQUITY_CALENDAR, self.clock_ns)

    @property
    def latency(self) -> Any:
        return self.wants.latency

    @latency.setter
    def latency(self, value: Any) -> None:
        self.wants.latency = value

    def use(self, api: Api) -> None:
        """Answer from another source -- the API, or sample data -- every
        tape read afresh."""
        self.api = api
        self.cursors.clear()
        self.read_at.clear()
        self.sent.clear()
        self.wake.set()

    async def read_licences(self) -> None:
        await self.wants.read_licences()

    def dataset(self, key: str) -> str:
        return self.wants.dataset(key)

    def now(self) -> int:
        return int(self.clock_ns())

    # ── Wants ───────────────────────────────────────────────────────────

    async def on_want(self, heard: meridian.Heard[ops.ObservationsWantedEvent]) -> None:
        await self.wants.hear(heard, self.answer)
        self.wake.set()

    async def on_withdrawn(self, heard: meridian.Heard[ops.WantWithdrawnEvent]) -> None:
        if self.wants.withdraw(heard.message.want_id) is not None:
            log.info("standing want %s withdrawn", heard.message.want_id)
        self.wake.set()

    async def answer(
        self,
        want: ops.ObservationsWantedEvent,
        key: str,
        subjects: list[str],
        kinds: tuple[int, ...],
    ) -> dict[str, str]:
        """One want answered: its rows recorded against it, and each subject
        declined, with why."""
        asks = {
            OPTIONS: ("", SERIES, STATISTIC),
            OPTION_TRADES: ("", TRADE),
            OFF_EXCHANGE: ("", TRADE),
        }
        if key not in asks or want.data_type not in asks[key]:
            return {s: "not_covered" for s in subjects}
        declined: dict[str, str] = {}
        listed: dict[str, Listing] = {}
        for subject in subjects:
            listing = await self.symbols.listing(subject)
            if listing is None or listing.index:
                declined[subject] = "not_covered"
            else:
                listed[subject] = listing
        if want.standing and listed:
            # Standing before the first read, so its rows are the standing
            # want's: judged at the edge, their feed delay recorded.
            self.wants.stand(want, list(listed), kinds)
        served: list[str] = []
        for subject, listing in listed.items():
            if key == OPTIONS:
                found = await self.read_chain(subject, listing, want.want_id)
            else:
                found = await self.read_range(key, subject, listing, want)
            if found:
                declined[subject] = found
            else:
                served.append(subject)
        if want.standing and listed:
            if served:
                self.wants.stand(want, served, kinds)
            else:
                self.wants.withdraw(want.want_id)
            for subject in served:
                self.read_at[(key, subject)] = self.now()
        return declined

    # ── Chains ──────────────────────────────────────────────────────────

    def _changed(self, data_type: str, dataset: str, row_key: str, said: str) -> bool:
        """Whether a row says something other than its last sending."""
        mark = (data_type, dataset, row_key)
        if self.sent.get(mark) == said:
            return False
        self.sent[mark] = said
        self.sent.move_to_end(mark)
        while len(self.sent) > REMEMBERED:
            self.sent.popitem(last=False)
        return True

    async def dates(self) -> dict[str, str]:
        """The trading date each statistic read now is for: open interest the
        market day before today, volume today's once its session has opened;
        a kind with no date known is not recorded."""
        moment = dt.datetime.fromtimestamp(self.now() / NS, NEW_YORK)
        today = moment.date()
        out: dict[str, str] = {}
        before = await self.calendar.previous_open(today)
        if before is not None:
            out["open_interest"] = before.isoformat()
        if moment.time() >= SESSION_OPENS and await self.calendar.is_open(today):
            out["volume"] = today.isoformat()
        return out

    async def read_chain(self, subject: str, listing: Listing, want_id: str) -> str:
        """An underlying's chain read and recorded; empty, or why it was
        declined."""
        try:
            pages = await asyncio.to_thread(self.api.contracts, listing.symbol)
        except ApiError as failed:
            log.warning("%s's chain was not read: %s", listing.symbol, failed)
            return "source_silent"
        if not any(rows for rows, _ in pages):
            return "not_covered"
        await self.alive(OPTIONS)
        dataset = self.dataset(OPTIONS)
        dates = await self.dates()
        now = self.now()
        root = listing.symbol.replace(".", "")
        series: list[Any] = []
        statistics: list[Any] = []
        counts = self.wants.sent_to(OPTIONS)
        for rows, raw_key in pages:
            raw = self.plugin.raw_record(raw_key[:256])
            for contract in convert.contracts(rows):
                counts.unread += len(contract.unconverted)
                if contract.osi[:6].rstrip() != root:
                    # An adjusted contract: its deliverable and multiplier are
                    # not stated in the chain, so it is not recorded.
                    counts.unread += 1
                    continue
                row = helpers.option_series(
                    subject,
                    contract.osi,
                    template_id=TEMPLATE_ID,
                    template_version=TEMPLATE_VERSION,
                    dataset=dataset,
                    currency=CURRENCY,
                    exercise_style=AMERICAN,
                    settlement_method=PHYSICAL,
                    contract_multiplier=STANDARD_SHARES,
                    deliverable=[(subject, STANDARD_SHARES)],
                    valid_from_ns=now,
                    raw=raw,
                )
                terms = repr([(f.path, f.value) for f in row.fields])
                if self._changed(SERIES, dataset, f"{contract.osi}@{subject}", terms):
                    series.append(row)
                key = helpers.osi_key(contract.osi)
                for kind, value in (
                    ("open_interest", contract.open_interest),
                    ("volume", contract.volume),
                ):
                    day = dates.get(kind)
                    if value is None or not day:
                        continue
                    stat = helpers.statistic(
                        subject, key, kind, value, day, dataset=dataset, valid_from_ns=now, raw=raw
                    )
                    assert stat.meta is not None
                    if self._changed(
                        STATISTIC, dataset, f"{stat.meta.row_key}@{subject}", str(value)
                    ):
                        statistics.append(stat)
        if series:
            await self.wants.record("series", series, OPTIONS, want_id)
        if statistics:
            await self.wants.record("statistics", statistics, OPTIONS, want_id)
        return ""

    # ── Tapes ───────────────────────────────────────────────────────────

    async def latest_day(self) -> dt.date | None:
        """The latest trading day the REST tape serves: today once a market
        day's first prints can be reported (04:00 New York), else the market
        day before; None where the calendar does not say."""
        moment = dt.datetime.fromtimestamp(self.now() / NS, NEW_YORK)
        if moment.time() >= OFF_EXCHANGE_HOURS[0] and await self.calendar.is_open(moment.date()):
            return moment.date()
        return await self.calendar.previous_open(moment.date())

    async def read_range(
        self, key: str, subject: str, listing: Listing, want: ops.ObservationsWantedEvent
    ) -> str:
        """A want of prints over a range: the latest trading day's read and
        recorded within it; empty, or why it was declined."""
        until = want.valid_until_ns
        if until:
            day = await self.latest_day()
            if day is not None and new_york_date(until) < day:
                return "beyond_history"
        try:
            sent = await self.read_tape(
                key, subject, listing.symbol, want.want_id, want.valid_from_ns, until
            )
        except ApiError as failed:
            log.warning("%s's prints were not read: %s", listing.symbol, failed)
            return "source_silent"
        return "" if sent or want.standing else "source_silent"

    def _fetch(self, key: str, symbol: str, cursor: Cursor) -> list[tuple[dict[str, Any], str]]:
        """Each print since the cursor (the day's newest call where it is
        empty), with its raw record's key: read back a call at a time."""
        out: list[tuple[dict[str, Any], str]] = []
        newer = max(cursor.newest_ns - MS, 0) if cursor.newest_ns else 0
        if key == OFF_EXCHANGE:
            for _ in range(MOST_TAPE_CALLS):
                rows, raw_key = self.api.off_exchange(symbol, newer)
                out += [(row, raw_key) for row in rows]
                times = [convert.moment_ns(r.get("executed_at")) or 0 for r in rows]
                if len(rows) < PAGE or not cursor.newest_ns or max(times, default=0) <= newer:
                    break
                newer = max(times) - MS
            else:
                self.tapes.gaps += 1
            return out
        older = 0
        for _ in range(MOST_TAPE_CALLS):
            rows, raw_key = self.api.option_trades(symbol, newer, older)
            out += [(row, raw_key) for row in rows]
            times = [convert.moment_ns(r.get("executed_at")) or 0 for r in rows]
            if len(rows) < PAGE or not cursor.newest_ns or not times:
                break
            older = min(times)
        else:
            self.tapes.gaps += 1
        return out

    async def read_tape(
        self,
        key: str,
        subject: str,
        symbol: str,
        want_id: str = "",
        from_ns: int = 0,
        until_ns: int = 0,
    ) -> int:
        """A tape's prints since the last read, recorded once each (within a
        range where one is asked); how many were sent."""
        cursor = self.cursors.setdefault((key, symbol), Cursor())
        fetched = await asyncio.to_thread(self._fetch, key, symbol, cursor)
        await self.alive(key)
        rows: list[Trade] = []
        heard: list[tuple[str, int]] = []
        counts = self.wants.sent_to(key)
        for row, raw_key in sorted(
            fetched, key=lambda r: convert.moment_ns(r[0].get("executed_at")) or 0
        ):
            trade = self.trade(key, subject, row, raw_key)
            if trade is None:
                counts.unread += 1
                continue
            made, trade_id, at_ns, cancelled, unread = trade
            counts.unread += unread
            if from_ns and at_ns < from_ns or until_ns and at_ns > until_ns:
                continue
            if not cancelled and not cursor.fresh(trade_id, at_ns):
                continue
            assert made.meta is not None
            if not self._changed(TRADE, self.dataset(key), made.meta.row_key, repr(cancelled)):
                continue
            rows.append(made)
            heard.append((trade_id, at_ns))
        for trade_id, at_ns in heard:
            cursor.heard(trade_id, at_ns)
        if rows:
            await self.wants.record("trades", rows, key, want_id)
        self.tapes.last_read_ns = self.now()
        return len(rows)

    def trade(
        self, key: str, subject: str, row: dict[str, Any], raw_key: str
    ) -> tuple[Trade, str, int, bool, int] | None:
        """One print as a trade under its subject: the trade, its ID, its
        time, whether cancelled, and how many values did not read; None
        where the print does not read."""
        raw = self.plugin.raw_record(raw_key[:256])
        dataset = self.dataset(key)
        if key == OFF_EXCHANGE:
            off = convert.off_exchange_trade(row)
            if off is None:
                return None
            times = [SourceTime(kind="SOURCE_TIME_KIND_EVENT", at_ns=off.at_ns)]
            if off.reported_ns:
                times.append(SourceTime(kind="SOURCE_TIME_KIND_REPORTED", at_ns=off.reported_ns))
            said = _as_reported(off.conditions)
            if off.market_center:
                said.append(
                    ops.AsReported(
                        scheme=f"{SOURCE}:market_center",
                        code=off.market_center[:128],
                        text=off.market_center[:256],
                    )
                )
            meta = ObservationMeta(
                row_key=f"{off.symbol}:{off.tracking_id}"[:128],
                subjects=[SubjectRef(entity_id=subject)],
                source=ops.Source(dataset=dataset),
                valid_from_ns=off.at_ns,
                source_times=times,
                raw=raw,
                unconverted=said,
            )
            made = Trade(
                meta=meta,
                price=Money(off.price, CURRENCY),
                quantity=off.size,
                attributes=_attributes(off.conditions),
                cancelled=off.cancelled,
                quote_at_trade=_quote(off.bid, off.ask, off.bid_size, off.ask_size, 0),
            )
            return made, off.tracking_id, off.at_ns, off.cancelled, 0
        option = convert.option_trade(row)
        if option is None:
            return None
        meta = helpers.series_meta(
            subject,
            helpers.osi_key(option.osi),
            row_key=option.trade_id,
            dataset=dataset,
            valid_from_ns=option.at_ns,
            raw=raw,
            source_times=[SourceTime(kind="SOURCE_TIME_KIND_EVENT", at_ns=option.at_ns)],
            unconverted=[
                *_as_reported(option.conditions),
                *unconverted(SOURCE, option.unconverted),
            ],
        )
        made = Trade(
            meta=meta,
            price=Money(option.price, CURRENCY),
            quantity=option.size,
            attributes=_attributes(option.conditions),
            cancelled=option.cancelled,
            quote_at_trade=_quote(
                option.bid, option.ask, option.bid_size, option.ask_size, option.quote_at_ns
            ),
        )
        return made, option.trade_id, option.at_ns, option.cancelled, len(option.unconverted)

    # ── Signs of life ───────────────────────────────────────────────────

    async def alive(self, key: str) -> None:
        """A read that answered: the dataset's sign of life, at most once a
        minute (contract v27, W10.4). A refusal is said, never raised."""
        now = self.now()
        if now - self.alive_ns.get(key, 0) < LIVENESS_EVERY_SECONDS * NS:
            return
        self.alive_ns[key] = now
        try:
            await self.wants.liveness(key, now)
        except (meridian.MeridianError, ValueError) as refused:
            log.warning("%s's liveness not recorded: %s", key, refused)

    # ── Standing wants ──────────────────────────────────────────────────

    async def in_hours(self, key: str) -> bool:
        """Whether a standing want of `key` is read now: on a market day (by
        the calendar, or a weekday where it does not answer), in its hours."""
        moment = dt.datetime.fromtimestamp(self.now() / NS, NEW_YORK)
        opened = await self.calendar.is_open(moment.date())
        if opened is None:
            opened = moment.weekday() < 5
        start, end = OFF_EXCHANGE_HOURS if key == OFF_EXCHANGE else OPTIONS_HOURS
        return bool(opened) and start <= moment.time() <= end

    async def due(self) -> int:
        """Every standing want's chain or tape whose cadence has come, read
        and recorded, the longest unread first, while the allowance's budget
        allows; how many were read."""
        read = 0
        now = self.now()
        due: list[tuple[int, str, str]] = []
        for key in KEYS:
            standing = self.wants.standing_of(key)
            if not standing or not await self.in_hours(key):
                continue
            cadence = CHAIN_CADENCE_SECONDS if key == OPTIONS else TAPE_CADENCE_SECONDS
            for subject in sorted({s for w in standing for s in w.subjects}):
                last = self.read_at.get((key, subject), 0)
                if now - last >= cadence * NS:
                    due.append((last, key, subject))
        for _, key, subject in sorted(due):
            if self.now() < self.paced_until_ns:
                break
            self.read_at[(key, subject)] = now
            listing = await self.symbols.listing(subject)
            standing = self.wants.standing_of(key)
            if listing is None or not standing:
                continue
            want_id = next((w.want_id for w in standing if subject in w.subjects), "")
            calls = self.api.health.calls
            try:
                if key == OPTIONS:
                    await self.read_chain(subject, listing, want_id)
                else:
                    await self.read_tape(key, subject, listing.symbol, want_id)
                self.tapes.error = ""
            except (ApiError, meridian.MeridianError, ValueError) as failed:
                self.tapes.error = str(failed)[:300]
                log.warning("%s of %s not read: %s", key, listing.symbol, failed)
            self.spent(self.api.health.calls - calls)
            read += 1
        self.tapes.passes += 1
        return read

    def spent(self, calls: int) -> None:
        """A standing read's requests: the next standing read put back by
        their share of what the allowance has left until it resets."""
        now = self.now()
        gap = self.api.allowance.gap_ns(now)
        if gap and calls:
            self.paced_until_ns = max(self.paced_until_ns, now) + calls * gap

    async def keep_current(self) -> None:
        """The standing wants kept current, each at its dataset's cadence,
        until stopped."""
        while True:
            with contextlib.suppress(Exception):
                await self.due()
            self.wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.wake.wait(), TICK_SECONDS)


def _as_reported(said: Conditions) -> list[ops.AsReported]:
    return [
        ops.AsReported(scheme=f"{SOURCE}:{name}"[:64], code=code[:128], text=code[:256])
        for name, code in said.unconverted
    ]


def _attributes(said: Conditions) -> TradeAttributes:
    """A print's attributes: its characteristics, and what it may set in the
    consolidated view and its market centre's alike (OPRA and the tape
    plans state one rule for both); not known where a code did not convert."""
    if said.eligible is None:
        return TradeAttributes(
            consolidated=Eligibility(), market_centre=Eligibility(),
            characteristics=list(said.characteristics),
        )  # fmt: skip
    high_low, opened, close, volume = said.eligible
    eligible = Eligibility(high_low=high_low, open=opened, close=close, volume=volume)
    return TradeAttributes(
        consolidated=eligible, market_centre=eligible, characteristics=list(said.characteristics)
    )


def _quote(
    bid: Any, ask: Any, bid_size: int | None, ask_size: int | None, at_ns: int
) -> QuoteAtTrade | None:
    """The NBBO in force at a print, as the source states it with the print;
    none where it states neither side."""
    if bid is None and ask is None:
        return None
    return QuoteAtTrade(
        bid=None if bid is None else Money(bid, CURRENCY),
        ask=None if ask is None else Money(ask, CURRENCY),
        bid_quantity=bid_size if bid is not None else None,
        ask_quantity=ask_size if ask is not None else None,
        source_time_ns=at_ns,
    )
