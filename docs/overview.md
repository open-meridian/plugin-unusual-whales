# Overview

Unusual Whales serves US options and equity market data through its API:
option chains, the full options tape with the NBBO at each print, equity
prints reported off exchange, and many figures of its own computed from
them. This plugin reads the API with your deployment's API token and puts
the market data into your deployment's lake.

It is a data plugin: its first-use path, its two pages and its Summary figures are every data plugin's, described once on [Using a data plugin](https://open-meridian.dev/how-to/using-a-data-plugin/). These sections cover what is Unusual Whales' own.

## Its datasets

| Dataset | What it holds | Behind it |
|---|---|---|
| `options` | An underlying's option chain: each series' terms, its open interest and its volume per trading date | OPRA, through Unusual Whales |
| `option_trades` | Each option print, with the NBBO in force when it printed | OPRA, through Unusual Whales |
| `off_exchange` | An equity's prints reported to FINRA's trade-reporting facilities, with the NBBO in force | FINRA's facilities on the consolidated tape, through Unusual Whales |

## The chain

- **Each series** is recorded under its underlying, keyed by its OCC symbol
  padded to 21 characters (`SPY   261120C00580000`), with its terms: put or
  call, strike, expiration, American exercise and physical settlement, 100
  shares of the underlying per contract. A series gets a record of its own
  only when a reader asks for one.
- **Open interest** read on a day is the clearing house's count at the end
  of the market day before it, and is dated that day; **volume** is the
  session's, dated today once the session has opened. Market days are the
  platform's US equity calendar's. A value Unusual Whales leaves empty is
  no row, never a zero.
- **Not recorded:** an index's chain (its terms, European and cash-settled,
  are not stated), and an adjusted contract (its deliverable is not stated).
  The chain's bid and ask are not recorded as quotes: Unusual Whales gives
  them no quote time.

## The prints

- **Each option print** is recorded under its underlying with its series'
  key, its price and size, and the NBBO in force when it printed with each
  side's size and time. Its conditions become the platform's trade
  characteristics -- a sweep, a leg of a complex order, a leg tied to a
  stock trade, a floor trade, a cross, an auction, a late report -- and say
  which statistics it may set, as OPRA's rules have them. A condition with
  no conversion is kept as Unusual Whales stated it.
- **Never a side.** Unusual Whales tags each print bid side, ask side, mid
  or no side: its own comparison of the price with the NBBO. That is an
  inferred side, not the side that took liquidity, so it is not recorded
  as one.
- **Each off-exchange print** is recorded under the equity with its
  conditions converted by the consolidated tape plans' rules (an odd lot or
  an average-price trade never sets the high or the low), the facility's
  report time beside its execution time, and the market centre's code as
  stated. These prints are labelled off-exchange.
- A cancelled print is recorded again as cancelled, the next version of its
  row.

## When values arrive

- **A want:** the chain, or the latest trading day's prints within the
  range asked, read when the lake asks. Unusual Whales' tape serves the
  latest trading day only: a range before it is beyond history.
- **Kept current:** while a reader keeps a standing want, the plugin reads
  the chain every five minutes and the prints every 30 seconds, in market
  hours (09:30 to 16:15 New York for options, 04:00 to 20:00 for
  off-exchange prints). It reads the API; it does not hold Unusual Whales'
  WebSocket open.

## What it does not do

- It shows no price, print or figure on its own pages: values are read by
  the plugins that use them.
- It records none of Unusual Whales' own figures -- its flow alerts, net
  premium, market tide, greek exposure and levels, max pain, IV rank,
  volume unusualness and the like. They are Unusual Whales' computations,
  and the lake has no kind for a publisher's figure yet; your deployment's
  own measures compute the same things from the prints and the chain.
- It never infers a side, groups prints into sweeps or scores activity.
