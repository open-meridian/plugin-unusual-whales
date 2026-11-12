"""The catalogue, from code, as the deployment approves it: an option chain,
the option tape and the off-exchange prints, each Unusual Whales' under its
public terms."""

from __future__ import annotations

from meridian.plugin.v1 import operations_pb2 as ops

from unusual_whales.declaration import DECLARATION
from unusual_whales.declared import CATALOGUE, UNDERLYING_SOURCE, US_EQUITY_CALENDAR, VENDOR


def test_three_datasets() -> None:
    assert [d.key for d in DECLARATION.catalogue] == ["options", "option_trades", "off_exchange"]
    for dataset in CATALOGUE:
        assert dataset.vendor == VENDOR == "Unusual Whales"
        assert not dataset.venue_id and not dataset.aggregator
        assert dataset.calendar_id == US_EQUITY_CALENDAR
        assert dataset.day_time_zone == "America/New_York" and dataset.day_end_minute == 960
        assert dataset.declared_delay_ns == 0
        assert UNDERLYING_SOURCE[dataset.key]


def test_each_by_its_kinds() -> None:
    by_key = {d.key: d for d in CATALOGUE}
    assert list(by_key["options"].data_types) == [
        "meridian.v1.ListedSeries", "meridian.v1.Statistic",
    ]  # fmt: skip
    assert [ops.ObservationMode.Name(m) for m in by_key["options"].modes] == [
        "OBSERVATION_MODE_PULL"
    ]
    for key in ("option_trades", "off_exchange"):
        assert list(by_key[key].data_types) == [
            "meridian.v1.Trade", "meridian.v1.Trade.quote_at_trade",
        ]  # fmt: skip
        assert [ops.ObservationMode.Name(m) for m in by_key[key].modes] == [
            "OBSERVATION_MODE_PULL", "OBSERVATION_MODE_STREAM",
        ]  # fmt: skip


def test_each_datasets_terms_are_unusual_whales_public_terms() -> None:
    # Contract 30 (ruling 1032): the public pages' terms in words, the source
    # behind each first, never a licence; how a gap is recovered; and the
    # off-exchange prints in the FINRA facilities' hours.
    for dataset in CATALOGUE:
        terms = dataset.terms_and_pricing
        assert terms.startswith("OPRA" if dataset.key != "off_exchange" else "FINRA")
        assert "personal use" in terms and "redistribution licence" in terms
        assert "not affiliated" in terms and len(terms) <= 2000
    assert {d.key: d.gap_recovery for d in CATALOGUE} == {
        "options": "none",
        "option_trades": "stream_only",
        "off_exchange": "stream_only",
    }
    assert {d.key: d.sessions_calendar_id for d in CATALOGUE} == {
        "options": "",
        "option_trades": "",
        "off_exchange": "CAL-01M5TTQCH5NTYF33970T8GVF1D",
    }


def test_the_token_is_a_secret_setting() -> None:
    assert DECLARATION.secret_settings == ["api_token"]
    declared = {s.name: s for s in DECLARATION.settings}
    assert declared["api_token"].secret
    assert declared["sample_data"].developer
    assert [s.name for s in DECLARATION.settings] == ["api_token", "sample_data"]


def test_the_answers_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]
