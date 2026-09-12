# Submission package: Bitget AI Base Camp Hackathon S2

Everything needed to submit. The two items marked **author action** are the only
blockers; the rest is prepared and can be pasted.

Track: **Track 2, Agentic Trading**. Sub-theme: **Cross-Asset Execution Agent**.
Deadline: **2026-09-21, UTC+8**. Public vote: 2026-09-22 to 09-28.

Repository: https://github.com/Jayanng/Omni

---

## 1. Compliant X post (author action: post it, then paste the link in the form)

Requirements from the handbook: at least one compliant X post, and it is the
entry point for the Best Spread Award and the Fan Favorite vote. Include
`#BitgetHackathon` and tag `@Bitget_AI`, and introduce the product.

**Option A (263 chars)**

> I built an AI agent that keeps a Bitget unified account alive when tokenized US stocks and crypto run on different clocks. Crypto trades 24/7, the US equity market does not. Omni watches that gap and hedges it, and logs every decision. @Bitget_AI #BitgetHackathon

**Option B (266 chars)**

> Weekend problem: tokenized US stocks sit in my Bitget account as collateral, but the equity market is closed while crypto keeps moving. I built an agent that models that gap and hedges it before Monday. Real orders, every decision logged. @Bitget_AI #BitgetHackathon

**Option C (259 chars)**

> Tokenized US stocks trade while Wall Street sleeps, so the collateral moves and the hedge cannot. I built Omni: an agent that watches a Bitget unified account, models the weekend gap and hedges it, and keeps the whole trail in a ledger. @Bitget_AI #BitgetHackathon

Suggested attachment: `omni-teaser-1080p.mp4` (13s, rendered from real ledger
values) or a screenshot of the console.

Note on the Best Spread Award: it is judged on your own reach data across posts
made while building, and KOL or ghost-posted reach is excluded. A second and
third post during the window helps; substance beats frequency.

---

## 2. Google Form: Project Description

The handbook states that a repository link cannot replace the project
description field. Paste the text below.

### Part 1: Thesis

Tokenized US equities (Bitget rTokens) trade continuously and can be posted as
collateral in a Bitget Unified Trading Account, but the underlying cash equity
market closes 68% of the week. Crypto perpetuals keep moving while the equity
leg is frozen, so the collateral value and the instruments available to hedge it
run on two different clocks. A gap move in the underlying stock, priced into the
rToken over a weekend, can consume maintenance margin before the cash market
reopens to let anyone react. Omni is an agentic risk governor that watches that
gap, models the stressed margin state, and places a protective hedge on the
mapped stock perpetual while the gap is still open.

### Part 2: Target user and product value

The named user is a trader or small desk running a Bitget Unified Trading
Account with tokenized US equity collateral and open crypto perpetuals, who
cannot sit in front of the screen all weekend. Today the workaround is a manual
calendar reminder plus a mental estimate of how much a Monday gap would hurt.
That fails in three ways: the estimate is not stress tested, nobody is watching
at 3am, and when the move comes there is no record of why any decision was made.
Omni produces a structured risk state every cycle, has an LLM choose an action
under deterministic policy constraints, and records the whole chain, so the
operator gets monitoring, a bounded automatic response, and an audit trail.

### Part 3: Validation data and key metrics

From `python3 -m omni.cli report`, as of 2026-09-12. The log continues to grow
daily, so the live values should be read from that command at submission time.

| Metric | Value |
|---|---|
| Runs | 45 |
| Decisions | 18 |
| Executions completed | 10 |
| Policy overrides | 1 |
| Risk violations | 0 |
| Protective action share | 55.6% |
| Equity observations | 33 |
| Max drawdown | 5.05% |
| Sharpe | -0.53, not annualised |

The Sharpe figure is negative and reported as measured. A defensive governor on
a demo book holds most of the time, so the return series is nearly flat and the
ratio is close to zero by construction. We report it rather than dress it up.
The rToken haircut used in the model is not assumed: it is queried live from the
venue discount-rate schedule (0.95 discount, i.e. 5% haircut, for rNVDA at the
demo tier).

### Part 4: Progress

- Session classifier built on live Reality endpoints (market states, per-symbol
  trading periods, calendar), producing a regime, a liquidity tier and a mark
  confidence used by the risk model.
- Cross-asset shock engine with per-position shocks derived from asset class.
- LLM decision layer with strict JSON output, retries, a secondary model and a
  labelled deterministic fallback.
- Deterministic policy layer: allowlist, hard vetoes, size caps, forced minimum
  protection on breach, and no funds movement path at all.
- Executor with a dry-run gate, venue pre-clamp, halved retry and authoritative
  position readback.
- Five-page operator console.
- Continuous paper-trading log since 2026-09-11.

### Part 5: Deliverables

| Item | Location |
|---|---|
| Runnable demo | `demo/run_demo.sh`, `python3 -m omni.cli demo` |
| Event to decision to execution flow | seven-step cycle, reproduced in `evidence/demo-run-*.log` |
| Paper trading log | `logs/paper-log-*.jsonl` |
| Console | `python3 -m omni.cli ui` then open the printed URL |
| Evidence ledger | `docs/evidence.md` |
| Limitations | `docs/limitations.md` |
| Compliance audit | `docs/audit_report.md` |

### Part 6: View on AI trading (optional)

The interesting use of an LLM in a trading system is not forecasting. It is
operating under uncertainty with a record. A model that reads a structured risk
state and proposes an action it can explain is genuinely useful when a
deterministic rule would need a dozen brittle special cases. What it must not do
is bypass controls, so the design here keeps the model as the decision maker and
puts an independent deterministic layer between that decision and the order
book. The part that makes it trustworthy is not the model quality, it is that
every proposal, veto, override and readback is on the record and can be
audited afterwards.

### Role of the LLM

`deepseek-ai/DeepSeek-V4.1-Flash` is the primary decision maker and receives a
compact structured state. `zai-org/GLM-5.3-Flash` is the secondary model used
automatically when the primary returns an unusable completion. Deterministic
policy is used only when both fail, and is labelled `used_fallback: true`. Qwen
credits: the project does not claim Qwen usage; the Qwen subsidy form is a
separate optional application.

### Other form fields

| Field | Value |
|---|---|
| Submission Materials Link | https://github.com/Jayanng/Omni |
| X Promotional Post Link | paste the Option A/B/C post URL after posting |
| Track to Sub-theme | Agentic Trading, Cross-Asset Execution Agent |
| University Name | leave blank unless a university entry is intended |
| Apply for Demo Day | optional, author decision |
| Apply for K3 Token Subsidy | optional, author decision |

---

## 3. Qwen token subsidy (separate form, optional)

Application is separate from the main form. The handbook says Bitget reviews KYC
every 24 hours and the first 300 teams that apply and pass KYC may receive
30 USDT-equivalent Qwen Token credits. Requires KYC, so it is an author action.

---

## 4. Demo video (optional, recommended)

Not required by the handbook for Track 2, but the form asks for submission
materials and a short recording strengthens the entry. Suggested 75 seconds:
open the console, show the two clocks, run one governance cycle, show the
decision and policy verdict appearing, then show the new ledger record. No
editing needed; an unedited proof moment is stronger than a polished cut.

---

## 5. Honesty notes to keep in the submission

These must not be dropped to make the entry look stronger:

- The account is Bitget's demo environment. No live order, transfer or
  withdrawal was ever sent.
- rToken spot execution is not claimed: the demo venue rejects RWA orders, so
  rToken fills are simulated against the real public order book and labelled
  `simulated`.
- The rToken holdings come from a declared portfolio file, because the demo
  account cannot hold rTokens.
- The paper log begins 2026-09-11, so it holds roughly ten days at the deadline,
  short of the two-week recommendation.
- No guarantee of liquidation avoidance is claimed. No alpha or profitability is
  claimed.
