"""Reading Unusual Whales' answers: symbols padded to the OCC's 21
characters, numbers exact from their text, and each condition converted by
OPRA's and the tape plans' rules, or kept as reported."""

from __future__ import annotations

import json
from decimal import Decimal
from importlib import resources

from unusual_whales import convert
from unusual_whales.convert import ALL, LATE, VOLUME_ONLY, Cursor


def _sample(name: str) -> list[dict[str, object]]:
    text = (resources.files("unusual_whales") / "synthetic" / name).read_text("utf-8")
    rows: list[dict[str, object]] = json.loads(text)["SPY"]
    return rows


def test_a_symbol_is_padded_to_the_occs_21_characters() -> None:
    assert convert.osi("AAPL240202P00185000") == "AAPL  240202P00185000"
    assert convert.osi("SPXW261120C05800000") == "SPXW  261120C05800000"
    assert convert.osi("SPY1261120C00580000") == "SPY1  261120C00580000"
    assert convert.osi("BRK.B261120C00450000") == "BRKB  261120C00450000"
    assert len(convert.osi("F261120C00012000") or "") == 21
    assert convert.osi("not a symbol") is None
    assert convert.osi("TOOLONGX261120C00012000") is None


def test_numbers_are_read_exactly_never_through_a_float() -> None:
    assert convert.decimal("0.610546281537814") == Decimal("0.610546281537814")
    assert convert.decimal(132276) == Decimal(132276)
    assert convert.decimal(0.1) is None and convert.decimal(None) is None
    assert convert.decimal("NaN") is None and convert.decimal("abc") is None
    assert convert.count("40") == 40 and convert.count("4.5") is None


def test_times_on_rest_and_on_the_websocket() -> None:
    assert convert.moment_ns("2024-08-21T13:50:52.278Z") == 1_724_248_252_278_000_000
    assert convert.moment_ns(1_726_670_167_412) == 1_726_670_167_412_000_000
    assert convert.moment_ns(None) is None and convert.moment_ns("") is None


def test_a_chains_contracts() -> None:
    contracts = convert.contracts(_sample("option_contracts.json"))
    assert [c.osi for c in contracts][:2] == ["SPY   261120C00580000", "SPY   261120P00580000"]
    assert contracts[0].open_interest == 18250 and contracts[0].volume == 4210
    # Stated null: no value, never a zero.
    assert contracts[-1].volume is None and contracts[-1].open_interest == 4410


def test_a_regular_print_with_its_nbbo_and_no_side() -> None:
    first = convert.option_trade(_sample("option_trades.json")[0])
    assert first is not None
    assert first.osi == "SPY   261120C00580000" and first.underlying == "SPY"
    assert first.price == Decimal("12.10") and first.size == 5
    assert first.conditions.characteristics == () and first.conditions.eligible == ALL
    assert first.bid == Decimal("12.05") and first.ask == Decimal("12.12")
    assert first.bid_size == 120 and first.ask_size == 95
    # The quote's time: the later of its two sides'.
    assert first.quote_at_ns == convert.moment_ns("2026-10-29T14:01:02.050Z")
    assert not first.cancelled


def test_option_conditions_converted() -> None:
    rows = {r["upstream_condition_detail"]: r for r in _sample("option_trades.json")}
    sweep = convert.option_trade(rows["isoi"])
    assert sweep is not None
    assert sweep.conditions.characteristics == ("TRADE_CHARACTERISTIC_INTERMARKET_SWEEP",)
    leg = convert.option_trade(rows["mlet"])
    assert leg is not None and leg.conditions.characteristics == ("TRADE_CHARACTERISTIC_MULTI_LEG",)
    tied = convert.option_trade(rows["tlet"])
    assert tied is not None
    assert tied.conditions.characteristics == ("TRADE_CHARACTERISTIC_STOCK_OPTION_TIED",)
    late = convert.option_trade(rows["late"])
    assert late is not None
    assert late.conditions.characteristics == ("TRADE_CHARACTERISTIC_LATE_REPORT",)
    assert late.conditions.eligible == LATE


def test_a_condition_with_no_conversion_is_kept_as_reported() -> None:
    rows = {r["upstream_condition_detail"]: r for r in _sample("option_trades.json")}
    unknown = convert.option_trade(rows["zzzz"])
    assert unknown is not None
    assert unknown.conditions.eligible is None
    assert unknown.conditions.unconverted == (("upstream_condition_detail", "zzzz"),)


def test_a_cancelled_print() -> None:
    cancelled = [convert.option_trade(r) for r in _sample("option_trades.json") if r["canceled"]]
    assert len(cancelled) == 1 and cancelled[0] is not None and cancelled[0].cancelled


def test_a_print_that_does_not_read_is_none() -> None:
    row = dict(_sample("option_trades.json")[0])
    for name, value in (("id", ""), ("option_chain_id", "nope"), ("price", None), ("size", 0)):
        broken = {**row, name: value}
        assert convert.option_trade(broken) is None, name


def test_off_exchange_conditions_by_the_tape_plans() -> None:
    rows = [convert.off_exchange_trade(r) for r in _sample("off_exchange.json")]
    assert all(r is not None for r in rows)
    by_size = {r.size: r for r in rows if r is not None}
    odd = by_size[Decimal(37)]
    assert odd.conditions.characteristics == ("TRADE_CHARACTERISTIC_ODD_LOT",)
    assert odd.conditions.eligible == VOLUME_ONLY
    late_hours = by_size[Decimal(2000)]
    assert late_hours.conditions.characteristics == ("TRADE_CHARACTERISTIC_EXTENDED_HOURS",)
    cash = by_size[Decimal(800)]
    assert cash.conditions.characteristics == ("TRADE_CHARACTERISTIC_NON_REGULAR_SETTLEMENT",)
    regular = by_size[Decimal(5000)]
    assert regular.conditions.characteristics == () and regular.conditions.eligible == ALL
    assert regular.market_center == "L" and regular.reported_ns
    made_up = by_size[Decimal(1500)]
    assert made_up.conditions.eligible is None
    assert made_up.conditions.unconverted == (("sale_cond_codes", "made_up_code"),)


def test_a_cursor_tells_prints_at_one_time_apart_by_id() -> None:
    cursor = Cursor()
    assert cursor.fresh("a", 10)
    cursor.heard("a", 10)
    assert not cursor.fresh("a", 10) and cursor.fresh("b", 10)
    assert not cursor.fresh("c", 9) and cursor.fresh("c", 11)
