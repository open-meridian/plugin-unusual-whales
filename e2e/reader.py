"""A reading plugin for the e2e, on the Python SDK: the deployment's view of
what this plugin recorded, as a `reporting` and `signal` plugin entitled to its datasets
reads it (W10.6). Not the plugin, and never shipped: the e2e runs it from
this directory in the plugin's own image, which carries the SDK.

It answers its page as JSON, so the harness's runner can read it
(`page --instance reader --level read PATH`):

  /resolve
      SPY's record, resolved by the FIGI the Makefile's mints name and
      Unusual Whales' symbol;
  /trades?subject=ID&dataset=D&from=NS&until=NS
      one read of trades over a range, every series of the subject's: each
      trade's row key, series key, price, quantity, aggressor, whether
      cancelled, its characteristics and its quote at the print; and what
      the lake left unanswered, with why;
  /chain?subject=ID&expiration=D&dataset=D
      an underlying's series for one expiration (`chains.read_chain`): each
      series' key and terms.

Standard library and the SDK only; every value stays text, never a float.
"""

import asyncio
import http.server
import json
import threading
import urllib.parse

import meridian
from meridian import Interface, Page, SourceChoice
from meridian.helpers import chains
from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import reporting, signal

PORT = 8088
LOOP = asyncio.new_event_loop()
ASKED = [
    ops.Identifier(scheme="figi", value="BBG00E2ESPY1"),
    ops.Identifier(scheme="symbol", value="SPY", source="unusual_whales"),
]


def money(held):
    return str(as_decimal(held.amount)) if held.HasField("amount") else ""


def trade_json(trade):
    quote = trade.quote_at_trade
    return {
        "dataset": trade.meta.source.dataset,
        "row_key": trade.meta.row_key,
        "series_key": [k.value for k in trade.meta.series_key],
        "price": money(trade.price),
        "quantity": str(as_decimal(trade.quantity)),
        "aggressor": ops.Aggressor.Name(trade.aggressor),
        "cancelled": trade.cancelled,
        "characteristics": [ops.TradeCharacteristic.Name(c) for c in trade.attributes.characteristics],
        "high_low": ops.Eligible.Name(trade.attributes.consolidated.high_low),
        "bid": money(quote.bid) if trade.HasField("quote_at_trade") and quote.HasField("bid") else "",
        "quote_time": quote.source_time_ns if trade.HasField("quote_at_trade") else 0,
    }


def unanswered(answer):
    return [{"subject": u.subject.entity_id, "dataset": u.dataset,
             "reason": ops.UnansweredReason.Name(u.reason)} for u in answer.unanswered]


class Reporting(reporting.Role):
    """`reporting`: names SPY by its identifiers."""


class Signal(signal.Role):
    """`signal`: reads trades and an underlying's series, which `reporting`
    does not."""


class Reader:
    """What the stand-in answers, through its role classes (SDK 0.35: each
    role one class, its acts made through it). It hears nothing: each read
    is asked when the runner asks."""

    def __init__(self):
        self.reporting = Reporting()
        self.signal = Signal()
        self.spy = ""

    async def resolve(self):
        if not self.spy:
            found = await self.reporting.resolve_identifier(
                identifiers=ASKED, stated_description="SPDR S&P 500 ETF Trust", stated_currency="USD")
            if not found.instrument_id:
                raise RuntimeError(f"SPY did not resolve: {found}")
            self.spy = found.instrument_id
        return {"spy": self.spy}

    async def trades(self, query):
        one = lambda name: query.get(name, [""])[0]  # noqa: E731
        answer = await self.signal.list_trades(
            subjects=[meridian.SubjectRef(entity_id=one("subject"))],
            sources=SourceChoice(named=[one("dataset")]),
            valid_from_ns=int(one("from") or 0), valid_until_ns=int(one("until") or 0),
            all_series=one("series") == "all")
        return {"trades": [trade_json(t) for t in answer.trades], "unanswered": unanswered(answer)}

    async def chain(self, query):
        one = lambda name: query.get(name, [""])[0]  # noqa: E731
        series = await chains.read_chain(self.signal, one("subject"), one("expiration"))
        return {"series": [
            {"key": [k.value for k in s.meta.series_key],
             "dataset": s.meta.source.dataset,
             "fields": {f.path: f.value for f in s.fields}}
            for s in series]}

    async def answer(self, path, query):
        if path == "/resolve":
            return await self.resolve()
        if path == "/trades":
            return await self.trades(query)
        if path == "/chain":
            return await self.chain(query)
        return {"page": "the e2e's reader"}


def serve(reader):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            future = asyncio.run_coroutine_threadsafe(
                reader.answer(parsed.path, urllib.parse.parse_qs(parsed.query)), LOOP)
            try:
                body, status = json.dumps(future.result(timeout=60), sort_keys=True), 200
            except Exception as failed:  # said on the page, for the run to quote
                body, status = json.dumps({"failed": f"{type(failed).__name__}: {failed}"}), 500
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


#: What the stand-in registers, its whole declaration (contract v25): the
#: e2e prints it with meridian-declaration and the harness holds the
#: stand-in's registration to it.
DECLARATION = meridian.Declaration(
    interface=Interface(PORT, "The e2e's reader", pages=[Page("/", "Prints", levels=["read"], roles=["reporting", "signal"])])
)


def main():
    reader = Reader()
    threading.Thread(target=serve, args=(reader,), daemon=True).start()
    # SDK 0.35: its role classes registered on one connection, until the
    # harness stops it.
    LOOP.run_until_complete(meridian.run_async(
        declaration=DECLARATION, roles=[reader.reporting, reader.signal]))


if __name__ == "__main__":
    asyncio.set_event_loop(LOOP)
    main()
