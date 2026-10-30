"""Sample data: the Unusual Whales API answered from files committed with the
plugin, so it runs, and is tested, with no token and nothing called. Every
value is made up, in the shape the API's documentation gives each answer --
never Unusual Whales' data.

- `synthetic/option_contracts.json`: SPY's chain as
  `/api/stock/{ticker}/option-contracts` answers it (`data`): six standard
  contracts over two expirations, an adjusted contract (root `SPY1`), and
  one whose volume is stated as null.
- `synthetic/option_trades.json`: SPY's prints of Thursday 29 October 2026
  as `/api/option-trades` answers them: a regular print, a sweep, a leg of
  a complex order, a late report, a print tied to a stock trade, one with a
  condition no table converts, and a cancelled one.
- `synthetic/off_exchange.json`: SPY's off-exchange prints of the same day
  as `/api/darkpool/{ticker}` answers them: a regular print, an odd lot, an
  average-price trade, an extended-hours trade, a cash-settled one, one with
  a condition no table converts, and a cancelled one.

The transport answers each request as the API would, by its path and query:
the chain's pages, the tape newest first after and before the times asked,
the off-exchange prints oldest first after the time asked; a ticker the
sample does not hold answers an empty `data`.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from importlib import resources
from typing import Any

from .api import CONTRACTS, OFF_EXCHANGE, OPTION_TRADES, PAGE
from .convert import moment_ns

_CONTRACTS = re.compile("^" + CONTRACTS.replace("{ticker}", "(?P<ticker>[^/]+)") + "$")
_OFF = re.compile("^" + OFF_EXCHANGE.replace("{ticker}", "(?P<ticker>[^/]+)") + "$")
MS = 1_000_000


def _json(name: str) -> dict[str, list[dict[str, Any]]]:
    text = (resources.files("unusual_whales") / "synthetic" / name).read_text(encoding="utf-8")
    held: dict[str, list[dict[str, Any]]] = json.loads(text)
    return held


def _at(row: dict[str, Any]) -> int:
    return moment_ns(row.get("executed_at")) or 0


class Synthetic:
    """The API, answered from the committed sample data."""

    def __init__(self) -> None:
        self.contracts = _json("option_contracts.json")
        self.trades = _json("option_trades.json")
        self.off_exchange = _json("off_exchange.json")
        self.requests: list[str] = []

    @staticmethod
    def _answer(rows: list[dict[str, Any]]) -> tuple[int, dict[str, str], str]:
        return (
            200,
            {"x-uw-token-req-limit": "sample", "x-uw-daily-req-count": "0"},
            json.dumps({"data": rows}),
        )

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], str]:
        self.requests.append(url)
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        limit = int(query.get("limit", PAGE))
        newer = int(query.get("newer_than", "0")) * MS
        older = int(query.get("older_than", "0")) * MS
        path = urllib.parse.unquote(parts.path)
        found = _CONTRACTS.match(path)
        if found:
            rows = self.contracts.get(found.group("ticker").upper(), [])
            page = int(query.get("page", "0"))
            return self._answer(rows[page * limit : (page + 1) * limit])
        if path == OPTION_TRADES:
            rows = self.trades.get(query.get("ticker_symbol", "").upper(), [])
            rows = [
                r for r in rows if (not newer or _at(r) > newer) and (not older or _at(r) < older)
            ]
            return self._answer(sorted(rows, key=_at, reverse=True)[:limit])
        found = _OFF.match(path)
        if found:
            rows = self.off_exchange.get(found.group("ticker").upper(), [])
            rows = [r for r in rows if not newer or _at(r) > newer]
            return self._answer(sorted(rows, key=_at)[:limit])
        return 404, {}, "not found"
