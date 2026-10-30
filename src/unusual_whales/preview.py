"""The pages on sample data, each printed as one HTML file: for looking at
them without a deployment.

    python -m unusual_whales.preview connection > preview/connection.html
    python -m unusual_whales.preview datasets > preview/datasets.html

The plugin's work runs on the SDK's lake as a test stands it in, in place of
a sidecar -- SPY a record the stand-in holds, the US equity calendar a
plain week, every batch recorded -- against the sample data, at 15:00 New
York on Thursday 29 October 2026: SPY's chain wanted and kept current, its
option prints and its off-exchange prints wanted standing, and an index's
chain declined. Each page links the kit where the dashboard serves it,
/.meridian/ui/<version>/: served beside the kit it is styled (`make preview
SHOTS=...` checks each in a browser). `connection-first` and
`datasets-first` are the pages before any want: the role's "not set up yet"
states.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meridian.edge import RawStore
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import Lake
from meridian.testing import PageClient

from .api import Api
from .declared import US_EQUITY_CALENDAR
from .page import hold, pages
from .synthetic import Synthetic
from .work import Work

INSTANCE = "unusual-whales"
SPY = "INS-PREVIEW-SPY"
SPX = "INS-PREVIEW-SPX"
#: Thursday 29 October 2026, 15:00 New York.
AT_NS = int(datetime(2026, 10, 29, 19, 0, tzinfo=UTC).timestamp()) * 1_000_000_000
PAGES = {
    "connection": "/",
    "datasets": "/datasets",
    "connection-first": "/",
    "datasets-first": "/datasets",
}


def calendar(params: Any) -> ops.ReadCalendarResult:
    """The US equity calendar as the stand-in answers it: Saturdays and
    Sundays closed, and no holiday in the span read."""
    return ops.ReadCalendarResult(
        found=True,
        calendar_id=params.calendar_id or US_EQUITY_CALENDAR,
        weekends=[ops.CalendarWeekend(weekdays=[ops.WEEKDAY_SATURDAY, ops.WEEKDAY_SUNDAY])],
        coverage=ops.CalendarCoverage(from_date=params.from_date, to_date=params.to_date),
    )


def want(want_id: str, key: str, subject: str, data_type: str, standing: bool = False) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=f"{INSTANCE}:{key}",
            data_type=data_type,
            subjects=[ops.SubjectRef(entity_id=subject)],
            standing=standing,
        ),
    )


def _work() -> Work:
    lake = Lake(INSTANCE)
    lake.instruments.hold(
        SPY,
        ops.Identifier(scheme="symbol", value="SPY", source="unusual_whales"),
        asset_class=ops.ASSET_CLASS_EQUITY,
    )
    lake.instruments.hold(
        SPX,
        ops.Identifier(scheme="symbol", value="SPX", source="unusual_whales"),
        instrument_type=ops.INSTRUMENT_TYPE_INDEX,
    )
    lake.answer("ReadCalendar", calendar)
    store = RawStore(Path(tempfile.mkdtemp(prefix="unusual-whales-preview-")))
    return Work(lake, Api(store, Synthetic(), "synthetic"), clock_ns=lambda: AT_NS)


async def worked() -> Work:
    """The work as sample data leaves it, on the stand-in lake."""
    work = _work()
    await work.on_want(want("want-chain", "options", SPY, "meridian.v1.ListedSeries", True))
    await work.on_want(want("want-tape", "option_trades", SPY, "meridian.v1.Trade", True))
    await work.on_want(want("want-off", "off_exchange", SPY, "meridian.v1.Trade", True))
    await work.on_want(want("want-spx", "options", SPX, "meridian.v1.Statistic"))
    return work


def render(page: str) -> str:
    work = _work() if page.endswith("-first") else asyncio.run(worked())
    hold(work)
    answer = PageClient(pages).get(PAGES[page], "admin")
    if answer.status != 200:
        raise SystemExit(f"{page} answered {answer.status}: {answer.text[:200]}")
    return answer.text


def main() -> None:
    page = sys.argv[1] if len(sys.argv) > 1 else "connection"
    if page not in PAGES:
        raise SystemExit(f"no page {page!r}: {', '.join(PAGES)}")
    sys.stdout.write(render(page))


if __name__ == "__main__":
    main()
