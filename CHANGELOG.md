# Changelog

## 0.1.2 (2026-10-30)

SDK 0.33.4: raw-record writes and enum conversion fixes (ruling 937).

- **The pins:** open-meridian 0.33.3 to 0.33.4, and plugin-python:0.33.4 by tag
  and digest (`meridian plugin migrate --to 0.33.4`: only the pins move).

## 0.1.1 (2026-10-30)

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
