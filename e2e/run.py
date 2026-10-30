"""`make e2e`: the plugin on the plugin harness of the runtime it pins
(contract v28), beside `reader`, a reporting and signal plugin (e2e/reader.py) entitled to
its datasets, and the harness's admin. Run from the repository's root by the
Makefile, which builds the image and writes the harness's plugins first;
standard library only. The harness's stand-in for the platform mints SPY's
record by the FIGI the Makefile names (HARNESS_PLATFORM_MINTS), invented for
the e2e.

No Unusual Whales token is used: the API answers nowhere (the e2e's hosts
file), and sample data answers from made-up contracts and prints committed
with the plugin.

1. No token, the API unreachable: Connection says "No key", and nothing is
   recorded.
2. Sample data on (a developer's setting, accepted on the harness).
3. Parity: through the deployment's MCP, `read_connection` and
   `read_datasets` answer what the pages show -- the token not set, three
   datasets, the source behind each -- and core's `dashboard__list_datasets`
   lists the three as the catalogue declares them.
4. Licensed and entitled at the Data sources page: the reader is entitled to
   the three.
5. The option tape: the reader's read of SPY's prints of 29 October 2026 is
   asked of the plugin, which records them under SPY with each series' key:
   the regular print at 12.10 with the NBBO in force (bid 12.05) and its
   time, no aggressor; the sweep, the leg of a complex order; the cancelled
   print as cancelled.
6. Off-exchange: the same day's off-exchange prints, the odd lot recorded
   as an odd lot that may not set the high and low.
7. The chain: SPY's series expiring 20 November 2026, read from the lake's
   listing after the plugin records the chain: four standard series, keyed
   by their 21-character OCC symbols, with their terms.
8. `store lake`: the plugin's rows and wants as the lake holds them.
"""

import json
import os
import subprocess
import sys
import time

PROJECT = "unusual-whales-e2e"
LOG = ".e2e/runner.log"
COMPONENTS = ".e2e/components.log"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", ".e2e/harness/compose.yaml",
           "-f", ".e2e/harness/plugins.yaml", "-f", "e2e/plugin.yaml"]
INSTANCE = "unusual-whales"
KEYS = ["options", "option_trades", "off_exchange"]
DATASETS = [f"{INSTANCE}:{key}" for key in KEYS]
OPTIONS, TAPE, OFF = DATASETS
#: 29 October 2026, 10:00 to 20:00 UTC: the sample's day, its early off-exchange print in it.
FROM_NS = 1_793_268_000 * 10**9
UNTIL_NS = 1_793_304_000 * 10**9


class Failed(Exception):
    pass


def log(text):
    with open(LOG, "a", encoding="utf-8") as kept:
        kept.write(text + "\n")


def compose(*args, check=True, timeout=600):
    done = subprocess.run(COMPOSE + list(args), capture_output=True, text=True,
                          timeout=timeout)
    log(f"$ compose {' '.join(args)[:300]}\n{done.stdout[-4000:]}{done.stderr[-2000:]}")
    if check and done.returncode != 0:
        raise Failed(f"compose {' '.join(args)[:200]}: {(done.stdout + done.stderr).strip()[-600:]}")
    return done


def runner(*args, check=True):
    done = compose("run", "--rm", "-T", "runner", *args, check=check)
    return done.stdout if check else done


def must(condition, why):
    if not condition:
        raise Failed(why)


def until(seconds, attempt, what):
    deadline = time.monotonic() + seconds
    last = None
    while True:
        try:
            answer = attempt()
        except Failed as failed:
            answer, last = None, failed
        if answer:
            return answer
        if time.monotonic() > deadline:
            raise Failed(f"{what}, in {seconds} seconds" + (f": {last}" if last else ""))
        time.sleep(2)


def page(instance, level, path):
    said = runner("page", "--instance", instance, "--level", level, path)
    status, _, body = said.partition("\n")
    must(status.strip() == "200", f"{instance} {path} answered {said[-600:]}")
    return body


def call(tool, arguments=None):
    done = runner("mcp", "call", tool, json.dumps(arguments or {}), check=False)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        raise Failed(f"{tool}: no answer: {(done.stdout + done.stderr)[-400:]}")
    must(answer.get("outcome") in ("read", "unchanged"), f"{tool} answered {done.stdout[-700:]}")
    return answer["data"]


def store_lake():
    return compose("run", "--rm", "-T", "store", "lake").stdout


def reader(path):
    return json.loads(page("reader", "read", path))


def trades_of(spy, dataset, series):
    def attempt():
        read = reader(f"/trades?subject={spy}&dataset={dataset}&from={FROM_NS}&until={UNTIL_NS}"
                      f"&series={series}")
        return read if len(read["trades"]) >= 7 else None
    return until(90, attempt, f"the prints of {dataset} were not read")["trades"]


def run():
    started = time.time()
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    compose("up", "-d")
    runner("ready")
    runner("ready", "--instance", "reader")

    # 1. No token, the API unreachable.
    runner("page", "--level", "admin", "/", "--until", "No key", "--seconds", "90")
    lake = store_lake()
    must("row|" not in lake, f"step 1, nothing recorded without a token: {lake[-500:]}")

    # 2. Sample data.
    runner("settings", "sample_data=true")
    runner("page", "--level", "admin", "/", "--until", "Sample data", "--seconds", "120")

    # 3. Parity through the deployment's MCP, and core's view of the catalogue.
    runner("grant", "--level", "admin")
    runner("mcp", "connect", "--covers", "deployment_admin", "--covers", f"{INSTANCE}:admin")
    tools = runner("mcp", "list").split()
    read_connection = next((t for t in tools if t.endswith("read_connection")), "")
    read_datasets = next((t for t in tools if t.endswith("read_datasets")), "")
    must(read_connection and read_datasets, f"step 3, the plugin's two tools are listed: {tools}")
    connection = call(read_connection)
    must(connection["mode"] == "Sample data"
         and connection["credentials"] == [{"label": "Unusual Whales API token", "set": False}],
         f"step 3, read_connection: {connection}")
    datasets = call(read_datasets)
    must([s["dataset"] for s in datasets["served"]] == DATASETS
         and [b["short"] for b in datasets["behind"]] == ["OPRA", "OPRA", "FINRA TRF"],
         f"step 3, read_datasets: {datasets}")
    shown = page(INSTANCE, "admin", "/datasets")
    must(shown.count(">OPRA<") == 2 and ">FINRA TRF<" in shown,
         "step 3, Datasets shows what read_datasets answers")
    listed = {d["dataset"]: d for d in call("dashboard__list_datasets")["datasets"]}
    must(all(d in listed for d in DATASETS), f"step 3, core lists the three datasets: {list(listed)}")
    entry = listed[TAPE].get("catalogue_entry", {})
    must(entry.get("modes") == ["pull", "stream"] and entry.get("day_time_zone") == "America/New_York",
         f"step 3, core lists {TAPE} as declared: {listed[TAPE]}")

    # 4. Licensed and entitled.
    for dataset in DATASETS:
        runner("licence", dataset, "kept=true", "retention_days=0", "derived_use=false",
               "display=true", "personal_use=true",
               "note=Unusual Whales' public API terms: personal use, kept, displayed.")
        runner("entitle", "--instance", "reader", dataset, "note=The e2e's reader reads them.")
    runner("grant", "--instance", "reader", "--level", "read")
    spy = reader("/resolve")["spy"]
    must(spy.startswith("INS-"), f"step 4, SPY's record is the platform's: {spy}")

    # 5. The option tape, wanted of the plugin and read back.
    tape = trades_of(spy, TAPE, "all")
    by_key = {t["row_key"][-1]: t for t in tape}
    regular = by_key["1"]
    must(regular["series_key"] == ["SPY   261120C00580000"] and regular["price"] in ("12.10", "12.1")
         and regular["bid"] in ("12.05",) and regular["quote_time"] > 0
         and regular["aggressor"] == "AGGRESSOR_UNSPECIFIED" and regular["dataset"] == TAPE,
         f"step 5, the regular print with its NBBO and no aggressor: {regular}")
    must(by_key["2"]["characteristics"] == ["TRADE_CHARACTERISTIC_INTERMARKET_SWEEP"]
         and by_key["3"]["characteristics"] == ["TRADE_CHARACTERISTIC_MULTI_LEG"]
         and by_key["7"]["cancelled"] is True,
         f"step 5, a sweep, a leg and a cancelled print: {tape}")

    # 6. Off-exchange prints.
    off = trades_of(spy, OFF, "")
    odd = [t for t in off if t["quantity"] == "37"]
    must(odd and odd[0]["characteristics"] == ["TRADE_CHARACTERISTIC_ODD_LOT"]
         and odd[0]["high_low"] == "ELIGIBLE_NOT_ELIGIBLE" and not odd[0]["series_key"],
         f"step 6, the odd lot: {off}")

    # 7. The chain.
    chain = until(90, lambda: (lambda c: c if len(c["series"]) == 4 else None)(
        reader(f"/chain?subject={spy}&expiration=2026-11-20")),
        "step 7, SPY's series of 20 November were not read")
    keys = sorted(s["key"][0] for s in chain["series"])
    must(keys == ["SPY   261120C00580000", "SPY   261120C00590000", "SPY   261120P00570000",
                  "SPY   261120P00580000"]
         and all(s["fields"]["exercise_style"] == "EXERCISE_STYLE_AMERICAN" for s in chain["series"]),
         f"step 7, four standard series with their terms: {chain}")

    # 8. The lake as it holds them.
    lake = store_lake()
    must(f"|{TAPE}|" in lake and f"|{OFF}|" in lake and f"|{OPTIONS}|" in lake,
         f"step 8, the lake holds the plugin's rows: {lake[-800:]}")

    print(f"e2e OK in {int(time.time() - started)}s on the plugin harness: no token said on "
          f"Connection and nothing recorded; sample data; read_connection and read_datasets "
          f"answering what the pages show, core listing the three datasets as declared; licensed "
          f"and entitled; SPY's option prints of 29 October wanted and recorded under SPY with "
          f"their series' keys, the NBBO at each print and no aggressor, a sweep, a leg and a "
          f"cancelled print; the off-exchange odd lot; and SPY's four standard series of 20 "
          f"November read from the lake's listing")


def main():
    os.makedirs(".e2e", exist_ok=True)
    open(LOG, "w").close()
    try:
        run()
    except (Failed, subprocess.TimeoutExpired, KeyError, ValueError, IndexError, TypeError) as failed:
        with open(COMPONENTS, "a", encoding="utf-8") as kept:
            kept.write(compose("logs", "--no-color", check=False).stdout)
        compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
        print(f"e2e FAILED: {failed}; the runner's log is in {LOG}, the components' in {COMPONENTS}",
              file=sys.stderr)
        return 1
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
