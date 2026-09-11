# Omni

**A cross-asset risk governor for a Bitget Unified Trading Account.**

Omni keeps a UTA alive when tokenized US stocks (rToken) are posted as collateral and crypto
perpetual positions keep moving while the underlying US cash equity market is closed.

> **Status:** working prototype, live-verified against Bitget's production data and demo
> (paper) environment on 2026-09-11. See [docs/evidence.md](docs/evidence.md) for the raw
> results and [docs/limitations.md](docs/limitations.md) for what is deliberately not claimed.

---

## The problem

Bitget's own support material describes the trap:

- During weekends and US market holidays, stock-token index prices can be fixed while crypto
  futures PnL and account risk continue updating in real time.
- Stock tokens used as margin are counted at a **collateral-ratio-adjusted** value, not gross value.
- Liquidation begins when the account margin ratio falls below the maintenance margin rate.
- A US market reopen gap can move the collateral haircut in one print.

So a trader can do everything right and still wake up liquidated, because:

```text
rToken mark looks frozen          ->  "my collateral is fine"
crypto perp PnL keeps moving      ->  margin ratio quietly deteriorates
Monday cash open gaps the equity  ->  collateral value drops in one print
human was asleep                  ->  no one executed the protective action
```

The tools that exist today do not close that loop inside Bitget. Playbook strategies, GetAgent
surfaces and generic trading agents optimise for entry signals. None of them treat an rToken
holding as **living margin** that can kill the account.

## What Omni does

Omni is an agent that does not try to beat NVDA. It tries to make sure the account is still
there on Monday.

```text
event intake         session regime, holiday windows, corporate actions      (live Bitget data)
market data          rToken marks, candles, real order book depth           (live Bitget data)
collateral model     haircut-adjusted effective collateral + stressed exits  (explicit scenario)
account read         effective equity, maintenance margin, open positions    (live demo account)
risk engine          cross-asset shock -> buffer, margin ratio, risk budget  (deterministic)
agent decision       LLM chooses one allowlisted action                      (model + logged)
policy layer         allowlist, size caps, forced minimum protection         (deterministic)
execution            dry run -> explicit paper order -> authoritative readback (real API calls)
evidence log         every input, decision, veto and fill, as JSONL           (auditable)
```

### The action space is deliberately narrow

| Action | Meaning |
|---|---|
| `HOLD` | No market action |
| `HEDGE_STOCK_PERP` | Short the mapped stock perpetual to neutralise rToken collateral gap risk |
| `REDUCE_PERP` | Partially reduce an existing crypto perpetual position |
| `CLOSE_PERP` | Close an existing crypto perpetual position |

Withdrawals, transfers, leverage changes and any new risk are **not implemented** in the
executor. The agent is structurally incapable of moving funds out of the account.

## Why this is Bitget-native

The product only exists because one account object holds all of these at once:

- rToken spot collateral
- crypto perpetuals
- a Unified Trading Account margin engine
- 24/7 crypto markets against a closed cash equity market
- an execution surface an agent can drive

Other venues tokenize stocks and other venues let you post them as collateral. Neither is the
same object. Omni's claim is narrow and defensible: it is a **Bitget-native cross-asset survival
agent**, not a generic risk dashboard.

## Quickstart

Requirements: Python 3.11+ (standard library only) and the official Bitget Agent Hub CLI.

```bash
# 1. Agent Hub CLI (the official Bitget surface Omni drives)
npm install -g @bitget-ai/bitget-agent-cli@3.0.0

# 2. credentials: create a Bitget DEMO API key, then
cat > .env <<'EOF'
BITGET_API_KEY=your-demo-key
BITGET_SECRET_KEY=your-demo-secret
BITGET_PASSPHRASE=your-demo-passphrase
OMNI_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
OMNI_LLM_API_KEY=your-llm-key
OMNI_LLM_MODEL=deepseek-ai/DeepSeek-V4.1-Flash
OMNI_LLM_FALLBACK_MODEL=zai-org/GLM-5.3-Flash
EOF
chmod 600 .env

# 3. verify every live dependency
python3 -m omni.cli doctor

# 4. run the full demo (event -> decision -> execution)
./demo/run_demo.sh

# 5. read the paper metrics
python3 -m omni.cli report
```

Or step through it manually:

```bash
python3 -m omni.cli status
python3 -m omni.cli setup --setup-symbol BTCUSDT --setup-qty 2   # demo book
python3 -m omni.cli demo --rtoken-shock -0.08 --crypto-shock -0.25
python3 -m omni.cli flatten
python3 -m omni.cli report
python3 -m unittest discover -s tests
```

## Example output

Taken verbatim from `evidence/demo-run-2026-09-11.log`, run A of `demo/run_demo.sh`.

```text
=== 1. event intake: session and calendar ===
  regime=pre_market liquidity=thin mark_confidence=medium weekend_tradable=True
  underlying code=NVDA trading_periods=overnight,pre_market,regular,after_hours
  corporate actions observed: 20

=== 3. account state ===
  effective equity=96,124.77 USDT, open futures positions=1
  hedge instrument for RNVDAUSDT: NVDAUSDT
    BTCUSDT long notional=153,985.60 asset_class=crypto shock=-25.0%

=== 4. rToken collateral stress and margin model ===
  modelled rToken gross        : 110,135.00 USDT
  haircut applied              : 15.0%
  effective collateral         : 93,614.75 USDT
  scenario rToken / crypto     : -8.0% / -25.0%
  shocked buffer               : 142,160.33 USDT
  breach                       : False
  Scenario consumes 24.4% of account equity, above the 10% risk budget.
  simulated rToken exit (labelled simulated): RNVDAUSDT 500 @ 202.57
    slippage 805.0 bps, fee 50.64 USDT

=== 5. agent decision (LLM is the decision maker) ===
  model=deepseek-ai/DeepSeek-V4.1-Flash fallback=False latency=4953ms
  action=HEDGE_STOCK_PERP params={"symbol": "NVDAUSDT", "notional_usdt": 110135.0}
  rationale: RNVDA rToken collateral (110,135 USDT gross, 93,614.75 after 15% haircut)
             carries unhedged NVDA price exposure while the cash equity market is closed
             and liquidity is thin. The -8% rToken / -25% crypto scenario models a 24.4%
             loss of equity, well above the 10% risk budget ...

=== 6. policy layer (allowlist, caps, forced protection) ===
  approved=True action=HEDGE_STOCK_PERP override=False
    check ok : action HEDGE_STOCK_PERP is allowlisted
    check ok : hedge notional capped to policy maximum 5,000 USDT

=== 7. execution: dry run then explicit order then readback ===
  executed=True reason=short 22.68 NVDAUSDT to neutralise rToken collateral gap risk
    step dry_run: ok=True endpoint=POST /api/v3/trade/place-order
    step execute: ok=True endpoint=POST /api/v3/trade/place-order
    readback: BTCUSDT long total=2 mark=76992.8
    readback: NVDAUSDT short total=22.68 mark=220.82
```

Run B of the same script shows the risk control layer hardening a model decision: the model
chose `HOLD`, the policy layer overrode it to `HEDGE_STOCK_PERP` because the modelled loss
exceeded the risk budget, and the executor placed a 21.98 contract hedge.

Latest paper metrics (`omni report`):

```text
decisions 12, executions_completed 9, blocked_or_refused 2,
policy_overrides 1, risk_violation_count 0, risk_violation_rate 0.0,
protective_action_share 0.75, max_drawdown_pct 0.04525,
sharpe not reported: 11 equity observations, minimum 20 required
```

## Repository layout

```text
omni/
  config.py         environment, allowlist, forbidden operations
  bitget_public.py  public production data (Reality session, stock info, dividends, marks, depth)
  bitget_demo.py    private demo account access through the official Agent Hub CLI
  session.py        session regime, liquidity tier and mark confidence
  collateral.py     haircut-adjusted collateral and depth-aware simulated fills
  risk.py           deterministic cross-asset shock and margin engine
  llm.py            LLM decision layer with retries and a deterministic fallback
  policy.py         allowlist, caps, hard vetoes and forced minimum protection
  executor.py       dry run, execution, venue size-limit adaptation, readback
  ledger.py         JSONL evidence ledger
  metrics.py        paper metrics computed from the ledger
  cli.py            doctor, status, decide, demo, setup, flatten, report
demo/
  run_demo.sh            the full end-to-end sequence
  portfolio.example.json large declared rToken book
  portfolio.small.json   right sized book
tests/
  test_engine.py         31 stdlib unit tests
tools/
  review_scan.py         unused import, long line and tab scan
  llm_latency_probe.py   measures model latency and fallback rate in isolation
docs/
  problem.md         the problem in detail
  architecture.md    module map, trust boundaries, data flow
  evidence.md        live-verified capability ledger
  compliance.md      requirement matrix for the hackathon tracks
  limitations.md     what is not claimed, and why
logs/
  paper-log-*.jsonl  the paper trading log
evidence/
  demo-run-*.log     console evidence of a complete run
```

## Honest boundaries

- The risk engine is a **scenario model**, not Bitget's official margin or liquidation engine.
- The rToken collateral ratio (haircut) is an **explicit input**, because Bitget does not
  publish an account-specific ratio through the Agent Hub surface.
- Bitget's demo service **does not support rToken (RWA) order execution**. rToken positions are
  therefore valued from live production data with fills simulated against the real order book,
  and every such fill is labelled `simulated`. Execution is real paper execution on the futures
  leg. See [docs/evidence.md](docs/evidence.md) for the proving tests.
- Omni does not claim to guarantee that an account avoids liquidation. It claims to model the
  risk, act early under an explicit scenario, and log everything.

## License

MIT. See [LICENSE](LICENSE).
