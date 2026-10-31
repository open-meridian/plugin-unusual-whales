"""Shared stand-ins: the API answered from the sample data and the requests
recorded for the tests, a clock a test moves, the deployment's records of
SPY and SPX, the platform's US equity calendar as a plain week, and the
lake's wants as the sidecar delivers them."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meridian.edge import RawStore
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import Instruments, Lake
from meridian.suites import Recorder

from unusual_whales.api import Api
from unusual_whales.preview import calendar
from unusual_whales.synthetic import Synthetic
from unusual_whales.work import Work

INSTANCE = "unusual-whales"
#: Thursday 29 October 2026, 15:00 New York: the sample's session open.
AT = datetime(2026, 10, 29, 19, 0, tzinfo=UTC)
SPY = "INS-SPY"
SPX = "INS-SPX"
#: A record of a listing another source resolved: a custodian's symbol.
OTHER = "INS-QQQ"
NO_SYMBOL = "INS-NOSYMBOL"


def held(store: Instruments) -> Instruments:
    store.hold(
        SPY,
        ops.Identifier(scheme="symbol", value="SPY", source="unusual_whales"),
        asset_class=ops.ASSET_CLASS_EQUITY,
    )
    store.hold(
        SPX,
        ops.Identifier(scheme="symbol", value="SPX", source="unusual_whales"),
        instrument_type=ops.INSTRUMENT_TYPE_INDEX,
    )
    store.hold(
        OTHER,
        ops.Identifier(scheme="symbol", value="QQQ", source="a-custodian"),
        asset_class=ops.ASSET_CLASS_EQUITY,
    )
    store.hold(NO_SYMBOL, ops.Identifier(scheme="cusip", value="000000000"))
    return store


def answering(recorder: Recorder, calendar_answers: bool = True) -> Recorder:
    """A suite recorder answering resolves from the records, and the calendar."""
    held(Instruments().answering(recorder))
    if calendar_answers:
        recorder.answer("ReadCalendar", calendar)
    return recorder


def lake(calendar_answers: bool = True) -> Lake:
    """The lake as a test stands it in, holding the records and the calendar."""
    made = Lake(INSTANCE)
    held(made.instruments)
    if calendar_answers:
        made.answer("ReadCalendar", calendar)
    return made


class Clock:
    """A clock a test moves, in nanoseconds."""

    def __init__(self, at: datetime = AT) -> None:
        self.ns = int(at.timestamp()) * 1_000_000_000

    def __call__(self) -> int:
        return self.ns

    def advance(self, seconds: int) -> None:
        self.ns += seconds * 1_000_000_000


class Sample(Synthetic):
    """The sample data, with what a test changes: the HTTP status every
    request answers, and the headers each request carried."""

    def __init__(self, status: int = 200, body: str = "refused") -> None:
        super().__init__()
        self.status = status
        self.body = body
        self.headers: list[dict[str, str]] = []

    def get(self, url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], str]:
        self.headers.append(dict(headers))
        if self.status != 200:
            self.requests.append(url)
            return self.status, {}, self.body
        return super().get(url, headers)


def work(
    tmp: Path, plugin: Any = None, transport: Any = None, clock: Any = None, mode: str = "synthetic"
) -> Work:
    """The plugin's work on the lake as a test stands it in and the sample
    data."""
    clock = clock or Clock()
    api = Api(RawStore(tmp), transport or Sample(), mode, clock_ns=clock)
    return Work(plugin if plugin is not None else lake(), api, clock_ns=clock)


def want(
    want_id: str,
    subjects: list[str],
    *,
    key: str = "options",
    standing: bool = False,
    data_type: str = "",
    valid_from_ns: int = 0,
    valid_until_ns: int = 0,
) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=f"{INSTANCE}:{key}",
            data_type=data_type,
            subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
            standing=standing,
            valid_from_ns=valid_from_ns,
            valid_until_ns=valid_until_ns,
        ),
    )


def sent(recorder: Recorder, row: str, name: str) -> list[Any]:
    """Every row a record operation sent, in the order sent."""
    return [r for params in recorder.on(row) for r in getattr(params, name)]
