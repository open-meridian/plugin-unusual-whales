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


def test_each_licence_is_unusual_whales_public_terms() -> None:
    for dataset in CATALOGUE:
        licence = dataset.licence_default
        assert licence is not None
        assert licence.kept and licence.display and licence.personal_use
        assert licence.derived_use_terms == "internal_only"
        assert licence.redistribution == "licence_required"
        assert "not affiliated" in licence.not_affiliated_notice


def test_the_token_is_a_secret_setting() -> None:
    assert DECLARATION.secret_settings == ["api_token"]
    declared = {s.name: s for s in DECLARATION.settings}
    assert declared["api_token"].secret
    assert declared["sample_data"].developer
    assert [s.name for s in DECLARATION.settings] == ["api_token", "sample_data"]


def test_the_answers_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]
