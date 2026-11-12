# Changelog

## 0.3.0

On open-meridian 0.36.0, contract 30, on core aae501d's harness (chart
0.1.538); `meridian` 0.1.60 in the check. What the plugin records is
unchanged.

- **Unusual Whales' terms in words** (ruling 1032): each dataset's
  `licence_default` is gone, and `terms_and_pricing` names the source behind
  it (OPRA, or FINRA's trade reporting facilities on the consolidated tape)
  and what Unusual Whales' public pages say of its API: plans and trials,
  personal use, data kept for personal or internal purposes after a
  subscription ends, no redistribution without its licence, a delayed
  service by arrangement, not affiliated. Shown on Data sources and in the
  Datasets page's row details (the page's own default-terms line is gone).
  The licence a deployment admin sets is the one enforced.
- **How a gap is recovered** (`gap_recovery`): the two tapes `stream_only`
  (the REST tape serves the latest trading day alone), `options` `none` (a
  chain is served as it stands now).
- **Off-exchange prints in the FINRA facilities' hours**
  (`sessions_calendar_id`, ruling 455): `off_exchange` names the platform's
  FINRA Trade Reporting Facilities operating hours
  (`CAL-01M5TTQCH5NTYF33970T8GVF1D`, 04:00 to 20:00 New York). OPRA's hours
  across its exchanges are no calendar the platform curates yet.
- **Row keys checked against the lake's rule 5** (ruled 2026-11-12): an
  option print is keyed by Unusual Whales' trade ID and an off-exchange
  print by its symbol and tracking ID, each valid at its trade time, a
  cancellation the same key's next version, `cancelled`. **Two cases change
  valid time:** an option series' open interest or volume is keyed by its
  series, its day and its kind (the SDK's `helpers.statistic`) but valid
  from when the plugin read it, so a value read again later the same day
  restates the key under another valid time; and a series' terms
  (`helpers.option_series`) are keyed by its OCC symbol but valid from when
  read, so terms that change restate under another valid time. Neither has
  a cancellation; listed for step 3d, unchanged.
- e2e: core lists the option tape with its terms in words and its gap
  recovered by the stream only.
- `meridian plugin migrate --to 0.36.0` moved the pins (the base by digest,
  `meridian` 0.1.60); its `licence-default-left` findings done by hand.
- Core's runtime and harness images at `aae501d`, by digest.

## 0.2.0

open-meridian 0.35.2 (each role one class; rulings 1003 to 1005 and 1009 to
1029), contract v29, on core v29's harness.

- **The pins:** open-meridian 0.33.4 to 0.35.2, plugin-python:0.35.2 by tag
  and digest, meridian 0.1.57 in the check, and the e2e's runtime and
  harness at core 1ae36f0 (contract v29) by digest.
- **One class for its role:** the work (`Work`) is the data role's class,
  its acts made on itself; `__main__.Lake` adds the settings applied as
  delivered and, in its `run`, the standing wants kept current, the
  licences read and the health said each minute and the latency reported,
  registered with `meridian.run`, which restarts it after a backoff should
  it stop (the plugin no longer exits to be restarted). The raw answers are
  tended from the settings as delivered (`RawStore.tend(settings=...)`).
- **Each row once** through the SDK's `SentRows`, in place of its own copy.
- **The suite at contract v29:** a derived series and a pool's factor
  named not presented, with why.
- **The e2e's reader** is two role classes, `reporting` and `signal`, on
  `meridian.run_async`.

## 0.1.2

SDK 0.33.4: raw-record writes and enum conversion fixes (ruling 937).

- **The pins:** open-meridian 0.33.3 to 0.33.4, and plugin-python:0.33.4 by tag
  and digest (`meridian plugin migrate --to 0.33.4`: only the pins move).

## 0.1.1

Bug fixes (ruling 926), until the SDK's own pacing, retry and allowance
helpers replace them (924).

- **Standing wants are budgeted against the plan's allowance:** what is
  left of the day's share (`x-uw-token-req-limit` less
  `x-uw-daily-req-count`), less a tenth kept for wants asked now, is spread
  evenly until the count resets at 20:00 New York; each standing read's
  requests put the next back by their share, the longest unread first, and
  once the share is spent standing reads wait for the reset. Until the
  count has been seen to reset, the allowance is taken as a month's
  (Options Starter's) and a 31st of it is spent a day, so it lasts the
  month. Connection's **Allowance** says what the budget allows. Wants
  asked now are never held back.
- **A 429 is waited out:** as `Retry-After` asks, else until the API's
  minute resets (`x-uw-req-per-minute-reset`), else after 1, 2 then 4
  seconds with jitter; at most three times, each counted, and only then is
  the read failed. Before, the first 429 failed it.
- Not in this version: the option prints' exchange resolved to a venue by
  its MIC (a follow-up).

## 0.1.0

The first version: Unusual Whales' public API as a data plugin, on
open-meridian 0.33.3 (contract v28). Rulings 903 and 904.

- Three datasets, vendor Unusual Whales, keys proposed: `options` (an
  underlying's chain: series as the listed-option template's fields, open
  interest and volume per trading date), `option_trades` (the option tape,
  each print with the NBBO in force at it) and `off_exchange` (an equity's
  prints reported to FINRA's facilities); each licence default Unusual
  Whales' public API terms as read (kept, one person's, display, derived
  data internal only, redistribution by licence only).
- Series keyed by their 21-character OCC symbols under the underlying,
  never minted or resolved; open interest dated the market day before it is
  read and volume the session's, by the platform's US equity calendar.
- Prints' conditions converted to the platform's characteristics and
  eligibilities by OPRA's and the tape plans' rules, or kept as reported;
  Unusual Whales' inferred side never recorded as the aggressor.
- Standing wants kept current by reading the API: a chain every five
  minutes, prints every 30 seconds, in market hours.
- The deployment's Unusual Whales API token: one secret setting, sent to the
  API as a bearer token and nowhere else.
- Sample data: made-up contracts and prints in the API's documented shape.
  No token in tests or e2e.
- The data role's Connection and Datasets pages and tools; the data suite;
  the e2e on the plugin harness of core 8def82a; meridian 0.1.53.
