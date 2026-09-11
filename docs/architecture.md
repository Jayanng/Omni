# Architecture

## Module map

```text
                         PUBLIC PRODUCTION DATA (no auth)
  ┌──────────────────────────────────────────────────────────────────────┐
  │ bitget_public.py                                                     │
  │   reality/market/states         session windows                      │
  │   reality/market/stock-info     trading periods, weekendTradable     │
  │   reality/market/calendar       holiday and closure windows          │
  │   reality/market/dividends      corporate actions                    │
  │   market/tickers               rToken marks                          │
  │   market/candles               rToken reference series               │
  │   market/orderbook             real rToken depth                     │
  └──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  session.py ──► regime, liquidity tier, mark confidence
                                    │
  collateral.py ──► haircut-adjusted collateral, depth-aware simulated fills
                                    │
  ┌──────────────────────────────────────────────────────────────────────┐
  │ DEMO (PAPER) ACCOUNT                                                 │
  │ bitget_demo.py  ->  official Bitget Agent Hub CLI (`bgc`)            │
  │   account overview, positions, open orders       (reads)             │
  │   place order, close position                    (writes, demo only) │
  └──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  risk.py ──► deterministic cross-asset shock model
                                    │
                                    ▼
  llm.py ──► LLM chooses ONE allowlisted action (recorded with rationale)
                                    │
                                    ▼
  policy.py ──► allowlist, caps, hard vetoes, forced minimum protection
                                    │
                                    ▼
  executor.py ──► dry run -> explicit paper order -> venue size adaptation -> readback
                                    │
                                    ▼
  ledger.py ──► JSONL evidence log        metrics.py ──► paper metrics
```

## Why the Agent Hub CLI is the private surface

Omni drives the **official Bitget Agent Hub CLI** for every private account call instead of
hand-rolling signatures. That choice is deliberate:

- it is Bitget's supported developer surface, so a judge can reproduce the calls;
- it already implements the safety gates the agent needs (`--dry-run`, `--read-only`,
  `--confirm`, `--paper-trading`);
- it keeps credentials out of the repository, because the CLI reads them from the environment.

`OMNI_BGC` can point at a locally installed binary. Otherwise Omni falls back to the pinned
`npx --yes @bitget-ai/bitget-agent-cli@3.0.0`.

## Trust boundaries

| Boundary | Rule |
|---|---|
| Model proposals | Never executed before policy validation. The model cannot name a symbol outside the allowlisted actionable set, exceed the size cap, or request a transfer. |
| Forbidden operations | `WITHDRAW`, `TRANSFER_OUT`, `INCREASE_LEVERAGE`, `ADD_RISK`, `SET_LEVERAGE`, `ACCOUNT_MODE_CHANGE` are scanned for in the action **and** in the parameters. A hit is a hard reject with no substitution. |
| Closed market | A hedge proposal while the venue is closed for the symbol is a hard reject. Doing nothing is the correct answer. |
| Write path | Every write is a dry run first, then an explicit order, then an authoritative readback from the exchange. |
| Funds path | Withdrawal and transfer operations are not implemented in the executor at all. |
| Secrets | Never written to the ledger, never printed, never committed. `.env` is gitignored and mode 600. |

## Data flow for one cycle

```text
1  event intake        stock-info + market states + calendar        -> session regime
2  market data         tickers + order book                         -> marks + depth
3  account read        account overview + positions                 -> equity, maintenance, book
4  risk model          scenario shocks + haircut                    -> buffer, ratio, loss, verdict
5  agent decision      structured risk state -> LLM                 -> action + rationale
6  policy              action + params + state                      -> approved / vetoed / overridden
7  execution           dry run -> order -> retry on size limit      -> orderId + readback
8  evidence            every step above                             -> JSONL
```

## Shock model

The identity used is stated in the code and repeated in every recorded risk state:

```text
total_equity   = observed demo effective equity + modelled rToken net collateral
maintenance    = sum over futures positions of (abs(notional) * mmr)
margin_ratio   = maintenance / total_equity
buffer         = total_equity - maintenance
```

Each futures position carries **its own scenario shock**:

- a **stock** perpetual moves with the equity gap (so a short hedge offsets the rToken leg);
- a **crypto** perpetual moves with the crypto shock.

Applying one shock to the whole book would misprice the cross-asset position, which is exactly
the error the agent exists to avoid.

The model also withholds the "liquidation shock" figure when the rToken leg alone cannot
plausibly drive the buffer to zero, and says so instead of publishing a meaningless number.

## Action semantics

| Action | Execution meaning |
|---|---|
| `HEDGE_STOCK_PERP` | Market short on the mapped stock perpetual, sized from the recommended notional, capped by policy, then reduced and retried if the venue rejects the size |
| `REDUCE_PERP` | Close a named perpetual position in the demo account (dry run, then confirmed) |
| `CLOSE_PERP` | Same path, full close |
| `HOLD` | No market action; recorded with the reason |

## Paper versus simulated

| Leg | Treatment | Labelling |
|---|---|---|
| Crypto perpetuals | Real paper orders, real fills, real readback | `executed: true` |
| Stock perpetuals | Real paper orders, real fills, real readback | `executed: true` |
| rToken spot | Live production price and depth, fills simulated against the real book | `simulated: true` |

This split exists because Bitget's demo service rejects RWA orders outright. The proving tests
are recorded in [evidence.md](evidence.md). No output of this repository presents a simulated
rToken fill as an executed exchange fill.
