# Limitations: what Omni does not claim

Written to be read by a sceptical reviewer. If a number or a claim is not listed as verified in
[evidence.md](evidence.md), treat it as not established.

## 1. The risk engine is a scenario model, not Bitget's engine

Omni computes:

```text
total_equity = observed demo effective equity + modelled rToken net collateral
maintenance  = sum over futures positions of (abs(notional) * mmr)
margin_ratio = maintenance / total_equity
buffer       = total_equity - maintenance
```

**Partially resolved (2026-09-12):** the maintenance-margin inputs are now
venue-sourced. `/api/v3/market/position-tier` returns the official per-symbol
tier ladder (notional band -> MMR and leverage cap), recorded in every cycle
ledger record as `mmr_tiers_source`, and the cycle records which tier a new
hedge would graduate into (`post_hedge_tier`). The per-position `mmr` the
account API reports is used as-is.

**Also resolved (2026-09-12): the scenario shocks are no longer constants.**
They are derived each cycle from the stressed instrument's own realised candle
history (a lower-tail quantile of daily close-to-close returns), and the method,
sample size, interval, lookback and endpoint are recorded in every cycle under
`scenario_provenance`. Observed on 2026-09-12: rToken `-3.35%`, crypto
`-2.36%`, replacing the previous fixed `-4%` / `-6%`.

**Fail-toward-caution rule.** When a live read fails the model does not invent a
value: an unreadable haircut means collateral is treated as unusable rather than
guessed, an underivable shock stops the cycle rather than producing a stress
result built on a guess, and an unmapped rToken refuses to hedge rather than
shorting a guessed instrument.

The model still does **not** reproduce Bitget's full liquidation engine, its
account-specific collateral schedule beyond the published discount-rate ladder,
or funding, fees inside the shock, or partial liquidation mechanics.

Consequence: every "buffer", "liquidation shock" and "time to breach" style
number is conditional on the stated inputs. The model withholds the
liquidation-shock figure entirely when the rToken leg alone cannot plausibly
drive the buffer to zero.

## 2. The rToken collateral ratio is an input, not an observation

**Resolved (2026-09-12).** Bitget publishes per-coin, per-tier collateral
ratios at `/api/v3/market/discount-rate` (the agent CLI exposes it as
`market --action discountRate`). The cycle now queries it live for the
portfolio's rToken coin, selects the tier by the holding's USD value, and uses
the venue's haircut instead of the previous explicit default. For rNVDA at the
demo holding (~109K USDT) the venue discount rate is 0.95, i.e. a **5%
haircut**, where the previous default input was 15%. The value and its source
are recorded in every cycle record (`haircut_pct`, `haircut_source`,
`haircut_verified`). The `--haircut` flag is now an explicit operator override
only; it is never used silently as a fallback. If the venue read fails and no
override is set, the collateral is treated as unusable (the cautious direction)
and `haircut_verified` is false. The engine no longer guesses this number.

Remaining nuance: the discount-rate ladder is the venue's published schedule
for margin counting; an account-specific custom-collateral configuration could
differ, and the demo `coinConfigList` is empty, so per-account confirmation is
still not observable in demo scope.

## 3. rToken fills are simulated, and labelled

Bitget's demo service rejects rToken (RWA) orders. Proving tests are recorded in
[evidence.md](evidence.md), including the dedicated Reality order route returning 404 in demo
scope and the regular route returning `papTradingService not support RWA order validation error`.

Therefore:

- rToken **valuation** uses live production prices, candles and real order-book depth;
- rToken **fills** are simulated against that real book and marked `simulated: true`;
- rToken **execution is not claimed**.

Execution is real paper execution on crypto and stock perpetuals, which the demo does accept.

## 4. No live-money verification

Every order in this repository was a paper order in Bitget's demo environment. No live order,
transfer or withdrawal was ever sent. The documented live path for rToken execution
(`/api/v3/trade/place-reality-order`) is described but not exercised, because it requires a live
account and real funds.

## 5. The demo account is not the user's real book

The demo account's balances are venue-provided test balances. The rToken holdings come from a
**declared portfolio file** (`demo/portfolio.example.json`), because the demo account cannot hold
rTokens. This is stated in the repository, in the run output and in the ledger, so nobody can
mistake a demo balance sheet for a real one.

## 6. Metrics are thin, and that is stated

- Sharpe is not reported below 20 equity observations. The metrics function says so explicitly.
- A defensive governor trades rarely, so win rate is reported as the share of decisions that
  produced an executed protective action, not as a trade hit rate.
- Max drawdown is computed from the recorded paper equity series only.

## 7. Venue size limits are queried, not discovered by rejection

**Resolved (2026-09-12).** Before any hedge order is sized, the executor now
queries three venue answers and pre-clamps to the smallest: the instrument
metadata (`maxOrderQty` / `maxMarketOrderQty` via
`market --action instruments`), and the venue-computed maximum additional open
size for the account and side (`/api/v3/account/max-open-available`, exposed as
`order --action maxOpen`), which already folds in position tiers, margin
availability and existing positions. A clamp is recorded as an explicit
`venue_pre_clamp` execution step. The halve-and-retry path remains as a
defence in depth for limits the venue does not surface, so an order may still
execute smaller than the recommendation in those rare cases, but the known
limits are now queried upfront.

## 8. What is still assumed, and why

Market inputs are live or venue-published. The following are not market data and
are declared rather than derived:

- **rToken quantities.** The demo account cannot hold rTokens, so holdings come
  from the declared portfolio file. Prices, candles, order-book depth and the
  collateral ratio are all live; the quantity is declared. Stated in the run
  output and the ledger. Replaced by real balances on a live account.
- **rToken spot fee rate** (0.05%): a published Bitget constant, cited in
  `config.py`, not a market reading.
- **Risk policy inputs** (attention threshold, risk budget, hedge cap): declared
  configuration, overridable by env, recorded in every cycle record. These are
  policy choices by definition, not observations.
- **Session clock interpretation:** Bitget publishes window clocks with timeZone
  "EST"; they are interpreted as New York local time so daylight saving is
  handled by the tz database rather than hardcoded. Recorded as an assumption in
  every session state.
- **Hedge ratio:** the neutralising size is the rToken gross notional, which
  assumes the mapped perpetual tracks the rToken one-for-one. A beta adjustment
  is not modelled. Stated here so the sizing is not mistaken for a fitted model.

## 9. Not claimed

- No guarantee that an account avoids liquidation.
- No claim to be first of a kind. The claim is narrow and qualified: within the public Bitget
  documentation, Agent Hub surface and adjacent tokenized-equity venues reviewed for this work,
  no direct implementation was found combining Bitget rToken collateral, cross-account crypto
  exposure, session-change risk and allowlisted protective execution.
- No claim of profitability or alpha. Omni is not a return-seeking strategy.
- No claim that Bitget's published session clocks are authoritative for daylight saving. The
  registers are interpreted as New York local time, and that interpretation is recorded as an
  assumption in every session state.
