"""The plugin's work on the sample data: a chain's series and statistics, the
option tape and the off-exchange prints recorded against the lake's wants,
under the underlying with each series' key, and kept current for a standing
want; and what is declined, with why."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops

from conftest import (
    NO_SYMBOL,
    OTHER,
    SPX,
    SPY,
    Clock,
    Sample,
    lake,
    sent,
    want,
    work,
)

TRADE = "meridian.v1.Trade"


def _declined(made: object) -> dict[str, int]:
    out: dict[str, int] = {}
    for params in made.on("DeclineWant"):  # type: ignore[attr-defined]
        for subject in params.subjects:
            out[subject.entity_id] = params.reason
    return out


async def test_a_chains_series_never_minted(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made)
    await done.on_want(want("w-1", [SPY]))
    series = sent(made, "RecordSeries", "series")
    # Seven standard series; the adjusted contract (root SPY1) is not recorded.
    assert len(series) == 7
    first = series[0]
    assert first.meta.subjects[0].entity_id == SPY
    assert [(k.scheme, k.value) for k in first.meta.series_key] == [
        ("occ_osi", "SPY   261120C00580000")
    ]
    assert first.template_id == "TPL-listed-option" and first.template_version == "1"
    fields = {f.path: f.value for f in first.fields}
    assert fields["put_or_call"] == "PUT_OR_CALL_CALL"
    assert fields["strike_price"] == "580 USD" and fields["expiration_date"] == "2026-11-20"
    assert fields["exercise_style"] == "EXERCISE_STYLE_AMERICAN"
    assert fields["deliverable[0].instrument_id"] == SPY
    assert fields["deliverable[0].quantity"] == "100"
    assert not made.on("ResolveIdentifier"), "a chain row is never resolved"
    assert first.meta.raw.key.startswith("responses/")


async def test_open_interest_dated_the_market_day_before(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made)
    await done.on_want(want("w-1", [SPY], data_type="meridian.v1.Statistic"))
    stats = sent(made, "RecordStatistics", "statistics")
    oi = [s for s in stats if s.kind == ops.STATISTIC_KIND_OPEN_INTEREST]
    volume = [s for s in stats if s.kind == ops.STATISTIC_KIND_VOLUME]
    assert len(oi) == 7 and len(volume) == 6  # one volume stated null: no row
    assert {s.meta.business_date for s in oi} == {"2026-10-28"}
    assert {s.meta.business_date for s in volume} == {"2026-10-29"}
    assert as_decimal(oi[0].value.value) == 18250 and oi[0].value.unit == ops.VALUE_UNIT_CONTRACTS
    assert oi[0].meta.row_key == "SPY   261120C00580000:2026-10-28:OI"
    calendar = made.on("ReadCalendar")
    assert calendar and calendar[0].calendar_id.startswith("CAL-")


async def test_before_the_session_opens_no_volume_is_dated_today(tmp_path: Path) -> None:
    made = lake()
    clock = Clock()
    clock.advance(-7 * 3600)  # 08:00 New York
    done = work(tmp_path, made, clock=clock)
    await done.on_want(want("w-1", [SPY]))
    kinds = {s.kind for s in sent(made, "RecordStatistics", "statistics")}
    assert kinds == {ops.STATISTIC_KIND_OPEN_INTEREST}


async def test_a_calendar_that_does_not_answer_dates_nothing(tmp_path: Path) -> None:
    made = lake(calendar_answers=False)
    done = work(tmp_path, made)
    await done.on_want(want("w-1", [SPY]))
    assert len(sent(made, "RecordSeries", "series")) == 7
    assert not made.on("RecordStatistics")
    assert done.calendar.error


async def test_an_unchanged_chain_is_not_sent_again(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made)
    await done.on_want(want("w-1", [SPY]))
    await done.on_want(want("w-2", [SPY]))
    assert len(sent(made, "RecordSeries", "series")) == 7
    assert len(sent(made, "RecordStatistics", "statistics")) == 13


async def test_what_is_declined_and_why(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made)
    await done.on_want(want("w-1", [SPX, NO_SYMBOL, "INS-UNKNOWN"]))
    await done.on_want(want("w-2", [SPY], data_type="meridian.v1.Quote"))
    declined = _declined(made)
    assert declined == {
        SPX: ops.UNANSWERED_REASON_NOT_COVERED,
        NO_SYMBOL: ops.UNANSWERED_REASON_NOT_COVERED,
        "INS-UNKNOWN": ops.UNANSWERED_REASON_NOT_COVERED,
        SPY: ops.UNANSWERED_REASON_NOT_COVERED,
    }
    assert not made.on("RecordSeries")


async def test_the_api_refusing_is_source_silent(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made, transport=Sample(401), mode="live")
    await done.on_want(want("w-1", [SPY]))
    assert _declined(made) == {SPY: ops.UNANSWERED_REASON_SOURCE_SILENT}


async def test_another_sources_symbol_is_reported_beside_it(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made)
    await done.on_want(want("w-1", [OTHER]))
    asked = made.on("ResolveIdentifier")
    assert asked and {(i.scheme, i.value, i.source) for i in asked[0].identifiers} == {
        ("symbol", "QQQ", "unusual_whales"),
        ("symbol", "QQQ", "a-custodian"),
    }
    # The sample holds no QQQ: declined, not covered.
    assert _declined(made) == {OTHER: ops.UNANSWERED_REASON_NOT_COVERED}


async def test_the_option_tape(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made)
    await done.on_want(want("w-1", [SPY], key="option_trades", data_type=TRADE))
    trades = made.rows("RecordTrades")
    assert len(trades) == 7
    first = trades[0]
    assert first.meta.subjects[0].entity_id == SPY
    assert first.meta.series_key[0].value == "SPY   261120C00580000"
    assert first.meta.row_key == "7d3c0e1a-0000-4000-8000-000000000001"
    assert as_decimal(first.price.amount) == Decimal("12.10") and first.price.currency_code == "USD"
    assert as_decimal(first.quantity) == 5
    # Unusual Whales' side is inferred: never the aggressor.
    assert all(t.aggressor == ops.AGGRESSOR_UNSPECIFIED for t in trades)
    quote = first.quote_at_trade
    assert as_decimal(quote.bid.amount) == Decimal("12.05") and as_decimal(quote.ask_quantity) == 95
    assert quote.source_time_ns and not quote.as_last_received
    assert first.attributes.consolidated.high_low == ops.ELIGIBLE_ELIGIBLE
    by_key = {t.meta.row_key[-1]: t for t in trades}
    assert list(by_key["2"].attributes.characteristics) == [
        ops.TRADE_CHARACTERISTIC_INTERMARKET_SWEEP
    ]
    assert list(by_key["3"].attributes.characteristics) == [ops.TRADE_CHARACTERISTIC_MULTI_LEG]
    assert by_key["4"].attributes.consolidated.close == ops.ELIGIBLE_NOT_ELIGIBLE
    assert [(u.scheme, u.code) for u in by_key["6"].meta.unconverted] == [
        ("unusual_whales:upstream_condition_detail", "zzzz")
    ]
    assert by_key["6"].attributes.consolidated.high_low == ops.ELIGIBLE_UNSPECIFIED
    assert by_key["7"].cancelled


async def test_a_standing_tape_records_each_print_once(tmp_path: Path) -> None:
    made = lake()
    clock = Clock()
    sample = Sample()
    done = work(tmp_path, made, transport=sample, clock=clock)
    later = sample.trades["SPY"][4:]
    sample.trades["SPY"] = sample.trades["SPY"][:4]
    await done.on_want(want("w-1", [SPY], key="option_trades", data_type=TRADE, standing=True))
    assert len(made.rows("RecordTrades")) == 4
    sample.trades["SPY"] += later
    clock.advance(10)
    assert await done.due() == 0  # not yet its cadence
    clock.advance(30)
    assert await done.due() == 1
    clock.advance(30)
    await done.due()
    rows = made.rows("RecordTrades")
    assert len(rows) == 7 and len({r.meta.row_key for r in rows}) == 7
    assert "newer_than=" in sample.requests[-1]
    assert made.on("RecordLiveness")


async def test_out_of_hours_a_standing_want_waits(tmp_path: Path) -> None:
    made = lake()
    clock = Clock()
    done = work(tmp_path, made, clock=clock)
    await done.on_want(want("w-1", [SPY], key="option_trades", data_type=TRADE, standing=True))
    clock.advance(6 * 3600)  # 21:00 New York
    assert await done.due() == 0


async def test_a_range_before_the_latest_day_is_beyond_history(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made)
    day_before = Clock().ns - 2 * 86_400 * 1_000_000_000
    await done.on_want(
        want(
            "w-1",
            [SPY],
            key="option_trades",
            data_type=TRADE,
            valid_from_ns=day_before - 3600 * 10**9,
            valid_until_ns=day_before,
        )
    )
    assert _declined(made) == {SPY: ops.UNANSWERED_REASON_BEYOND_HISTORY}


async def test_a_range_within_the_day(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made)
    start = 1_793_288_400_000_000_000  # 2026-10-29 15:40 UTC
    until = 1_793_295_600_000_000_000  # 2026-10-29 17:40 UTC
    await done.on_want(
        want(
            "w-1",
            [SPY],
            key="option_trades",
            data_type=TRADE,
            valid_from_ns=start,
            valid_until_ns=until,
        )
    )
    assert [t.meta.row_key[-1] for t in made.rows("RecordTrades")] == ["3"]


async def test_off_exchange_prints(tmp_path: Path) -> None:
    made = lake()
    done = work(tmp_path, made)
    await done.on_want(want("w-1", [SPY], key="off_exchange", data_type=TRADE))
    trades = made.rows("RecordTrades")
    assert len(trades) == 7
    assert all(not t.meta.series_key for t in trades)
    assert all(t.meta.source.dataset == "unusual-whales:off_exchange" for t in trades)
    odd = next(t for t in trades if as_decimal(t.quantity) == 37)
    assert list(odd.attributes.characteristics) == [ops.TRADE_CHARACTERISTIC_ODD_LOT]
    assert odd.attributes.consolidated.high_low == ops.ELIGIBLE_NOT_ELIGIBLE
    assert odd.attributes.consolidated.volume == ops.ELIGIBLE_ELIGIBLE
    first = trades[0]
    assert first.meta.row_key.startswith("SPY:")
    assert ("unusual_whales:market_center", "L") in [
        (u.scheme, u.code) for u in first.meta.unconverted
    ]
    kinds = {t.kind for t in first.meta.source_times}
    assert kinds == {ops.SOURCE_TIME_KIND_EVENT, ops.SOURCE_TIME_KIND_REPORTED}
    assert any(t.cancelled for t in trades)


async def test_a_withdrawn_want_is_no_longer_kept_current(tmp_path: Path) -> None:
    made = lake()
    clock = Clock()
    done = work(tmp_path, made, clock=clock)
    await done.on_want(want("w-1", [SPY], standing=True))
    calls = len(done.api.transport.requests)  # type: ignore[attr-defined]
    made.answer("WantWithdrawn", lambda _: ops.WantWithdrawnEvent(want_id="w-1"))
    await made.receive(want_withdrawn=done.on_withdrawn)
    clock.advance(600)
    await done.due()
    assert len(done.api.transport.requests) == calls  # type: ignore[attr-defined]
