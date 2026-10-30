"""What this version declares beside its role, `data` (W8.1, W4.1): its
settings, its catalogue and its storage, built from code and used twice --
`__main__` registers with them, and `meridian plugin upload` reads them from
the built image (declaration.py puts them together with the pages and the
documentation).

**The catalogue: three datasets** (keys proposed with 0.1.0, ruling 903):

- `options`: an underlying's option chain as Unusual Whales lists it --
  each series' terms (`meridian.v1.ListedSeries`) and its open interest and
  volume per trading date (`meridian.v1.Statistic`), from
  `/api/stock/{ticker}/option-contracts`. Pulled for a want, a standing
  want's chain read again every five minutes while US option markets are
  open. OPRA's data, through Unusual Whales; the open interest is the
  clearing house's count, which OPRA carries each morning. Its trading
  dates follow the platform's US equity calendar. Never its quotes: the
  chain's NBBO carries no quote time (the trade's time stands in for it),
  so no quote row is made from it; the NBBO in force at each print travels
  on the print (`option_trades`).
- `option_trades`: each option print of an underlying (`meridian.v1.Trade`,
  with `quote_at_trade`), keyed under the underlying by its series, from
  `/api/option-trades`: the latest trading day's prints, pulled for a want
  of a range within it and read every 30 seconds for a standing want while
  the session is open. OPRA's tape, through Unusual Whales.
- `off_exchange`: an equity's prints reported to FINRA's trade-reporting
  facilities (`meridian.v1.Trade`, with `quote_at_trade`), from
  `/api/darkpool/{ticker}`, pulled and kept current the same way, from 04:00
  to 20:00 New York. The consolidated tape's off-exchange prints, through
  Unusual Whales; labelled off-exchange, never "dark pool".

Each `vendor` is Unusual Whales, whose terms a deployment takes the data
under; the source behind each -- OPRA, and FINRA's trade-reporting
facilities on the consolidated tape -- is declared on each dataset once the
SDK carries `underlying_source` (ruling 896, which ruling 387 named), and is
said in docs/terms.md meanwhile. Real time: Unusual Whales' 15-minute
delayed plans are arranged with its sales team, and would be datasets of
their own (ruling 382), not declared here.

Unusual Whales' own figures -- its flow alerts, net premium ticks, market
tide, greek exposure and levels, max pain, IV rank, unusualness -- are not
declared: the lake has no kind for a publisher's derived figure (a derived
series is a `signal` plugin's own, never a publisher's), so they wait for
one (docs/overview.md says which).

**Each licence default** is what Unusual Whales' public pages say of its
API, which the deployment's licence confirms or replaces on Data sources --
never whether a deployment meets them: kept, for personal or internal use,
also after a subscription ends; one person's (the API is sold "strictly for
personal use"); displayed to its holder; derived data for internal use
only, since the pages say nothing more of it; redistribution only under a
redistribution licence from Unusual Whales; not affiliated.

**Storage**: one kind of raw record, the API's answers as received (never
the token), a month by default.

**Settings**, in the data role's order: no environment (the API has one),
the credential -- the deployment's Unusual Whales API token, secret -- and
sample data, a developer's.
"""

from __future__ import annotations

import meridian
from meridian import DatasetDeclaration, DatasetLicence, RecordKind

VENDOR = "Unusual Whales"
OPTIONS, OPTION_TRADES, OFF_EXCHANGE = "options", "option_trades", "off_exchange"
KEYS = (OPTIONS, OPTION_TRADES, OFF_EXCHANGE)
SERIES, STATISTIC, TRADE = "meridian.v1.ListedSeries", "meridian.v1.Statistic", "meridian.v1.Trade"
QUOTE_AT_TRADE = "meridian.v1.Trade.quote_at_trade"
API_TOKEN, SAMPLE_DATA = "api_token", "sample_data"
#: New York's day, ending at the 16:00 close.
DAY_TIME_ZONE = "America/New_York"
DAY_END_MINUTE = 16 * 60
#: A standing want's chain read again at most this often, in seconds.
CHAIN_CADENCE_SECONDS = 300
#: A standing want's prints read again at most this often, in seconds.
TAPE_CADENCE_SECONDS = 30
#: The platform's US equity venues (NYSE markets) calendar, the one
#: plugin-tradier's option chains name (ruling 768): an option's trading
#: dates are the days it says US equity markets are open.
US_EQUITY_CALENDAR = "CAL-01M4VF0F4XGP3RATCCSKDPZSBP"
#: Real time: no declared delay.
DECLARED_DELAY_NS = 0
#: The REST tape serves the latest trading day only; a chain the latest.
HISTORY_DAYS = 0

#: Its one kind of raw record, the API's answers as received.
KIND = "responses"
LABEL = "Raw responses"
WINDOW_DAYS = 30
RESPONSES_KIND = RecordKind(KIND, LABEL, window_days=WINDOW_DAYS)

#: Who stands behind each dataset's values (ruling 387), until the SDK
#: declares it (ruling 896).
UNDERLYING_SOURCE = {
    OPTIONS: "OPRA (the Options Price Reporting Authority), through Unusual Whales",
    OPTION_TRADES: "OPRA (the Options Price Reporting Authority), through Unusual Whales",
    OFF_EXCHANGE: (
        "FINRA's trade reporting facilities, on the consolidated tape (CTA and UTP plans), "
        "through Unusual Whales"
    ),
}

NOT_AFFILIATED = (
    "Unusual Whales is a trademark of its owner. This plugin is not affiliated with or "
    "endorsed by Unusual Whales."
)
LICENCE = DatasetLicence(
    kept=True,
    derived_use=False,
    derived_use_terms="internal_only",
    display=True,
    personal_use=True,
    redistribution="licence_required",
    not_affiliated_notice=NOT_AFFILIATED,
)


@meridian.settings
class Config:
    """The settings, in the data role's order: the credential, then sample
    data."""

    api_token: str = meridian.setting(
        "Unusual Whales API token",
        secret=True,
        description=(
            "The deployment's Unusual Whales API token, from its API dashboard. Every request "
            "asks for it, sent as a bearer token and nowhere else. Its plan sets what it "
            "serves and how many requests a day or a month it may make."
        ),
    )
    sample_data: bool = meridian.sample_data(
        description=(
            "Answer from made-up option contracts and prints in the API's documented shape, "
            "committed with the plugin, instead of calling Unusual Whales. No token needed. "
            "Development deployments only."
        )
    )


def _tape(key: str) -> DatasetDeclaration:
    return DatasetDeclaration(
        key=key,
        vendor=VENDOR,
        data_types=[TRADE, QUOTE_AT_TRADE],
        modes=["pull", "stream"],
        cadence=TAPE_CADENCE_SECONDS,
        history=HISTORY_DAYS,
        licence_default=LICENCE,
        day_time_zone=DAY_TIME_ZONE,
        day_end_minute=DAY_END_MINUTE,
        calendar_id=US_EQUITY_CALENDAR,
        declared_delay_ns=DECLARED_DELAY_NS,
    )


CATALOGUE = [
    DatasetDeclaration(
        key=OPTIONS,
        vendor=VENDOR,
        data_types=[SERIES, STATISTIC],
        modes=["pull"],
        cadence=CHAIN_CADENCE_SECONDS,
        history=HISTORY_DAYS,
        licence_default=LICENCE,
        day_time_zone=DAY_TIME_ZONE,
        day_end_minute=DAY_END_MINUTE,
        calendar_id=US_EQUITY_CALENDAR,
        declared_delay_ns=DECLARED_DELAY_NS,
    ),
    _tape(OPTION_TRADES),
    _tape(OFF_EXCHANGE),
]
