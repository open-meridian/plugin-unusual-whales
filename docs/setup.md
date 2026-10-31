# Setup

## The API token

Every request to the Unusual Whales API asks for a token, sent as a bearer
token. It comes from your Unusual Whales account's API dashboard, under an
API plan your organisation chooses. Unusual Whales' public API page lists:

- **API Options Starter:** 25,000 requests per billing month (50,000 a
  month on an annual plan), one year of history.
- **API Basic** and **API Advanced:** a daily request allowance, two years
  of history; Advanced adds the CME futures tape.

Its pricing page has the current prices and a free trial. The plugin works
with whatever the token's plan serves; a request the plan does not serve is
refused, and Connection says so with the entitlement Unusual Whales names.

**Mind the allowance.** A standing want of prints costs about two requests a
minute per underlying in market hours, a chain one call per 500 contracts
every five minutes. Only answers that succeed count toward the allowance,
and every token of the account shares it. Connection shows the allowance and
the count as the API last stated them, and what the budget allows: the
plugin spreads what is left of the day's share evenly until the count resets
at 20:00 New York, keeping a tenth for wants asked now, and slows its
standing reads to fit. Until it has seen the count reset, it takes the
allowance as a month's (Options Starter's) and spends a 31st of it a day.

## Launching it

1. Launch the plugin and approve its one role, `data` (a data plugin).
2. In the dashboard's Settings form, enter the **Unusual Whales API token**.
   It is a secret setting: no page, tool or log shows it, and the plugin
   sends it to api.unusualwhales.com alone.
3. Its other settings: **Raw responses window** and **past the window**
   (the SDK's), how long the API's answers are kept in the plugin's storage,
   a month by default; and **Sample data**, on a deployment installed for
   development only: made-up option contracts and prints in the API's
   shape, committed with the plugin, in place of the API. No token needed.

## Its datasets

On the deployment's **Data sources** page (deployment admins):

1. **License** `<instance>:options`, `<instance>:option_trades` and
   `<instance>:off_exchange`. Each catalogue default is what Unusual Whales'
   public pages say of its API: kept, for one person's use, displayed,
   derived data for internal use, redistribution only under a licence from
   Unusual Whales. Confirm it, or set your own, with a note saying why.
2. **Entitle** each plugin that reads them, such as your options analytics.
3. **Priority**, where another plugin records the same chain or tape: put
   the one your readers should read first.

## The underlyings

A want names an underlying by its record; the plugin reads the record's
`symbol` and asks Unusual Whales for that ticker. Where the symbol is
another source's, the plugin reports Unusual Whales' beside it, so the
record gains it. A record with no symbol is declined, not covered.
