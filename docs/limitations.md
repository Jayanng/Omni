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

It then applies user-supplied scenario shocks. It does **not** reproduce Bitget's official
liquidation engine, does not know the venue's account-specific collateral schedule, and does not
model funding, fees inside the shock, or partial liquidation mechanics.

Consequence: every "buffer", "liquidation shock" and "time to breach" style number is conditional
on the stated inputs. The model withholds the liquidation-shock figure entirely when the rToken
leg alone cannot plausibly drive the buffer to zero.

## 2. The rToken collateral ratio is an input, not an observation

Bitget does not publish an account-specific rToken collateral ratio through the Agent Hub
surface. Omni therefore requires the ratio as an explicit parameter (`--haircut`, default 15%)
and prints its source in the run output and the ledger. A different ratio produces different
results, and that is the intended behaviour: the assumption is visible and adjustable.

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

## 7. Venue size limits are discovered, not documented

The demo exchange enforces per-order and position-tier caps that are not published in the
instrument metadata (`maxOrderQty` reports a much larger number than the venue accepts). The
executor adapts by reducing size and retrying, and it logs every attempt. This makes the agent
resilient but it does mean an order may execute smaller than the recommendation.

## 8. Not claimed

- No guarantee that an account avoids liquidation.
- No claim to be first of a kind. The claim is narrow and qualified: within the public Bitget
  documentation, Agent Hub surface and adjacent tokenized-equity venues reviewed for this work,
  no direct implementation was found combining Bitget rToken collateral, cross-account crypto
  exposure, session-change risk and allowlisted protective execution.
- No claim of profitability or alpha. Omni is not a return-seeking strategy.
- No claim that Bitget's published session clocks are authoritative for daylight saving. The
  registers are interpreted as New York local time, and that interpretation is recorded as an
  assumption in every session state.
