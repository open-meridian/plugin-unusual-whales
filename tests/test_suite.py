"""The data suite (meridian.suites) at contract v28, each case Unusual Whales
presents mapped to the plugin's own work on answers in the API's documented
shape -- SPY's made-up chain, option prints and off-exchange prints.

Presented: a chain's series and its open interest (`options`), the calendar
read to date them; a print recorded with no condition, a condition
converted (an off-exchange odd lot), a condition kept as reported, a print
withdrawn, and a standing want's prints read and recorded (`option_trades`);
a dataset's liveness on a read that brought nothing new; the feed delay; an
underlying whose symbol meets two records; and the wants, the licences, and
one bounded lake query, as the SDK's data template maps it.

Not presented, with why: every case about a price, which Unusual Whales'
plugin never records; the aggressor (Unusual Whales states an inferred
side, never the side that took liquidity); quotes and their quality (a
chain's NBBO carries no quote time); a restart's gap backfilled from the
lake (the REST tape is read afresh from the day's newest prints); a
settlement date; outcomes, rates and the filings slice, which Unusual
Whales' API serves only as its own figures or not at all.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data.testing import RATES_CASES, Instruments, feed_delay, lake_query
from meridian.suites import ANSWERED_BY_SDK, Recorder, run

from conftest import INSTANCE, OTHER, SPX, SPY, Sample, answering, held, want, work

TRADE = "meridian.v1.Trade"
_PRICES = (
    "a-daily-close", "the-forming-day-restated", "an-exact-price", "a-daily-bar", "an-fx-rate",
    "a-stablecoin-quote", "a-venue-resolved", "a-venue-not-held", "a-want-recorded-against",
    "a-subject-another-source-resolved",
)  # fmt: skip
_OUTCOMES = (
    "records-an-outcome", "restates-a-disputed-outcome", "records-a-partial-payout",
    "reports-an-event-group", "reports-a-flag-the-venue-does-not-state",
)  # fmt: skip
_FILINGS = (
    "a-filing-recorded", "a-fact-restated", "a-fact-confirmed", "resolves-a-filer",
    "a-complete-holdings-report", "a-cusip-used-as-key", "a-stake-crossed",
    "a-dividend-declared", "a-rating-action",
)  # fmt: skip
_NO_QUOTES = (
    "its option chains' NBBO carries no quote time (Unusual Whales' last_tape_time is the last "
    "trade's), so no quote row is made from it; the NBBO in force at each print travels on the "
    "print as its quote at trade"
)
NOT_PRESENTED = {
    **{case: "it records option chains and prints, never a price" for case in _PRICES},
    "the-takers-side-stated": (
        "Unusual Whales states an inferred side (its comparison of the price with the NBBO), "
        "never the side that took liquidity, and an inferred side is never the aggressor"
    ),
    "the-makers-side-inverted": (
        "Unusual Whales states no resting order's side; its inferred side is never the aggressor"
    ),
    "a-quote-recorded": _NO_QUOTES,
    "a-one-sided-quote": _NO_QUOTES,
    "a-chain-row-is-never-resolved": _NO_QUOTES,
    "a-crossed-quote-is-recorded-invalid": _NO_QUOTES,
    "a-duplicate-is-recorded-suspicious": _NO_QUOTES,
    "rows-after-a-gap-are-suspicious": _NO_QUOTES,
    "a-restarts-gap-backfilled": (
        "the REST tape serves the latest trading day, newest first, by time and not by "
        "sequence: a restart reads each tape afresh from the day's newest prints, a print "
        "recorded before answered unchanged by its row key, rather than from the lake's last"
    ),
    "asks-for-a-settlement-date": "it records prints and statistics as stated; never a settlement",
    **{case: "Unusual Whales' API states no event contract's outcome" for case in _OUTCOMES},
    **{
        case: "Unusual Whales publishes no rate fixing, curve or index level"
        for case in RATES_CASES
    },
    **{
        case: "it records no filings; Unusual Whales' filings are its own feed" for case in _FILINGS
    },
}
PRESENTED = {
    "a-subject-declined", "a-standing-want-withdrawn", "an-asset-that-does-not-resolve",
    "reads-its-datasets-licences", "reports-its-feed-delay", "records-a-datasets-liveness",
    "a-trade-recorded", "a-condition-converted", "a-condition-not-converted",
    "a-trade-withdrawn", "a-standing-want-streamed", "queries-the-lake-within-bounds",
    "records-a-chains-series", "records-open-interest", "reads-a-calendar",
}  # fmt: skip


def producers(tmp: Path) -> dict[str, Callable[[Recorder], Awaitable[None]]]:
    def wanted(
        message: Any, keep: Callable[[Sample], None] | None = None
    ) -> Callable[[Recorder], Awaitable[None]]:
        async def produce(recorder: Recorder) -> None:
            answering(recorder)
            sample = Sample()
            if keep is not None:
                keep(sample)
            done = work(tmp, recorder, sample)
            recorder.answer("ObservationsWanted", lambda _: message)
            await recorder.receive(observations_wanted=done.on_want)

        return produce

    def only(field: str, value: Any, tape: str = "trades") -> Callable[[Sample], None]:
        def keep(sample: Sample) -> None:
            held = getattr(sample, tape)
            held["SPY"] = [r for r in held["SPY"] if r.get(field) == value]

        return keep

    async def two_records(recorder: Recorder) -> None:
        store = held(Instruments().answering(recorder))
        # A second record holding Unusual Whales' own QQQ: the report of
        # QQQ beside the custodian's symbol meets two records.
        store.hold(
            "INS-QQQ-UW", ops.Identifier(scheme="symbol", value="QQQ", source="unusual_whales")
        )
        done = work(tmp, recorder)
        await done.symbols.listing(OTHER)

    async def withdrawn(recorder: Recorder) -> None:
        done = work(tmp, recorder)
        recorder.answer(
            "WantWithdrawn",
            lambda _: ops.WantWithdrawnEvent(want_id="w-standing", dataset=f"{INSTANCE}:options"),
        )
        await recorder.receive(want_withdrawn=done.on_withdrawn)

    async def licences(recorder: Recorder) -> None:
        dataset = f"{INSTANCE}:options"
        recorder.answer(
            "ListDatasets",
            lambda _: ops.ListDatasetsResult(licences=[ops.DatasetLicence(dataset=dataset)]),
        )
        done = work(tmp, recorder)
        await done.read_licences()
        assert done.wants.licensed == {dataset}

    async def heartbeat(recorder: Recorder) -> None:
        # A standing want's read that brings no new print: the dataset's
        # sign of life, no row.
        answering(recorder)
        sample = Sample()
        sample.trades["SPY"] = []
        done = work(tmp, recorder, sample)
        await done.on_want(
            want("w-standing", [SPY], key="option_trades", data_type=TRADE, standing=True)
        )

    async def delayed(recorder: Recorder, latency: Any) -> None:
        # A standing want's prints recorded, each one's age at the edge --
        # when it was read, less its execution time -- recorded.
        answering(recorder)
        done = work(tmp, recorder)
        done.latency = latency
        await done.on_want(
            want("w-standing", [SPY], key="option_trades", data_type=TRADE, standing=True)
        )

    async def calendar(recorder: Recorder) -> None:
        answering(recorder)
        done = work(tmp, recorder)
        await done.dates()

    tape = want("w-1", [SPY], key="option_trades", data_type=TRADE).message
    return {
        "a-subject-declined": wanted(want("w-2", [SPX]).message),
        "a-standing-want-withdrawn": withdrawn,
        "an-asset-that-does-not-resolve": two_records,
        "reads-its-datasets-licences": licences,
        "reports-its-feed-delay": feed_delay(delayed),
        "records-a-datasets-liveness": heartbeat,
        "a-trade-recorded": wanted(tape, only("upstream_condition_detail", "auto")),
        "a-condition-converted": wanted(
            want("w-1", [SPY], key="off_exchange", data_type=TRADE).message,
            only("sale_cond_codes", "odd_lot_execution", "off_exchange"),
        ),
        "a-condition-not-converted": wanted(tape, only("upstream_condition_detail", "zzzz")),
        "a-trade-withdrawn": wanted(tape, only("canceled", True)),
        "a-standing-want-streamed": wanted(
            want("w-1", [SPY], key="option_trades", data_type=TRADE, standing=True).message
        ),
        "queries-the-lake-within-bounds": lake_query(SPY, "trades"),
        "records-a-chains-series": wanted(want("w-1", [SPY]).message),
        "records-open-interest": wanted(
            want("w-1", [SPY], data_type="meridian.v1.Statistic").message
        ),
        "reads-a-calendar": calendar,
    }


def test_the_data_suite_passes(tmp_path: Path) -> None:
    report = run("data", producers(tmp_path), not_presented=NOT_PRESENTED, instance_id=INSTANCE)
    assert report.passed, report.failures
    assert sorted(report.not_presented) == sorted(NOT_PRESENTED)
    assert set(report.passed_cases) == PRESENTED | set(ANSWERED_BY_SDK)
