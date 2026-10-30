"""Unusual Whales' answers, read into what the lake records: every number a
`Decimal` from the API's own text (it sends prices and greeks as strings),
never a float, and every code it states converted into the platform's words
or kept as reported.

**An option's symbol.** Unusual Whales writes the OCC's symbol with its root
unpadded (`AAPL240202P00185000`); the lake keys a series by the OCC's
21-character Options Symbology Initiative symbol, the root padded with
spaces to six (`AAPL  240202P00185000`, `occ_osi`, W1.26). `osi` pads it;
a symbol that does not read is no series.

**An option trade's conditions** (OPRA's, as Unusual Whales names them in
`upstream_condition_detail`, its `trade_code`, and its `report_flags`) are
converted to the platform's trade characteristics and eligibilities
(`TradeAttributes`): a sweep (`isoi`, `intermarket_sweep`), a leg of a
complex order (`ml*`, `cbmo`), a leg tied to a stock trade (`tl*`, `t*sl`),
a floor trade, a cross, an auction, a late or out-of-sequence report. A late
or out-of-sequence print may set the high, the low and the volume, never
the open or the close, as OPRA's last-sale rules have it; every other print
named here may set them all. A code with no conversion is kept as reported
(`unconverted`), and the print's eligibilities are then not known.

**Never a side.** Unusual Whales tags each print `ask_side`, `bid_side`,
`mid_side` or `no_side`: its own comparison of the price with the NBBO, an
inferred side. The lake's `aggressor` is the side the source says took
liquidity, never one inferred (the options sample's G12), so it is left
unstated; the tags stay in the raw record. The NBBO in force at the print,
which Unusual Whales states with each side's time, is the trade's quote at
the print (`quote_at_trade`, contract v28).

**An off-exchange print's conditions** (the equity trade-reporting
facilities' sale conditions, as Unusual Whales names them on its off-exchange
prints) are converted by the consolidated tape plans' eligibility rules: an
odd lot, an average-price, a contingent or a non-regular-settlement trade
never sets the high, the low, the open or the close; a derivatively priced
or prior-reference-price trade, or one out of sequence, sets the high and
the low but not the open or the close; an extended-hours trade sets none;
each counts toward the volume.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from meridian.roles.data import Unread

NEW_YORK = ZoneInfo("America/New_York")
NS = 1_000_000_000
#: The source name a value that did not read is kept under (`<source>:<field>`).
SOURCE = "unusual_whales"

_SYMBOL = re.compile(r"^(?P<root>[A-Z0-9.]{1,6})(?P<day>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")

E, N = "ELIGIBLE_ELIGIBLE", "ELIGIBLE_NOT_ELIGIBLE"
#: Every statistic a print may set: high and low, open, close, volume.
ALL = (E, E, E, E)
#: A print reported late or out of sequence: the high, the low and the volume.
LATE = (E, N, N, E)
#: A print that sets none but the volume.
VOLUME_ONLY = (N, N, N, E)


def osi(symbol: str) -> str | None:
    """The OCC's 21-character symbol of Unusual Whales' unpadded one, or None
    where it does not read as one."""
    found = _SYMBOL.match(symbol.strip().upper())
    if found is None:
        return None
    root = found.group("root").replace(".", "")
    return f"{root:<6}{found.group('day')}{found.group('right')}{found.group('strike')}"


def decimal(value: Any) -> Decimal | None:
    """A number as Unusual Whales sent it -- text, or an integer -- exactly;
    None where it sent none or it does not read."""
    if value is None or isinstance(value, (bool, float)):
        return None
    try:
        read = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return read if read.is_finite() else None


def count(value: Any) -> int | None:
    """A whole count as stated, or None."""
    read = decimal(value)
    if read is None or read != read.to_integral_value():
        return None
    return int(read)


def moment_ns(value: Any) -> int | None:
    """A time as Unusual Whales states it -- ISO 8601 in UTC on REST, Unix
    milliseconds on its WebSocket -- in nanoseconds; None where none."""
    if value is None or value == "":
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value * 1_000_000
    try:
        text = str(value).replace("Z", "+00:00")
        moment = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return int(moment.timestamp()) * NS + moment.microsecond * 1000


def new_york_date(at_ns: int) -> dt.date:
    return dt.datetime.fromtimestamp(at_ns / NS, NEW_YORK).date()


# ── Option contracts (a chain) ──────────────────────────────────────────


@dataclass(frozen=True)
class Contract:
    """One option contract as `/api/stock/{ticker}/option-contracts` states
    it: its OCC symbol, its open interest (the clearing house's count at the
    previous session's end), its volume so far in the session, and what did
    not read."""

    osi: str
    open_interest: int | None
    volume: int | None
    unconverted: tuple[Unread, ...] = ()


def contracts(rows: Iterable[Mapping[str, Any]]) -> list[Contract]:
    """Each contract of an answer's `data` that names a symbol that reads."""
    out: list[Contract] = []
    for row in rows:
        symbol = osi(str(row.get("option_symbol", "")))
        if symbol is None:
            continue
        unread: list[Unread] = []
        held: dict[str, int | None] = {}
        for name in ("open_interest", "volume"):
            value = row.get(name)
            held[name] = count(value)
            if value is not None and held[name] is None:
                unread.append(Unread(name, str(value)))
        out.append(Contract(symbol, held["open_interest"], held["volume"], tuple(unread)))
    return out


# ── Trade conditions ────────────────────────────────────────────────────

#: OPRA's trade conditions as Unusual Whales names them (its `trade_codes[]`
#: filter and each print's `upstream_condition_detail`): the platform's
#: characteristics, and what the print may set.
OPTION_CODES: Mapping[str, tuple[tuple[str, ...], tuple[str, str, str, str]]] = {
    "auto": ((), ALL),
    "isoi": (("INTERMARKET_SWEEP",), ALL),
    "late": (("LATE_REPORT",), LATE),
    "oseq": (("OUT_OF_SEQUENCE",), LATE),
    "opnl": (("LATE_REPORT", "OUT_OF_SEQUENCE"), LATE),
    "open": (("OPENING_AUCTION",), ALL),
    "reop": (("OTHER_AUCTION",), ALL),
    "mlet": (("MULTI_LEG",), ALL),
    "mlat": (("MULTI_LEG", "OTHER_AUCTION"), ALL),
    "mlct": (("MULTI_LEG", "CROSS"), ALL),
    "mlft": (("MULTI_LEG", "FLOOR"), ALL),
    "mesl": (("MULTI_LEG",), ALL),
    "masl": (("MULTI_LEG", "OTHER_AUCTION"), ALL),
    "mfsl": (("MULTI_LEG", "FLOOR"), ALL),
    "cbmo": (("MULTI_LEG", "FLOOR"), ALL),
    "tlet": (("STOCK_OPTION_TIED",), ALL),
    "tlat": (("STOCK_OPTION_TIED", "OTHER_AUCTION"), ALL),
    "tlct": (("STOCK_OPTION_TIED", "CROSS"), ALL),
    "tlft": (("STOCK_OPTION_TIED", "FLOOR"), ALL),
    "tesl": (("STOCK_OPTION_TIED",), ALL),
    "tasl": (("STOCK_OPTION_TIED", "OTHER_AUCTION"), ALL),
    "tfsl": (("STOCK_OPTION_TIED", "FLOOR"), ALL),
    "slai": (("OTHER_AUCTION", "INTERMARKET_SWEEP"), ALL),
    "slan": (("OTHER_AUCTION",), ALL),
    "slci": (("CROSS", "INTERMARKET_SWEEP"), ALL),
    "slcn": (("CROSS",), ALL),
    "slft": (("FLOOR",), ALL),
}
#: Unusual Whales' report flags on a print: the platform's characteristics,
#: and what the print may set. `normal` and `printable` say nothing more.
OPTION_FLAGS: Mapping[str, tuple[tuple[str, ...], tuple[str, str, str, str]]] = {
    "normal": ((), ALL),
    "printable": ((), ALL),
    "intermarket_sweep": (("INTERMARKET_SWEEP",), ALL),
    "cross_trade": (("CROSS",), ALL),
    "opening": (("OPENING_AUCTION",), ALL),
    "reopening": (("OTHER_AUCTION",), ALL),
    "closing": (("CLOSING_AUCTION",), ALL),
    "extended_hours": (("EXTENDED_HOURS",), VOLUME_ONLY),
    "odd_lot": (("ODD_LOT",), VOLUME_ONLY),
}
#: The equity trade-reporting facilities' conditions on an off-exchange print,
#: as Unusual Whales names them (`sale_cond_codes`, `trade_code`,
#: `ext_hour_sold_codes`, `trade_settlement`).
EQUITY_CODES: Mapping[str, tuple[tuple[str, ...], tuple[str, str, str, str]]] = {
    "contingent_trade": (("CONTINGENT",), VOLUME_ONLY),
    "qualified_contingent_trade": (("CONTINGENT",), VOLUME_ONLY),
    "odd_lot_execution": (("ODD_LOT",), VOLUME_ONLY),
    "average_price_trade": (("AVERAGE_PRICE",), VOLUME_ONLY),
    "prior_reference_price": (("PRIOR_REFERENCE_PRICE",), LATE),
    "derivative_priced": (("DERIVATIVELY_PRICED",), LATE),
    "intermarket_sweep": (("INTERMARKET_SWEEP",), ALL),
    "extended_hours_trade": (("EXTENDED_HOURS",), VOLUME_ONLY),
    "sold_out_of_sequence": (("OUT_OF_SEQUENCE",), LATE),
    "extended_hours_trade_late_or_out_of_sequence": (
        ("EXTENDED_HOURS", "OUT_OF_SEQUENCE"),
        VOLUME_ONLY,
    ),
    "regular": ((), ALL),
    "regular_settlement": ((), ALL),
    "cash": (("NON_REGULAR_SETTLEMENT",), VOLUME_ONLY),
    "cash_settlement": (("NON_REGULAR_SETTLEMENT",), VOLUME_ONLY),
    "next_day": (("NON_REGULAR_SETTLEMENT",), VOLUME_ONLY),
    "next_day_settlement": (("NON_REGULAR_SETTLEMENT",), VOLUME_ONLY),
    "seller": (("NON_REGULAR_SETTLEMENT",), VOLUME_ONLY),
    "seller_settlement": (("NON_REGULAR_SETTLEMENT",), VOLUME_ONLY),
}


@dataclass(frozen=True)
class Conditions:
    """A print's conditions converted: the platform's characteristics, what
    it may set (high and low, open, close, volume; all None where a code
    did not convert, so not known), and each code kept as reported."""

    characteristics: tuple[str, ...]
    eligible: tuple[str, str, str, str] | None
    unconverted: tuple[tuple[str, str], ...] = ()


def conditions(
    stated: Sequence[tuple[str, str]],
    table: Mapping[str, tuple[tuple[str, ...], tuple[str, str, str, str]]],
) -> Conditions:
    """Each `(field, code)` a print states, converted by `table`; the
    eligibilities the strictest of them, or not known where any code has no
    conversion."""
    characteristics: list[str] = []
    eligible = list(ALL)
    unconverted: list[tuple[str, str]] = []
    for name, code in stated:
        held = table.get(code.strip().lower())
        if held is None:
            unconverted.append((name, code))
            continue
        said, may = held
        for one in said:
            if one not in characteristics:
                characteristics.append(one)
        eligible = [
            N if N in (mine, theirs) else E for mine, theirs in zip(eligible, may, strict=True)
        ]
    return Conditions(
        tuple(f"TRADE_CHARACTERISTIC_{c}" for c in characteristics),
        None if unconverted else (eligible[0], eligible[1], eligible[2], eligible[3]),
        tuple(unconverted),
    )


# ── Option trades ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class OptionTrade:
    """One option print as `/api/option-trades` states it (and its WebSocket
    channel `option_trades`): Unusual Whales' ID for it, the contract, the
    underlying's symbol, when it executed, its price and size, the NBBO in
    force with each side's size and time, whether it was cancelled, its
    conditions, and what did not read."""

    trade_id: str
    osi: str
    underlying: str
    at_ns: int
    price: Decimal
    size: Decimal
    cancelled: bool
    conditions: Conditions
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: int | None = None
    ask_size: int | None = None
    quote_at_ns: int = 0
    unconverted: tuple[Unread, ...] = ()


def _codes(row: Mapping[str, Any], *names: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for name in names:
        value = row.get(name)
        if isinstance(value, str) and value:
            out.append((name, value))
        elif isinstance(value, list):
            out += [(name, str(v)) for v in value if isinstance(v, str) and v]
    return out


def option_trade(row: Mapping[str, Any]) -> OptionTrade | None:
    """A print as Unusual Whales states it; None where it names no ID, no
    contract that reads, no time, no price or no size above zero."""
    trade_id = str(row.get("id") or "")
    symbol = osi(str(row.get("option_symbol") or row.get("option_chain_id") or ""))
    at_ns = moment_ns(row.get("executed_at"))
    price = decimal(row.get("price"))
    size = decimal(row.get("size"))
    if not trade_id or symbol is None or at_ns is None or price is None or not size or size <= 0:
        return None
    unread = [
        Unread(name, str(row.get(name)))
        for name in ("nbbo_bid", "nbbo_ask")
        if row.get(name) not in (None, "") and decimal(row.get(name)) is None
    ]
    times = [
        t for t in (moment_ns(row.get("nbbo_bid_time")), moment_ns(row.get("nbbo_ask_time"))) if t
    ]
    bid, ask = decimal(row.get("nbbo_bid")), decimal(row.get("nbbo_ask"))
    return OptionTrade(
        trade_id=trade_id,
        osi=symbol,
        underlying=str(row.get("underlying_symbol") or "").upper(),
        at_ns=at_ns,
        price=price,
        size=size,
        cancelled=row.get("canceled") is True,
        conditions=conditions(
            _codes(row, "upstream_condition_detail", "trade_code", "report_flags"),
            {**OPTION_CODES, **OPTION_FLAGS},
        ),
        bid=bid if bid is not None and bid > 0 else None,
        ask=ask if ask is not None and ask > 0 else None,
        bid_size=count(row.get("nbbo_bid_size")),
        ask_size=count(row.get("nbbo_ask_size")),
        quote_at_ns=max(times, default=0),
        unconverted=tuple(unread),
    )


# ── Off-exchange prints ─────────────────────────────────────────────────


@dataclass(frozen=True)
class OffExchangeTrade:
    """One off-exchange equity print as `/api/darkpool/{ticker}` states it:
    its tracking ID, the symbol, when it executed (and when the reporting
    facility reported it), its price and size, the market centre's code,
    whether it was cancelled, its conditions, and the NBBO in force."""

    tracking_id: str
    symbol: str
    at_ns: int
    reported_ns: int
    price: Decimal
    size: Decimal
    market_center: str
    cancelled: bool
    conditions: Conditions
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_size: int | None = None
    ask_size: int | None = None


def off_exchange_trade(row: Mapping[str, Any]) -> OffExchangeTrade | None:
    """An off-exchange print as stated; None where it names no tracking ID,
    no symbol, no time, no price or no size above zero."""
    tracking = str(row.get("tracking_id") or "")
    symbol = str(row.get("ticker") or "").upper()
    at_ns = moment_ns(row.get("executed_at"))
    price = decimal(row.get("price"))
    size = decimal(row.get("size"))
    if not tracking or not symbol or at_ns is None or price is None or not size or size <= 0:
        return None
    bid, ask = decimal(row.get("nbbo_bid")), decimal(row.get("nbbo_ask"))
    return OffExchangeTrade(
        tracking_id=tracking,
        symbol=symbol,
        at_ns=at_ns,
        reported_ns=moment_ns(row.get("trf_executed_at")) or 0,
        price=price,
        size=size,
        market_center=str(row.get("market_center") or ""),
        cancelled=row.get("canceled") is True,
        conditions=conditions(
            _codes(row, "sale_cond_codes", "trade_code", "ext_hour_sold_codes", "trade_settlement"),
            EQUITY_CODES,
        ),
        bid=bid if bid is not None and bid > 0 else None,
        ask=ask if ask is not None and ask > 0 else None,
        bid_size=count(row.get("nbbo_bid_quantity")),
        ask_size=count(row.get("nbbo_ask_quantity")),
    )


@dataclass
class Cursor:
    """Where a tape's polling of one symbol stands: the newest print's time
    read, and the IDs read at that time (Unusual Whales' cursor is a time,
    so prints at the same time are told apart by ID)."""

    newest_ns: int = 0
    seen: set[str] = field(default_factory=set)

    def fresh(self, trade_id: str, at_ns: int) -> bool:
        """Whether a print is newer than the cursor, or at its time and unseen."""
        return not (at_ns < self.newest_ns or (at_ns == self.newest_ns and trade_id in self.seen))

    def heard(self, trade_id: str, at_ns: int) -> None:
        if at_ns > self.newest_ns:
            self.newest_ns = at_ns
            self.seen = {trade_id}
        elif at_ns == self.newest_ns:
            self.seen.add(trade_id)
