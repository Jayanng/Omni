# Compliance audit: Omni vs. Bitget AI Base Camp Hackathon S2

**Entry:** Track 2, Agentic Trading. Sub-theme: Cross-Asset Execution Agent.
**Audit date:** 2026-09-12 (revised). Earlier revisions of this file contained
stale numbers and self-assigned scores; both are removed. This file now states
requirements, what the repository does, and where the evidence lives.
**Standard:** the official S2 handbook (`bitget-ai.gitbook.io/bitgetai_hackathons2`),
read on 2026-09-11 and re-read on 2026-09-12.

No score is assigned here. Scoring is 50 percent quantitative and 50 percent
judge scoring per the handbook, and self-grading against a rubric we did not
write is not evidence. Readers should form their own view from
[evidence.md](evidence.md).

---

## Requirement 1: the LLM is the primary decision-maker

**Handbook:** the agent must sense the environment, judge independently, and
autonomously place orders with risk controls.

**Implementation:** `omni/llm.py` sends a compact structured state to
`deepseek-ai/DeepSeek-V4.1-Flash` and requires strict JSON back: one allowlisted
action, its parameters, a rationale and a confidence. The state includes the
session classification, the observed account snapshot, the modelled rToken
collateral (gross, haircut and its source, effective value) and the shocked
cross-asset results.

Deterministic code does not choose the action. It can veto or substitute, and
every proposal is recorded with the model name, latency, token usage, raw
response and the policy verdict. When both models fail, a rule-based decision is
used and labelled `used_fallback: true`, so a fallback can never be mistaken for
a model decision.

**Evidence:** `docs/evidence.md`, "Model layer". Live runs in
`logs/paper-log-*.jsonl` under `kind: decision`.

---

## Requirement 2: sub-theme fit, Cross-Asset Execution Agent

**Handbook:** how does the agent manage rToken and crypto positions
simultaneously? Example approach: hedge when rToken anomalies appear.

**Implementation:** `omni/risk.py` applies a shock per position derived from its
asset class: stock perpetuals take the equity gap shock, crypto perpetuals take
the crypto shock. Collateral is modelled separately from futures, and the
decision is driven by the interaction between the two. The neutralising trade is
a short on the stock perpetual mapped from the rToken symbol
(`RTOKEN_TO_STOCK_PERP` in `omni/config.py`).

**Limitation:** the account in this repository is a demo account and the rToken
leg is a declared portfolio file, because the demo venue cannot hold rTokens.
See [limitations.md](limitations.md) items 3 and 5.

---

## Requirement 3: paper or simulated trading acceptable

**Handbook:** teams are not expected to trade real capital; demo or paper
trading is acceptable.

**Implementation:** every order is a paper order on Bitget's demo environment
through the official Agent Hub CLI with `--paper-trading`. The rToken leg cannot
be executed there: the venue returns `papTradingService not support RWA order
validation error` and the dedicated reality order route 404s in demo scope.
rToken fills are therefore simulated against the real public order book and
labelled `simulated: true`. Execution on the futures leg is real paper
execution with an authoritative position readback.

**Evidence:** `docs/evidence.md`, "Venue boundaries".

---

## Requirement 4: paper trading log run during the competition period

**Handbook:** a machine-auditable paper trading log, run during the competition
period.

**Implementation:** `omni/ledger.py` writes day-scoped JSONL. Every record
carries timestamp, run id, kind and payload.

**Current state** (`python3 -m omni.cli report`, 2026-09-12):

| Metric | Value |
|---|---|
| Runs | 44 |
| Decisions | 18 |
| Executions completed | 10 |
| Blocked or refused | 3 |
| Policy overrides | 1 |
| Risk violations | 0 |
| Protective action share | 55.56% |
| Equity observations | 32 |
| Max drawdown | 5.04% |
| Sharpe | -0.54, not annualised |

**Honest note on duration:** the log begins 2026-09-11. The handbook recommends
at least two weeks and states that a 9/3 start meets the minimum. This entry
will hold roughly ten days by the 9/21 deadline, which is short of the
recommendation. The shortfall is stated rather than hidden.

**Honest note on Sharpe:** the value is negative and computed on a mostly flat
demo book. A defensive governor that correctly declines to trade produces a
near-zero-return series; the metric is reported as measured, not dressed up.

---

## Requirement 5: risk control layer

**Handbook:** robust risk controls preventing rogue actions.

**Implementation:** `omni/policy.py` and `omni/executor.py`.

- Allowlist: only `HOLD`, `HEDGE_STOCK_PERP`, `REDUCE_PERP`, `CLOSE_PERP` can reach execution.
- Hard vetoes: any proposal mentioning `WITHDRAW`, `TRANSFER_OUT`, `INCREASE_LEVERAGE`, `ADD_RISK`, `SET_LEVERAGE` or `ACCOUNT_MODE_CHANGE` is rejected with no substitution.
- Size cap: hedge notional is capped at the policy maximum (5,000 USDT by default, settable).
- Venue pre-clamp: before sending, size is clamped to the stricter of the instrument caps and the venue's own max-open-available answer, so limits are queried rather than discovered by rejection.
- Dry-run gate: every order is previewed before it is sent. Execution requires an explicit execute flag; the default is dry run.
- No funds path: no withdrawal or transfer function is implemented in the client at all.
- Forced minimum protection: when the modelled state is dangerous and the model chose to hold, deterministic policy substitutes the smallest protective action available.

**Evidence:** unit tests in `tests/test_engine.py`; live execution records in the ledger.

---

## Requirement 6: presentation

The console is a five-page instrument (overview, risk model, positions, audit
ledger, controls) styled after Denar's warm editorial language: cream canvas,
serif headings, mono data. No landing page, no marketing copy inside the tool.
Every displayed value comes from the API or config; missing data renders as an
em dash rather than a placeholder.

**Honest note:** an earlier version of this file described a different dark
theme and different page structure. That design has been replaced.

---

## System health at this revision

```text
Target                              Result    Detail
──────────────────────────────────────────────────────────────────────────
omni doctor                         13/13     reality endpoints, demo API, session
Unit suite (tests/)                 45/45     stdlib only, ~0.02s
Console routes                      all 200   5 pages, hash-routed, no landing page
Public data feeds                   pass      Reality states, stock info, calendar, ticker, book
Demo account read                   pass      effective equity and maintenance margin observed live
Paper order + readback              pass      futures leg only; rToken leg simulated and labelled
Policy violation rate               0.0%      across all recorded runs
Secrets                             pass      .env gitignored, mode 600, no secret in any log
```

---

## Outstanding before the 9/21 deadline

| Item | Status |
|---|---|
| Compliant X post (required, and entry point for the spread and fan-vote awards) | **Not published. Author action.** |
| Google Form submission with the full project description | **Not submitted. Author action.** |
| Qwen token subsidy form (optional, separate, 24h KYC review) | Not submitted. Author action. |
| Demo video | Not recorded. Optional but recommended by the handbook. |
| Paper log continuity | Running; keep the daily cycle going so the series grows. |

The X post and the form are the only true blockers: the handbook requires a
compliant X post link at submission and states that a repository link cannot
replace the project description field.

---

## Removed from earlier revisions

These claims appeared previously and were wrong or unsupported. They are listed
so a reader can see what was corrected:

- A self-assigned overall score and per-category 10/10 grades.
- "15% haircut" as the applied collateral ratio. The venue publishes 0.95
  discount for rNVDA at the demo tier, i.e. a 5% haircut, queried live.
- A test count of 31. The suite is 45.
- A description of the console as a dark Floor-style page. The console is now
  the five-page Denar-style instrument.
- A reference to a `walkthrough.md` that does not exist in this repository.
- Stale ledger figures (31 runs, 62.5% protective share).
