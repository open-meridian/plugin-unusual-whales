# Troubleshooting

## Connection

| What you see | What it means | What to do |
|---|---|---|
| **No key** | No API token is set: every request would be refused | Enter the token in Settings |
| Last error: *refused the request (401)* | The API did not accept the token, or it is missing | Check the token on your Unusual Whales API dashboard, and enter it again |
| Last error: *refused the token for this request (403: ...)* | The token's plan does not serve that request; the code names the entitlement | `historic_data_access_missing`: a date past the plan's history; `advanced_tier_required`: an Advanced endpoint |
| Last error: *limiting this token's requests (429)* | The plan's allowance or a limit was reached | Fewer standing wants, or a plan with more requests |
| **Allowance** near its limit | The day's (or month's) requests are nearly spent | Fewer standing wants; the count resets at 20:00 New York, or with the billing month on Starter |
| Standing wants: *Calendar* not read | The deployment answered no US equity calendar | Pull the calendar from the platform; until then no statistic is dated |
| **Not answering** | The API could not be reached | Check the deployment's outbound access to api.unusualwhales.com |

## Wants and datasets

| What you see | What it means | What to do |
|---|---|---|
| Declined, *not covered* | The record has no symbol, is an index, or Unusual Whales holds nothing for it | Give the record a symbol, or read another source |
| Declined, *source silent* | The API answered nothing: no token, a refusal, or no print in the range | See Connection's last error |
| Declined, *beyond history* | The range ends before the latest trading day, the only day the tape serves | Read it from a source that keeps history |
| No open interest or volume | The calendar was not read, or the session has not opened | See Connection's Standing wants |
| Datasets: **Not licensed yet** | No deployment admin has licensed the dataset | Ask a deployment admin to license it on Data sources |
