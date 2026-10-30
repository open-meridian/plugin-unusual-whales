"""The two pages under Manage, and their read tools: what each shows, to
whom, that neither shows a price or a print, and that the token is never
shown."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from meridian.testing import PageClient

from unusual_whales.page import connection_read, datasets_read, figures, hold, pages

from conftest import SPX, SPY, Sample, want, work

TOKEN = "test-token-not-real"


@pytest.fixture
def client(tmp_path: Path) -> PageClient:
    done = work(tmp_path)

    async def run() -> None:
        await done.on_want(want("w-1", [SPY], standing=True))
        await done.on_want(
            want("w-2", [SPY], key="option_trades", data_type="meridian.v1.Trade", standing=True)
        )
        await done.on_want(want("w-3", [SPX]))

    asyncio.run(run())
    hold(done)
    return PageClient(pages)


def test_each_page_is_managed_alone(client: PageClient) -> None:
    served = {(r.page.path, r.level): r.response.status for r in client.every_page()}
    assert served == {
        ("/", "admin"): 200,
        ("/", "write"): 403,
        ("/", "read"): 403,
        ("/datasets", "admin"): 200,
        ("/datasets", "write"): 403,
        ("/datasets", "read"): 403,
    }
    # No price or print on any page: the sample's are the readers'.
    client.assert_no_account_data("12.10", "579.8450", "18250")


def test_connection_says_how_the_api_is_reached(client: PageClient) -> None:
    text = client.get("/", "admin").text
    assert text.index("<h2>Key</h2>") < text.index("<h2>Limits and use</h2>")
    assert text.index('<th scope="row">Allowance</th>') < text.index("<h2>Stream</h2>")
    assert "Sample data" in text and "Unusual Whales API token: not set" in text
    assert "0 of sample" in text and "CAL-" in text
    assert '<th scope="row">Standing wants</th><td>2' in text


def test_datasets_say_the_source_behind_each(client: PageClient) -> None:
    text = client.get("/datasets", "admin").text
    assert text.count(">OPRA<") == 2 and ">FINRA TRF<" in text


def test_the_token_is_never_shown(tmp_path: Path) -> None:
    done = work(tmp_path, transport=Sample(), mode="live")
    done.api.use_token(TOKEN)
    read = connection_read(done)
    assert read.mode == "Live" and read.credentials[0].set
    assert TOKEN not in repr(read) and TOKEN not in repr(datasets_read(done))
    assert TOKEN not in repr(figures(done))


def test_without_a_token_the_mode_says_so(tmp_path: Path) -> None:
    done = work(tmp_path, mode="live")
    assert connection_read(done).mode == "No key"
    assert [f.value for f in figures(done)][0] == "No key"
