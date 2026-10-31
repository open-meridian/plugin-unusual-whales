"""The Unusual Whales API, as this plugin calls it, with the standard library.

Every request carries the deployment's API token as `Authorization: Bearer
<token>` (the API's documented authentication): the token is the
deployment's, entered by its admin in Settings (a secret setting), sent on
each request and nowhere else -- never logged, never kept with a response,
never shown. Each answer is kept as received before anything is read from
it (the SDK's `RawStore`, decisions/028).

Three calls, each Unusual Whales' documented REST endpoint
(https://api.unusualwhales.com/docs):

- `contracts(ticker, page)`: `GET /api/stock/{ticker}/option-contracts`,
  every option contract of an underlying, 500 a page from page 0: its
  symbol, open interest and volume (convert.contracts reads them);
- `option_trades(ticker, newer_than)`: `GET /api/option-trades`, the
  latest trading day's option prints of one underlying, newest first, at
  most 500 a call, after a time (convert.option_trades);
- `off_exchange(ticker, newer_than)`: `GET /api/darkpool/{ticker}`, an
  equity's off-exchange prints of the latest market day, after a time
  (convert.off_exchange_trade).

**Its limits** are the plan's: a request allowance per day on most plans
(reset at 20:00 New York), or per billing month on the Options Starter plan
(25,000), counted on HTTP 200 answers only, every token of the account
sharing it. The API states the allowance and the count on each answer
(`x-uw-token-req-limit`, `x-uw-daily-req-count`), which Connection shows,
and against which the standing wants' polling is budgeted (`Allowance`,
0.1.1): what is left of the day's share, less a reserve for wants asked now,
spread evenly until the count resets. Where the count has not yet been seen
to reset at 20:00, the allowance is taken as a month's (Options Starter's),
a 31st of it a day, so a month's allowance lasts the month.

**A 429** is the API's per-minute cap (its usage guide): it is waited out
(0.1.1) as `Retry-After` asks, else until the minute resets
(`x-uw-req-per-minute-reset`, milliseconds), else after a backoff of 1, 2
then 4 seconds with jitter; at most `RETRIES` times, each counted, and only
then is the call failed. This plugin makes one request at a time.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from meridian.edge import RawStore
from meridian.roles.data import Endpoint, Health, Limits, Session

from .convert import NEW_YORK, NS

log = logging.getLogger(__name__)

BASE = "https://api.unusualwhales.com"
CONTRACTS = "/api/stock/{ticker}/option-contracts"
OPTION_TRADES = "/api/option-trades"
OFF_EXCHANGE = "/api/darkpool/{ticker}"
#: The most rows one page or call answers (the API's `limit`, 1 to 500).
PAGE = 500
#: The most pages of one chain read: 25,000 contracts, past any listed chain.
MOST_PAGES = 50
#: How long one request may take before it is given up, in seconds.
TIMEOUT_SECONDS = 30
ALLOWED = (
    "as the token's plan allows: a daily request allowance, or 25,000 a month on Options "
    "Starter; HTTP 200 answers alone are counted"
)
LIMIT_HEADER = "x-uw-token-req-limit"
COUNT_HEADER = "x-uw-daily-req-count"
#: Milliseconds until the API's per-minute counter resets (its usage guide).
MINUTE_RESET_HEADER = "x-uw-req-per-minute-reset"
#: How many times a 429 is waited out before the call fails.
RETRIES = 3
#: The first wait after a 429 that says no wait, in seconds; doubled each time.
BACKOFF_FIRST_SECONDS = 1.0
#: The longest one wait may be, whatever the API asks.
WAIT_MOST_SECONDS = 60.0
#: When the API resets its daily count, New York.
RESETS_AT = dt.time(20, 0)
#: The share of a day's allowance kept for wants asked now: never spent on
#: standing wants.
RESERVE_SHARE = 0.1
#: The days a month's allowance is spread over, a day's share a 31st of it.
MONTH_DAYS = 31


class ApiError(Exception):
    """The API answered with an error, or could not be reached: its status
    (0 for none) and what it said, in words that never carry the token."""

    def __init__(self, status: int, said: str) -> None:
        super().__init__(said)
        self.status = status


def waited(headers: Mapping[str, str]) -> float | None:
    """The seconds a 429 asks to be waited: `Retry-After` in seconds, else
    until the minute's counter resets; None where it says neither."""
    for name, scale in (("retry-after", 1.0), (MINUTE_RESET_HEADER, 1000.0)):
        try:
            seconds = float(headers.get(name, "").strip()) / scale
        except ValueError:
            continue
        if seconds >= 0:
            return seconds
    return None


def backoff(attempt: int, rand: Callable[[], float] = random.random) -> float:
    """The wait before retry `attempt` (0 first) where the API said none: 1,
    2, 4 seconds, each between half and the whole of it (jitter)."""
    full = min(BACKOFF_FIRST_SECONDS * (1 << attempt), WAIT_MOST_SECONDS)
    return full / 2 + rand() * full / 2


class Transport(Protocol):
    """How the API is reached: one request, its status, headers and body."""

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], str]: ...


class Https:
    """The API over HTTPS, with the standard library."""

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], str]:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as answer:  # noqa: S310 - the API's https address
                said = {k.lower(): v for k, v in answer.headers.items()}
                return int(answer.status), said, answer.read().decode("utf-8")
        except urllib.error.HTTPError as refused:
            said = {k.lower(): v for k, v in (refused.headers or {}).items()}
            return int(refused.code), said, refused.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as unreached:
            raise ApiError(0, f"the Unusual Whales API was not reached: {unreached}") from None


def _said(status: int, body: str) -> str:
    """What an error answer means, in words for a person: the API's own
    `code` where it states one (403 names the entitlement missing)."""
    code = ""
    try:
        held = json.loads(body)
        if isinstance(held, dict):
            code = str(held.get("code") or held.get("reason") or "")
    except ValueError:
        pass
    if status == 401:
        return (
            "the API refused the request (401): it needs the deployment's Unusual Whales API "
            "token, set in Settings"
        )
    if status == 403:
        return f"the API refused the token for this request (403{': ' + code if code else ''})"
    if status == 404:
        return "the API has no such route (404)"
    if status == 422:
        return "the API refused the request's parameters (422): an index has no raw quotes"
    if status == 429:
        return "the API is limiting this token's requests (429)"
    if status == 503:
        return "the API asks to be tried again later (503)"
    return f"the API answered {status}: {body[:120]}"


def _number(text: str) -> int | None:
    try:
        return int(text.replace(",", "").strip())
    except ValueError:
        return None


def allowance_day(at_ns: int) -> dt.date:
    """The day of the allowance a moment counts toward: it ends at 20:00 New
    York, when the API resets its count."""
    moment = dt.datetime.fromtimestamp(at_ns / NS, NEW_YORK)
    return moment.date() + dt.timedelta(days=1 if moment.time() >= RESETS_AT else 0)


def resets_ns(at_ns: int) -> int:
    """When the allowance a moment counts toward resets: 20:00 New York."""
    ends = dt.datetime.combine(allowance_day(at_ns), RESETS_AT, NEW_YORK)
    return int(ends.timestamp()) * NS


@dataclass
class Allowance:
    """The plan's request allowance and the count toward it, as the API last
    stated them (empty before any answer stated them), and what of it the
    standing wants may spend: the day's share less a reserve, spread until
    the count resets.

    A day's share is the whole allowance once the count has been seen to
    reset at 20:00 New York (a daily plan); before that -- and on Options
    Starter, whose count runs for the billing month -- a 31st of it, so the
    month's allowance lasts the month."""

    limit: str = ""
    count: str = ""
    #: Whether the count resets daily: True once seen to, False once seen
    #: not to, None before a reset has been seen.
    daily: bool | None = None
    #: The allowance day last heard, its first count and the latest.
    day: dt.date | None = None
    first: int = 0
    last: int = 0

    def heard(self, limit: str, count: str, at_ns: int) -> None:
        """An answer's headers: the allowance and the count it states."""
        if limit:
            self.limit = limit[:32]
        if not count:
            return
        self.count = count[:32]
        stated = _number(count)
        if stated is None:
            return
        day = allowance_day(at_ns)
        if day != self.day:
            if self.day is not None and self.last > 0:
                self.daily = stated < self.last
            self.day, self.first = day, stated
        self.last = stated

    def share(self) -> int | None:
        """The requests a day may spend; None where no allowance is stated."""
        limit = _number(self.limit)
        if limit is None:
            return None
        return limit if self.daily else limit // MONTH_DAYS

    def left(self, at_ns: int) -> int | None:
        """The requests standing wants may still spend before the count
        resets: the day's share, less what was spent toward it and the
        reserve; None where no allowance is stated."""
        share = self.share()
        if share is None:
            return None
        spent = 0
        if self.day == allowance_day(at_ns):
            spent = self.last if self.daily else self.last - self.first
        return max(share - spent - int(share * RESERVE_SHARE), 0)

    def gap_ns(self, at_ns: int) -> int:
        """The time one standing request may take of what is left, so it
        lasts until the count resets: 0 where no allowance is stated, the
        whole time to the reset where nothing is left."""
        left = self.left(at_ns)
        if left is None:
            return 0
        until = max(resets_ns(at_ns) - at_ns, 0)
        return until if left <= 0 else until // left

    def said(self, at_ns: int) -> str:
        """What the budget allows, in words for Connection."""
        left = self.left(at_ns)
        if left is None:
            return "Standing wants are not budgeted until the API states an allowance."
        basis = (
            "the day's allowance"
            if self.daily
            else "a 31st of the allowance a day (a month's, until the count is seen to reset "
            "at 20:00 New York)"
        )
        if left <= 0:
            return (
                f"Standing wants wait for 20:00 New York: {basis}, less a tenth kept for wants "
                "asked now, is spent."
            )
        gap = self.gap_ns(at_ns) / NS
        return (
            f"Standing wants may spend {left:,} more requests until 20:00 New York, "
            f"one every {gap:,.0f} s at most: {basis}, less a tenth kept for wants asked now."
        )


class Api:
    """The API, as this plugin calls it: each call counted on its session's
    health, each answer kept before it is read."""

    def __init__(
        self,
        store: RawStore,
        transport: Transport,
        mode: str = "live",
        token: str = "",
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[], float] = random.random,
        clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        self.store = store
        self.transport = transport
        self.token = token
        self.sleep, self.rand, self.clock_ns = sleep, rand, clock_ns
        self.allowance = Allowance()
        self.session = Session(
            mode=mode,
            endpoints=(
                Endpoint(
                    "Option contracts",
                    BASE + CONTRACTS,
                    "an underlying's chain: series, open interest, volume",
                ),
                Endpoint(
                    "Option trades",
                    BASE + OPTION_TRADES,
                    "the day's option prints of an underlying",
                ),
                Endpoint(
                    "Off-exchange prints",
                    BASE + OFF_EXCHANGE,
                    "an equity's prints reported off exchange",
                ),
            ),
            limits=Limits(allowed=ALLOWED, spent="one request at a time"),
        )

    @property
    def mode(self) -> str:
        return self.session.mode

    @property
    def health(self) -> Health:
        return self.session.health

    def use_token(self, token: str) -> None:
        self.token = token.strip()

    def _headers(self) -> dict[str, str]:
        # The API asks for a real User-Agent (its WebSocket documentation).
        headers = {
            "User-Agent": "open-meridian-plugin-unusual-whales",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _url(self, path: str, query: Sequence[tuple[str, str]] = ()) -> str:
        return BASE + path + ("?" + urllib.parse.urlencode(list(query)) if query else "")

    def get(
        self, call: str, name: str, path: str, query: Sequence[tuple[str, str]] = ()
    ) -> tuple[Any, str]:
        """One request: its answer kept, then its JSON and the raw record's
        key; a 429 waited out up to `RETRIES` times; an error answer kept
        too, then raised in words."""
        url = self._url(path, query)
        health = self.health
        attempt = 0
        while True:
            health.calls += 1
            try:
                status, headers, body = self.transport.get(url, self._headers())
            except ApiError as failed:
                self._failed(str(failed))
                raise
            now = time.time_ns()
            key = self.store.keep(
                call, name, {"received_at_ns": now, "request": url, "status": status, "body": body}
            )
            self.allowance.heard(
                headers.get(LIMIT_HEADER, ""), headers.get(COUNT_HEADER, ""), self.clock_ns()
            )
            if status != 429:
                break
            health.rate_limited += 1
            if attempt >= RETRIES:
                break
            asked = waited(headers)
            wait = backoff(attempt, self.rand) if asked is None else asked
            log.info("the API answered 429; waiting %.1f s before trying again", wait)
            self.sleep(min(wait, WAIT_MOST_SECONDS))
            attempt += 1
        if status != 200:
            said = _said(status, body)
            self._failed(said)
            raise ApiError(status, said)
        try:
            held = json.loads(body)
        except ValueError:
            said = "the API answered something other than JSON"
            self._failed(said)
            raise ApiError(status, said) from None
        health.last_ok_ns = now
        return held, key

    def _failed(self, said: str) -> None:
        health = self.health
        health.failures += 1
        health.last_failed_ns = time.time_ns()
        health.last_error = said

    # ── The calls ───────────────────────────────────────────────────────

    def contracts(self, ticker: str) -> list[tuple[list[dict[str, Any]], str]]:
        """Every option contract of an underlying, page by page, each page's
        rows with the raw record it came in; the pages end at the first that
        is not full."""
        out: list[tuple[list[dict[str, Any]], str]] = []
        path = CONTRACTS.format(ticker=urllib.parse.quote(ticker, safe=""))
        for page in range(MOST_PAGES):
            held, key = self.get(
                "option_contracts", f"{ticker}-{page}", path,
                [("limit", str(PAGE)), ("page", str(page))],
            )  # fmt: skip
            rows = _rows(held)
            out.append((rows, key))
            if len(rows) < PAGE:
                break
        return out

    def option_trades(
        self, ticker: str, newer_than_ns: int = 0, older_than_ns: int = 0
    ) -> tuple[list[dict[str, Any]], str]:
        """The latest trading day's option prints of one underlying, newest
        first, after a time and before another (in nanoseconds; 0 for no
        bound), at most a call's 500."""
        query = [("ticker_symbol", ticker), ("limit", str(PAGE))]
        if newer_than_ns:
            query.append(("newer_than", str(newer_than_ns // 1_000_000)))
        if older_than_ns:
            query.append(("older_than", str(older_than_ns // 1_000_000)))
        held, key = self.get("option_trades", ticker, OPTION_TRADES, query)
        return _rows(held), key

    def off_exchange(self, ticker: str, newer_than_ns: int = 0) -> tuple[list[dict[str, Any]], str]:
        """An equity's off-exchange prints of the latest market day after a
        time, oldest first, at most a call's 500."""
        query = [("limit", str(PAGE)), ("order", "asc")]
        if newer_than_ns:
            query.append(("newer_than", str(newer_than_ns // 1_000_000)))
        path = OFF_EXCHANGE.format(ticker=urllib.parse.quote(ticker, safe=""))
        held, key = self.get("off_exchange", ticker, path, query)
        return _rows(held), key


def _rows(held: Any) -> list[dict[str, Any]]:
    """An answer's rows: its `data` array, every row an object."""
    rows = held.get("data", []) if isinstance(held, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
