"""The plugin's pages, under Manage alone: the data role's common pages
(spec/plugin-pages-follow-their-role), Connection and Datasets, each also a
read tool for agents on the deployment's MCP under the role's names
(`read_connection`, `read_datasets`). Each record is the role's
(`meridian.roles.data`), extended with Unusual Whales' fields; each template
is the role's, with Unusual Whales' nuance at its blocks only.

- **Connection** (`/`): the role's "Key" (the API token, set or not --
  never its value), "Limits and use" and "Stream"; then Unusual Whales' own:
  the plan's request allowance and the count toward it as the API last
  stated them, the calendar the trading dates follow, and the standing
  wants' reading.
- **Datasets** (`/datasets`): the role's "Served", "Wants" and "Subjects",
  with Unusual Whales' "Behind" column: the source behind each dataset's
  values (ruling 387).

Neither shows a price, a print or a figure: those are the reading roles' to
show.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import meridian
from meridian.edge import RawStore, storage_root
from meridian.roles import data

from .api import Api
from .declared import CATALOGUE, KEYS, UNDERLYING_SOURCE
from .synthetic import Synthetic
from .work import Work

TITLE = "Unusual Whales"

pages = meridian.Pages(TITLE, templates=Path(__file__).parent / "templates")

#: How many wants the Datasets tab draws; read_datasets answers every one held.
SHOWN_WANTS = 3
DEFAULT_TERMS = (
    "kept, one person's, display, derived use internal only, redistribution by licence only"
)
#: Each dataset's source behind, as the Datasets column says it briefly.
BEHIND_SHORT = {key: ("FINRA TRF" if key == "off_exchange" else "OPRA") for key in KEYS}


@dataclass(frozen=True)
class Behind:
    """One dataset and the source behind its values."""

    dataset: str
    short: str
    source: str


@dataclass(frozen=True)
class ConnectionRead(data.ConnectionRead):
    """Connection's common fields, then Unusual Whales': the plan's request
    allowance and the count toward it as last stated, the calendar, and the
    standing wants' reading."""

    allowance: str = ""
    allowance_used: str = ""
    calendar: str = ""
    calendar_error: str = ""
    standing: int = 0
    tape_passes: int = 0
    tape_gaps: int = 0
    tape_error: str = ""


@dataclass(frozen=True)
class DatasetsRead(data.DatasetsRead):
    """Datasets' common fields, then Unusual Whales': the source behind each
    dataset's values."""

    behind: list[Behind] = field(default_factory=list)


_held: dict[str, Work] = {}


def hold(work: Work) -> None:
    """The work the pages read, once the plugin has registered."""
    _held["work"] = work


def _mode(work: Work) -> str:
    if work.api.mode != "live":
        return "Sample data"
    return "Live" if work.api.token else "No key"


def connection_read(work: Work) -> ConnectionRead:
    health = work.api.health
    keyed = bool(work.api.token)
    calendar = work.calendar
    return ConnectionRead(
        mode=_mode(work),
        credentials=[data.Credential("Unusual Whales API token", keyed)],
        entitled_at_vendor=(
            "Sample data: no token needed"
            if work.api.mode != "live"
            else "As the token's plan allows"
            if keyed
            else "Nothing: every request asks for a token"
        ),
        limit=f"{work.api.session.limits.allowed}. This plugin: one request at a time",
        calls=health.calls,
        rate_limited=health.rate_limited,
        last_call_at=data.iso_time(max(health.last_ok_ns, health.last_failed_ns)),
        last_error=health.last_error,
        sessions=None,
        allowance=work.api.allowance.limit,
        allowance_used=work.api.allowance.count,
        calendar=calendar.calendar_id if calendar.read_on else "",
        calendar_error=calendar.error,
        standing=len(work.wants.standing),
        tape_passes=work.tapes.passes,
        tape_gaps=work.tapes.gaps,
        tape_error=work.tapes.error,
    )


def datasets_read(work: Work) -> DatasetsRead:
    instance = work.plugin.identity.instance_id
    served = data.served(
        CATALOGUE,
        instance,
        work.wants,
        "As the token's plan allows" if work.api.mode == "live" else "Sample data",
    )
    return DatasetsRead(
        served=[replace(s, default_terms=DEFAULT_TERMS) for s in served],
        wants=list(data.want_rows(work.wants)),
        reads_instruments=work.symbols.reads_instruments,
        behind=[
            Behind(f"{instance}:{key}", BEHIND_SHORT[key], UNDERLYING_SOURCE[key]) for key in KEYS
        ],
    )


def figures(work: Work) -> list[meridian.Figure]:
    """The data role's figures, in its order; Unusual Whales' plugin reports
    none of its own."""
    health = work.api.health
    mode = _mode(work)
    if mode in ("Sample data", "No key"):
        connection: Any = mode
    elif not health.healthy:
        connection = meridian.Figure(
            "", "Not answering", state="error", why=health.last_error[:200]
        )
    else:
        connection = "Answering"
    last = work.wants.counts.last_ns
    standing = len(work.wants.standing)
    return data.figures(
        connection=connection,
        entitled_at_vendor=f"{len(KEYS)} of {len(KEYS)} datasets",
        stream=f"{standing} standing wants, polled" if standing else "Off",
        last_recorded=datetime.fromtimestamp(last / 10**9, UTC) if last else None,
    )


def _running(request: meridian.Request) -> Work:
    held = _held.get("work")
    if held is None:
        held = Work(request.plugin, Api(RawStore(storage_root()), Synthetic(), "synthetic"))
    return held


@pages.page(
    "/",
    "Connection",
    levels="admin",
    answers=ConnectionRead,
    name="read_connection",
    description=(
        "How this plugin reaches the Unusual Whales API, as every data plugin's Connection "
        "answers it: the mode (Live, No key or Sample data), whether the API token is set "
        "(never its value), the calls made and the last error. Then Unusual Whales' own: the "
        "plan's request allowance and the count toward it as the API last stated them, the "
        "calendar the trading dates follow, and how the standing wants' reading is going. No "
        "price, print or figure."
    ),
)
async def connection(request: meridian.Request) -> meridian.Response:
    return pages.answer("connection.html", connection_read(_running(request)))


@pages.page(
    "/datasets",
    "Datasets",
    levels="admin",
    answers=DatasetsRead,
    name="read_datasets",
    description=(
        "What this plugin serves the lake, as every data plugin's Datasets answers it: its "
        "three datasets as the catalogue declares them (option chains' series and statistics, "
        "option prints, and off-exchange equity prints), whether a deployment admin has "
        "licensed each, what it recorded and declined, and the wants it answered and keeps "
        "current. Then Unusual Whales' own: the source behind each dataset's values. No "
        "price, print or figure."
    ),
)
async def datasets(request: meridian.Request) -> meridian.Response:
    read = datasets_read(_running(request))
    drawn = read if request.tool_name else replace(read, wants=read.wants[:SHOWN_WANTS])
    return pages.answer("datasets.html", drawn)
