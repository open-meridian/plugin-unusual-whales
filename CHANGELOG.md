# Changelog

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
