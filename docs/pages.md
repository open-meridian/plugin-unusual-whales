# Pages

Both pages are the data role's, the same on every data plugin, under
**Manage**, for the plugin's admins. Neither shows a price, a print or a
figure. Each is also a read tool on the deployment's MCP, answering what the
page shows, under the same names on every data plugin.

## Connection (`read_connection`)

How the plugin reaches the Unusual Whales API:

- **Key:** the mode (Live, No key or Sample data) and whether the API token
  is set -- never its value;
- **Limits and use:** the plan's limits, the requests made, the last call
  and the last error; and **Allowance**, the plan's request allowance and
  the count toward it as the API last stated them, with what is left for
  standing wants until the count resets;
- **Stream:** **Standing wants**, how many it keeps current; its `…` opens
  the reading passes, the calendar its trading dates follow (or why it was
  not read) and the last error.

## Datasets (`read_datasets`)

What the plugin serves:

- **Served:** its three datasets as the deployment's catalogue lists them,
  with the terms each declares and whether a deployment admin has licensed
  it, what it recorded and declined; and **Behind**: the source behind each
  dataset's values, OPRA or FINRA's facilities, in full on hover;
- **Wants:** the standing wants it keeps current, and the last wants it
  answered; **Subjects**.
