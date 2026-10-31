"""The API as the plugin calls it: the token sent as a bearer token and
nowhere else, every answer kept as received, errors said in words, the
allowance read from the answer's headers, and a chain read page by page."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from meridian.edge import RawStore

from unusual_whales.api import (
    COUNT_HEADER,
    LIMIT_HEADER,
    MINUTE_RESET_HEADER,
    RETRIES,
    Allowance,
    Api,
    ApiError,
    backoff,
    resets_ns,
    waited,
)

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
    api = Api(RawStore(tmp_path), Sample(status, body), "live", TOKEN, sleep=lambda _: None)
    with pytest.raises(ApiError) as refused:
        api.option_trades("SPY")
    assert said in str(refused.value) and TOKEN not in str(refused.value)
    assert refused.value.status == status
    assert api.health.failures == 1 and api.health.last_error == str(refused.value)
    assert api.health.rate_limited == (RETRIES + 1 if status == 429 else 0)


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


class Limited(Sample):
    """The API answering 429 to the first `times` requests, with `said`
    headers."""

    def __init__(self, times: int, said: dict[str, str]) -> None:
        super().__init__()
        self.times, self.said = times, said

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], str]:
        if self.times > 0:
            self.times -= 1
            self.requests.append(url)
            return 429, dict(self.said), '{"code":"too_many_requests"}'
        return super().get(url, headers)


@pytest.mark.parametrize(
    ("said", "waits"),
    [
        ({"retry-after": "3"}, [3.0, 3.0]),
        ({MINUTE_RESET_HEADER: "12500"}, [12.5, 12.5]),
        ({}, [0.75, 1.5]),  # 1 then 2 seconds, each at the middle of its jitter
    ],
)
def test_a_429_is_waited_out(tmp_path: Path, said: dict[str, str], waits: list[float]) -> None:
    slept: list[float] = []
    api = Api(
        RawStore(tmp_path), Limited(2, said), "live", TOKEN, sleep=slept.append, rand=lambda: 0.5
    )
    rows, _ = api.option_trades("SPY")
    assert rows and slept == waits
    assert api.health.rate_limited == 2 and api.health.failures == 0 and api.health.calls == 3


def test_a_429_past_the_retries_fails(tmp_path: Path) -> None:
    slept: list[float] = []
    api = Api(
        RawStore(tmp_path), Limited(9, {"retry-after": "1"}), "live", TOKEN, sleep=slept.append
    )
    with pytest.raises(ApiError) as refused:
        api.option_trades("SPY")
    assert refused.value.status == 429 and len(slept) == RETRIES


def test_what_a_429_asks_to_be_waited() -> None:
    assert waited({"retry-after": "2"}) == 2.0
    assert waited({MINUTE_RESET_HEADER: "800"}) == 0.8
    assert waited({"retry-after": "Fri, 30 Oct 2026 20:00:00 GMT"}) is None
    assert waited({}) is None
    assert backoff(0, lambda: 0.0) == 0.5 and backoff(2, lambda: 1.0) == 4.0


NS = 1_000_000_000
#: Thursday 29 October 2026, 15:00 New York: five hours before the count resets.
AFTERNOON = int(datetime(2026, 10, 29, 19, 0, tzinfo=UTC).timestamp()) * NS
EVENING = AFTERNOON + 6 * 3600 * NS  # 21:00 New York: the next allowance day


def test_the_count_resets_at_20_new_york() -> None:
    assert resets_ns(AFTERNOON) == AFTERNOON + 5 * 3600 * NS
    assert resets_ns(EVENING) == AFTERNOON + 29 * 3600 * NS


def test_before_a_reset_is_seen_a_31st_of_the_allowance_a_day() -> None:
    held = Allowance()
    held.heard("25000", "4000", AFTERNOON)
    assert held.daily is None and held.share() == 806
    held.heard("", "4100", AFTERNOON + NS)
    # 806, less the 100 spent today and a tenth kept for wants asked now.
    assert held.left(AFTERNOON + NS) == 806 - 100 - 80
    assert held.gap_ns(AFTERNOON + NS) == (5 * 3600 - 1) * NS // 626


def test_a_count_that_resets_is_a_days_allowance() -> None:
    held = Allowance()
    held.heard("20000", "5000", AFTERNOON)
    held.heard("20000", "12", EVENING)
    assert held.daily is True and held.share() == 20_000
    assert held.left(EVENING) == 20_000 - 12 - 2_000


def test_a_count_that_runs_on_is_a_months() -> None:
    held = Allowance()
    held.heard("25000", "5000", AFTERNOON)
    held.heard("25000", "5050", EVENING)
    assert held.daily is False and held.left(EVENING) == 806 - 0 - 80


def test_with_nothing_left_standing_wants_wait_for_the_reset() -> None:
    held = Allowance(daily=True)
    held.heard("1000", "950", AFTERNOON)
    assert held.left(AFTERNOON) == 0
    assert held.gap_ns(AFTERNOON) == 5 * 3600 * NS
    assert "wait for 20:00" in held.said(AFTERNOON)


def test_no_allowance_stated_no_budget() -> None:
    held = Allowance()
    held.heard("sample", "0", AFTERNOON)
    assert held.left(AFTERNOON) is None and held.gap_ns(AFTERNOON) == 0
    assert "not budgeted" in held.said(AFTERNOON)


def test_the_allowance_headers_feed_the_budget(tmp_path: Path) -> None:
    class Stated(Sample):
        def get(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], str]:
            status, _, body = super().get(url, headers)
            return status, {LIMIT_HEADER: "20000", COUNT_HEADER: "150"}, body

    api = Api(RawStore(tmp_path), Stated(), "live", TOKEN, clock_ns=lambda: AFTERNOON)
    api.option_trades("SPY")
    assert api.allowance.limit == "20000" and api.allowance.left(AFTERNOON) == 645 - 64
