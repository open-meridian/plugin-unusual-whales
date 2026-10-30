"""Unusual Whales' options flow and market data as an Open Meridian data
plugin.

It connects to the sidecar it is launched beside with its whole declaration
(declaration.py): its catalogue, its storage, its settings, its pages
(page.py) and its documentation; and serves the pages. Once the settings
have said where to answer from -- the Unusual Whales API with the
deployment's API token, or sample data -- it hears what the lake wants of it
and records it or declines it, and keeps each standing want current by
reading the API at its dataset's cadence (work.py), until stopped. Everything
goes through the sidecar; nothing but the Unusual Whales API is called, and
with sample data not even that (synthetic.py).

It holds nothing it cannot lose: the API's answers are kept in the storage
the deployment grants it (decisions/028), moved past their window as the
settings say; a restart hears again what the lake wants, and reads each
tape afresh from the day's newest prints. The token is held in memory only,
as the settings deliver it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Mapping
from datetime import UTC, datetime

import meridian
from meridian.edge import RawStore, storage_root
from meridian.roles import Latency

from .api import Api, Https
from .declaration import DECLARATION, PORT
from .declared import API_TOKEN, KIND, SAMPLE_DATA, WINDOW_DAYS
from .page import figures, hold, pages
from .synthetic import Synthetic
from .work import Work

log = logging.getLogger("unusual_whales")

#: How often the datasets' licences are read again and the figures set.
LICENCES_SECONDS = 60
#: How long before a broken settings stream is asked again, in seconds.
RETRY_SECONDS = 2


def source(store: RawStore, sample_data: bool, token: str) -> Api:
    """The API itself with the deployment's token, or the sample data."""
    if sample_data:
        return Api(store, Synthetic(), "synthetic")
    return Api(store, Https(), "live", token)


async def apply(
    plugin: meridian.Plugin, work: Work, store: RawStore, values: Mapping[str, object]
) -> None:
    """One delivery of the settings: the source switched where sample data
    changed, the token given to the API, and the raw answers past their
    window moved. The token's value is never logged: only whether it is
    set."""
    sample = values.get(SAMPLE_DATA) is True
    given = values.get(API_TOKEN)
    token = given.strip() if isinstance(given, str) else ""
    log.info("settings delivered: sample data %s, an API token %s", sample,
             "set" if token else "not set")  # fmt: skip
    if sample != (work.api.mode != "live"):
        work.use(source(store, sample, token))
        log.info("answering from %s", work.api.mode)
    if work.api.mode == "live":
        work.api.use_token(token)
    window = values.get(f"{KIND}_window_days")
    past = values.get(f"{KIND}_past_window")
    await store.tend(
        plugin,
        window if isinstance(window, int) else WINDOW_DAYS,
        past if isinstance(past, str) else "kept",
        datetime.now(UTC).date(),
    )


async def watch_settings(
    plugin: meridian.Plugin, work: Work, store: RawStore, configured: asyncio.Event
) -> None:
    while True:
        try:
            async for delivered in plugin.settings():
                await apply(plugin, work, store, delivered.values)
                configured.set()
        except Exception as failed:  # noqa: BLE001 - the stream broke: said, and watched again
            log.warning("the settings' stream broke, watching again: %s", failed)
        await asyncio.sleep(RETRY_SECONDS)


async def hear_wants(plugin: meridian.Plugin, work: Work, configured: asyncio.Event) -> None:
    """What the lake wants, once the settings have said where to answer from."""
    await configured.wait()
    await plugin.receive(observations_wanted=work.on_want, want_withdrawn=work.on_withdrawn)


async def keep_current(work: Work, configured: asyncio.Event) -> None:
    await configured.wait()
    await work.keep_current()


async def report_health(plugin: meridian.Plugin, work: Work) -> None:
    """Each minute: its datasets' licences read again (contract v20), and
    on the heartbeat whether the API answers, with the data role's figures."""
    while True:
        try:
            await work.read_licences()
        except meridian.MeridianError as failed:
            log.warning("licences not read: %s", failed)
        health = work.api.health
        healthy = health.healthy
        detail = "The Unusual Whales API answers" if healthy else health.last_error
        try:
            await plugin.report(healthy=healthy, detail=detail[:200], figures=figures(work))
        except (meridian.MeridianError, ValueError) as failed:
            log.warning("health not reported: %s", failed)
        await asyncio.sleep(LICENCES_SECONDS)


def _said(task: asyncio.Task[None]) -> None:
    """A task that stopped, said with why, and the plugin stopped with it: a
    restart starts it again."""
    if not task.cancelled() and task.exception() is not None:
        log.error("stopped: %r", task.exception(), exc_info=task.exception())
        os._exit(1)


async def run() -> None:
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop, stopped.set)

    async with await meridian.connect(declaration=DECLARATION) as plugin:
        log.info("registered as %s, roles %s", plugin.identity.instance_id, plugin.identity.roles)
        store = RawStore(storage_root(), KIND)
        work = Work(plugin, source(store, sample_data=False, token=""))
        # Contract v28 (ruling 518): each row recorded unasked or for a
        # standing want has its age at the edge recorded, reported every 10
        # seconds (ReportLatency).
        work.latency = Latency(plugin)
        hold(work)
        served = pages.serve(plugin, PORT)
        configured = asyncio.Event()
        tasks = [
            asyncio.create_task(watch_settings(plugin, work, store, configured)),
            asyncio.create_task(hear_wants(plugin, work, configured)),
            asyncio.create_task(keep_current(work, configured)),
            asyncio.create_task(report_health(plugin, work)),
            asyncio.create_task(work.latency.run()),
        ]
        for task in tasks:
            task.add_done_callback(_said)
        await stopped.wait()
        log.info("stopping")
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        served.shutdown()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
