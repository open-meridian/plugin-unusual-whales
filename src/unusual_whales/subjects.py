"""What a want's subjects are, and which days are trading days: read from the
deployment, never assumed.

**A subject is the deployment's own record** (W3.6): the lake names an
`INS-` record, and the plugin asks the instrument store what it is and takes
the listing's ticker from its `symbol` identifiers -- its own, under the
source `unusual_whales`, else another source's, reporting its own beside it
(W3.1), so the record gains Unusual Whales' code; a report that meets
another record, or none, is a miss (W3.2), which a person settles. A record
with no symbol, in another currency than the dollar, or an index (whose
options are European and cash-settled, terms Unusual Whales' chain does not
state) is declined, not covered.

**A trading date is the platform's US equity calendar's** (W3.19, the
calendar the datasets declare): open interest read on a day is the clearing
house's count at the end of the market day before it, and a session's
volume is that day's. Read once for a span around today; a calendar that
does not answer leaves the dates not known, so no statistic is recorded
rather than one dated by guess.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from meridian.errors import MeridianError, NotGranted
from meridian.plugin.v1 import operations_pb2 as ops

from .convert import SOURCE, new_york_date

log = logging.getLogger(__name__)

#: How far back a market day is looked for, and forward the span reads.
LOOK_BACK_DAYS = 14
LOOK_AHEAD_DAYS = 7
CURRENCY = "USD"


@dataclass
class Listing:
    """What a subject is to Unusual Whales: its ticker, and whether it is an
    index."""

    symbol: str
    index: bool = False


@dataclass
class Symbols:
    """Each subject's ticker, resolved from its record once."""

    plugin: Any
    clock_ns: Callable[[], int]
    held: dict[str, Listing] = field(default_factory=dict)
    reads_instruments: bool = True

    async def listing(self, subject: str) -> Listing | None:
        """The listing a subject is; None where the deployment holds no such
        record, it carries no symbol, or it is priced in another currency."""
        known = self.held.get(subject)
        if known is not None:
            return known
        if not self.reads_instruments:
            return None
        now = self.clock_ns()
        try:
            found = await self.plugin.resolve_instrument(instrument_id=subject, as_of_ns=now)
        except NotGranted:
            log.warning("this data plugin may not read an instrument's record")
            self.reads_instruments = False
            return None
        if not found.found:
            return None
        record = found.instrument
        if record.currency and record.currency != CURRENCY:
            return None
        symbols = [i for i in record.identifiers if i.scheme == "symbol" and i.value.strip()]
        own = next((i for i in symbols if i.source == SOURCE), None)
        if own is not None:
            symbol = own.value.strip().upper()
        elif symbols:
            other = symbols[0]
            symbol = other.value.strip().upper()
            await self._join(subject, symbol, other)
        else:
            return None
        listing = Listing(symbol, record.instrument_type == ops.INSTRUMENT_TYPE_INDEX)
        self.held[subject] = listing
        return listing

    async def _join(self, subject: str, symbol: str, other: ops.Identifier) -> None:
        """Report Unusual Whales' symbol beside the one another source gave
        the record (W3.1); a report meeting another record, or ambiguous, is
        a miss (W3.2). Said, never raised."""
        own = ops.Identifier(scheme="symbol", value=symbol, source=SOURCE)
        given = ops.Identifier(scheme=other.scheme, value=other.value, source=other.source)
        now = self.clock_ns()
        try:
            found = await self.plugin.resolve_identifier(
                identifiers=[own, given], as_of_ns=now, stated_currency=CURRENCY
            )
            if found.found and found.instrument_id == subject:
                return
            reason = ops.MISS_REASON_AMBIGUOUS if found.found else found.miss_reason
            await self.plugin.report_missing_instrument(
                source=SOURCE,
                identifiers=[own, given],
                as_of_ns=now,
                reason=reason or ops.MISS_REASON_AMBIGUOUS,
            )
        except (MeridianError, ValueError) as refused:
            log.warning("%s's symbol not reported beside its record: %s", symbol, refused)


@dataclass
class Calendar:
    """The platform's US equity calendar, as the deployment answers it."""

    plugin: Any
    calendar_id: str
    clock_ns: Callable[[], int]
    days: dict[dt.date, bool] = field(default_factory=dict)
    read_on: dt.date | None = None
    error: str = ""

    async def _read(self, today: dt.date) -> bool:
        span = (
            today - dt.timedelta(days=LOOK_BACK_DAYS + LOOK_AHEAD_DAYS),
            today + dt.timedelta(days=LOOK_AHEAD_DAYS),
        )
        try:
            answer = await self.plugin.read_calendar(
                calendar_id=self.calendar_id, from_date=span[0], to_date=span[1]
            )
        except (MeridianError, ValueError) as failed:
            self.error = f"the calendar was not read: {failed}"[:300]
            log.warning("%s", self.error)
            return False
        if not answer.found:
            self.error = f"the deployment holds no calendar {self.calendar_id}"
            log.warning("%s", self.error)
            return False
        weekends: set[int] = set()
        for weekend in answer.weekends:
            weekends.update(weekend.weekdays)
        closed = {c.date for c in answer.days if c.kind == ops.CALENDAR_DAY_KIND_CLOSED}
        opened = {c.date for c in answer.days if c.kind == ops.CALENDAR_DAY_KIND_OPEN}
        day = span[0]
        while day <= span[1]:
            text = day.isoformat()
            weekday = ops.WEEKDAY_MONDAY + day.weekday()
            self.days[day] = text in opened or (text not in closed and weekday not in weekends)
            day += dt.timedelta(days=1)
        self.read_on = today
        self.error = ""
        return True

    async def is_open(self, day: dt.date) -> bool | None:
        """Whether a day is a US equity market day; None where the calendar
        did not answer for it."""
        today = new_york_date(self.clock_ns())
        stale = day not in self.days or self.read_on != today
        if stale and not await self._read(today):
            return None
        return self.days.get(day)

    async def previous_open(self, day: dt.date) -> dt.date | None:
        """The market day before `day`; None where not known."""
        for back in range(1, LOOK_BACK_DAYS + 1):
            before = day - dt.timedelta(days=back)
            held = await self.is_open(before)
            if held is None:
                return None
            if held:
                return before
        return None
