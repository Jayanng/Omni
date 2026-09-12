# Evidence ledger

Live-verified results. Every row was produced by an actual call on 2026-09-11 from this
repository against Bitget's production endpoints and demo (paper) environment.

Environment: Python 3.11.15, `@bitget-ai/bitget-agent-cli@3.0.0` driving
`bitget-agent-sdk`, credentials scoped to Bitget's **demo** environment.

## 1. Public production data

| Capability | Endpoint | Result |
|---|---|---|
| US session windows | `GET /api/v3/reality/market/states` | pass, returns pre_market 04:00-09:30, regular 09:30-16:00, after_hours 16:00-20:00 |
| Per-symbol rToken info | `GET /api/v3/reality/market/stock-info?symbol=RNVDAUSDT` | pass, `code=NVDA`, `tradingPeriod=[overnight,pre_market,regular,after_hours]`, `weekendTradable=yes` |
| Market calendar | `GET /api/v3/reality/market/calendar?code=NVDA` | pass, closure windows in EST |
| Dividends | `GET /api/v3/reality/market/dividends?code=NVDA` | pass, cash dividend with announcement, record, ex-rights and payment dates |
| Company overview | `GET /api/v3/reality/market/company-overview?code=NVDA` | pass, name, PE, PB, market cap, 52 week range |
| Valuation indicators | `GET /api/v3/reality/market/valuation-indicators?code=NVDA` | pass |
| Earnings forecast | `GET /api/v3/reality/market/earnings-forecast?code=NVDA` | pass |
| Share capital change | `GET /api/v3/reality/market/share-capital-change?code=NVDA` | pass |
| Suspension and resumption | `GET /api/v3/reality/market/suspension-resumption-info?code=NVDA` | pass |
| rToken ticker | `GET /api/v3/market/tickers?category=SPOT&symbol=RNVDAUSDT` | pass |
| rToken candles | `GET /api/v3/market/candles?category=SPOT&symbol=RNVDAUSDT&interval=1H` | pass |
| rToken order book depth | `GET /api/v3/market/orderbook?category=SPOT&symbol=RSPYUSDT` | pass, real bid and ask levels with sizes |

Important implementation detail discovered by probing: these public calls must **not** carry the
`paptrading` header. With the header present the demo service returns 404 for `reality/*` routes.

## 2. Demo (paper) account and execution

| Capability | Result |
|---|---|
| Credentials and environment | pass, demo scope (production calls return `exchange environment is incorrect`) |
| Account snapshot | pass, `effEquity`, `imr`, `mmr`, `mgnRatio`, per-asset balances |
| Account settings | pass, `accountMode=hybrid`, `assetMode=multi_assets`, `holdMode=hedge_mode` |
| Open positions | pass, normalized list with `total`, `avgPrice`, `markPrice`, `mmr`, `leverage`, `unrealisedPnl` |
| Crypto perpetual order | pass, filled and read back, then closed |
| **Stock perpetual order** | **pass, filled and read back** (`NVDAUSDT` market, `AAPLUSDT` limit) |
| Order dry run | pass, returns the exact would-send request without sending |
| High risk confirmation gate | pass, close requires an explicit confirm flag |
| Instrument metadata | pass, `symbolType=stock` identifies stock perpetuals in the demo universe |

## 3. rToken (RWA) execution: proven unavailable in demo

| Test | Result |
|---|---|
| `RNVDAUSDT` spot order | `40034 Parameter RNVDAUSDT does not exist` (not in the demo universe at all) |
| `RSPYUSDT` spot limit | `papTradingService not support RWA order validation error` |
| `RSPYUSDT` spot market | same RWA service error |
| `RGOOGLUSDT` spot limit | same RWA service error |
| lowercase `rSPYUSDT` | same RWA service error |
| strategy or trigger order on an rToken | rejected, the route is futures only |
| `POST /api/v3/trade/place-reality-order` (demo) | `40404 Request URL NOT FOUND`, route absent in the demo service |
| `GET /api/v3/account/reality-orderbook` (demo) | `40404 Request URL NOT FOUND` |
| `GET /api/v3/account/reality-fills` (demo) | `40404 Request URL NOT FOUND` |
| POST control with a bogus symbol | `40034 Parameter ... does not exist`, proving the probing method is valid |
| `POST /api/v3/trade/place-reality-order` (production) | `40099 exchange environment is incorrect`, the key is demo scoped |

The demo universe does list 12 rToken symbols with live quotes (RSPY, RQQQ, RGOOGL, RMU, RBILI,
RINCE, REQT, RECHO, RSOXL, RNVD and a test symbol), so the demo has rToken **market data** but no
rToken **order** support. This matches Bitget's own developer documentation, which states that
stock futures are live and rToken spot is on the roadmap.

## 4. Documented production path for rToken execution

From the Bitget UTA API documentation (`/docs/catalog/reality/trading`):

| Endpoint | Notes |
|---|---|
| `POST /api/v3/trade/place-reality-order` | params symbol, side, orderType, qty, category=SPOT, price, clientOid |
| `POST /api/v3/trade/cancel-reality-order` | |
| Permission | UTA trade (read and write) |
| Rate limit | 1/sec/UID, 30/sec/UID for whitelisted users |
| Reality order book and platform fills | whitelist required, apply through Bitget BD |

This is the path Omni would use for live rToken execution. It is not exercised here because it
requires a live account and real funds.

## 5. Venue-published risk parameters (added 2026-09-12)

Three Bitget endpoints publish the values the risk engine previously modelled.
Each was probed live and is now queried on every cycle through
`omni/venue_risk.py`, with the source string recorded in the ledger.

| Endpoint | CLI action | Observed result | Used for |
|---|---|---|---|
| `GET /api/v3/market/discount-rate` | `market --action discountRate` | per-coin tiered collateral ratios; `rNVDA` discountRate `0.95` for the `0` tier, `0.94` from 500,000 USDT, decreasing in tiers | the rToken haircut: `0.95` discount means a **5% haircut**, replacing the previous 15% fallback |
| `GET /api/v3/market/position-tier` | `market --action positionTier` | `NVDAUSDT` returns 11 bands, `mmr` 0.005 at tier 1 rising to 0.04, leverage 100 down to 15 | the official maintenance-margin ladder, and which tier a new hedge would graduate into |
| `GET /api/v3/account/max-open-available` | `order --action maxOpen` | for `NVDAUSDT` sell with an existing short: `maxSellOpen 0.15`, `maxBuyOpen 45.73`, `available 93863.40` | the pre-trade size clamp: the venue's own answer for additional size, folding in tiers, margin and open positions |

Behaviour when a read fails: the explicit input is used and the ledger records
the fallback source. No value is invented.

### Why this matters

The haircut moved from a guessed 15% to the venue's published 5% for rNVDA at
the demo tier. Every downstream buffer, loss percentage and risk-budget
comparison shifts with it. The change is recorded in the ledger per cycle as
`haircut_pct`, `haircut_source`, `haircut_input`, `mmr_tiers_source`,
`post_hedge_tier`, `venue_order_cap_qty` and `venue_max_sell_open`.

## 6. Exchange size limits

The demo venue enforces size limits that are **not** fully published in the
instrument metadata (`maxOrderQty` reports 52000 for `NVDAUSDT`):

| Size | Result |
|---|---|
| 10 contracts | accepted |
| 22 contracts | accepted |
| 45 contracts | rejected, `Order quantity cannot exceed the maximum for this level` |
| 54.43 contracts | rejected, same |

Two mitigations now exist and they are complementary:

1. **Pre-clamp (preferred).** Before sending, size is clamped to the stricter of
   the instrument caps and `max-open-available`, so the known limits are queried
   rather than discovered by rejection. A clamp is recorded as a
   `venue_pre_clamp` execution step.
2. **Halve-and-retry (defence in depth).** If a size rejection still comes back,
   the executor reduces and retries, logging every attempt. This covers limits
   the venue does not surface.

Both behaviours are visible in the paper log.

## 7. Agent and policy layer

| Capability | Result |
|---|---|
| LLM decision maker | pass, real calls to the configured model returning strict JSON |
| Decision rationale | pass, recorded verbatim in the ledger with model, latency and token usage |
| Prompt size control | the model receives a compact decision view (about 1.3 KB) while the full risk state, assumptions and narrative stay in the ledger. A bloated prompt on a reasoning model caused empty completions and a 77 second fallback; after trimming, the primary model answers in about 6 seconds with no fallback |
| Provider flakiness handling | implemented, retries with a larger budget then an optional secondary model |
| Deterministic fallback | implemented, used only when the model is unusable, and labelled `used_fallback: true` |
| Allowlist enforcement | pass, unit tested |
| Forbidden operation detection | pass, hard reject with no substitution, unit tested |
| Size cap | pass, logged as a policy check |
| Forced minimum protection | pass, a `HOLD` while risk needs attention is overridden and logged, unit tested |
| Closed market block | pass, hard reject when the venue is closed for the symbol, unit tested |
| Risk violation rate | 0 override events on model-proposed actions in the recorded runs |

### Note on the paper log

`logs/paper-log-*.jsonl` is append only and unedited. It contains the full working history,
including earlier cycles where venue size limits and model fallbacks were still being
discovered. Nothing was deleted to make the run look cleaner.

## 8. Unit tests

```text
Ran 52 tests - OK
```

Covers session classification (regular, pre-market, weekend tradable, weekend frozen, holiday),
collateral math and depth-aware fills, the shock engine (including per-position shocks and the
withheld liquidation figure), policy allowlist and veto semantics, venue parameter lookup and
tier selection, symbol mapping, and ledger metrics.

## 9. Hygiene

No live order, transfer or withdrawal was ever sent: every order in this
repository is a demo (paper) order.

The demo book is currently **open by design**, because the paper trading log
requires a live book to govern:

```text
open positions : BTCUSDT long 0.05, NVDAUSDT short 45.59
open orders    : 0
```

Probe orders created during capability testing were closed as they were
completed. The two positions above are the intentional demo book that the
governor monitors; they are demo balances, not real funds. See
[limitations.md](limitations.md) item 5 on the difference between this demo
book and a real account.
