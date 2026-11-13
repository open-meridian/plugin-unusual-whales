# plugin-unusual-whales

Unusual Whales' options flow and market data for
[Open Meridian](https://open-meridian.com), as a data plugin: the Unusual
Whales API, read with your deployment's API token, into your deployment's
lake.

| Dataset | What it holds | Behind it |
|---|---|---|
| `options` | An underlying's option chain: each series' terms, its open interest and volume per trading date | OPRA |
| `option_trades` | Each option print, with the NBBO in force when it printed | OPRA |
| `off_exchange` | An equity's prints reported to FINRA's trade-reporting facilities | FINRA TRF, on the consolidated tape |

**An API token is needed.** Unusual Whales' API plans (Options Starter,
Basic, Advanced) each have a free trial. The token is a secret setting: sent
to the API alone, never logged or shown. Unusual Whales' terms are your
deployment's to settle with Unusual Whales: each dataset describes them in
words on the Data sources page (contract 30), and
[docs/terms.md](docs/terms.md) says the same.

It records market data, never Unusual Whales' own figures (flow alerts, net
premium, greek exposure, max pain and the like), and never an inferred side.

**A row key fixes its valid time** (spec/the-lake rule 5; open-meridian
0.36.3): an option series' open interest and volume are valid from the start
of the market day they describe, in New York, never when they were read, so
a re-read restates the value alone. A series' terms keep their key's first
valid time and first underlying, held across restarts in the plugin's
storage (`series.json`, beside its raw records, through the SDK's
`option_chains.SeriesTimes`); a series the lake already holds under
another first valid time is taken as recorded, said once, and one asked
under another underlying than its first is skipped and counted.

The documentation the plugin ships with -- overview, setup, pages,
troubleshooting and terms -- is in [docs/](docs/README.md); `AGENTS.md` is
for whoever works on it next.

## Develop

    make ci-remote     # lint and the tests, in a container
    make check         # meridian plugin check --verified --run-tests
    make e2e           # the plugin on the plugin harness, on sample data
    make preview       # the pages on sample data, in preview/

Every gate runs in a container; plugins land CI-first, through a pull
request.

Apache-2.0. Unusual Whales is a trademark of its owner; this project is not
affiliated with or endorsed by Unusual Whales.
