"""The API as the plugin calls it: the token sent as a bearer token and
nowhere else, every answer kept as received, errors said in words, the
allowance read from the answer's headers, and a chain read page by page."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from meridian.edge import RawStore

from unusual_whales.api import Api, ApiError

from conftest import Sample

TOKEN = "test-token-not-real"


def test_the_token_is_a_bearer_token_and_never_kept(tmp_path: Path) -> None:
    sample = Sample()
    api = Api(RawStore(tmp_path), sample, "live", TOKEN)
    pages = api.contracts("SPY")
    assert len(pages) == 1 and len(pages[0][0]) == 8
    assert sample.headers[0]["Authorization"] == f"Bearer {TOKEN}"
    assert sample.headers[0]["User-Agent"].startswith("open-meridian")
    kept = list(RawStore(tmp_path).records())
    assert kept and TOKEN not in json.dumps(kept)


def test_without_a_token_no_authorization_is_sent(tmp_path: Path) -> None:
    sample = Sample()
    Api(RawStore(tmp_path), sample, "live").option_trades("SPY")
    assert "Authorization" not in sample.headers[0]


@pytest.mark.parametrize(
    ("status", "body", "said"),
    [
        (401, '{"code":"authentication_required","reason":"missing_token"}', "API token"),
        (403, '{"code":"historic_data_access_missing"}', "historic_data_access_missing"),
        (429, "slow down", "limiting"),
        (500, "boom", "500"),
    ],
)
def test_an_error_is_said_in_words(tmp_path: Path, status: int, body: str, said: str) -> None:
    api = Api(RawStore(tmp_path), Sample(status, body), "live", TOKEN)
    with pytest.raises(ApiError) as refused:
        api.option_trades("SPY")
    assert said in str(refused.value) and TOKEN not in str(refused.value)
    assert refused.value.status == status
    assert api.health.failures == 1 and api.health.last_error == str(refused.value)
    assert (api.health.rate_limited == 1) is (status == 429)


def test_the_allowance_as_the_api_states_it(tmp_path: Path) -> None:
    api = Api(RawStore(tmp_path), Sample(), "synthetic")
    api.option_trades("SPY")
    assert api.allowance.limit == "sample" and api.allowance.count == "0"


def test_a_chain_is_read_page_by_page(tmp_path: Path) -> None:
    sample = Sample()
    sample.contracts["SPY"] = sample.contracts["SPY"] * 70  # 560 rows: two pages
    pages = Api(RawStore(tmp_path), sample, "synthetic").contracts("SPY")
    assert [len(rows) for rows, _ in pages] == [500, 60]
    assert ["page=0" in r for r in sample.requests] == [True, False]


def test_the_tape_after_and_before_a_time(tmp_path: Path) -> None:
    sample = Sample()
    api = Api(RawStore(tmp_path), sample, "synthetic")
    rows, _ = api.option_trades("SPY")
    assert len(rows) == 7 and rows[0]["executed_at"] > rows[-1]["executed_at"]
    after = 1_793_293_200_000_000_000  # 2026-10-29 17:00:00 UTC
    later, _ = api.option_trades("SPY", newer_than_ns=after)
    assert len(later) == 4
    assert "newer_than=1793293200000" in sample.requests[-1]
