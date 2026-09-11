# Compliance: Bitget AI Base Camp Hackathon S2

Source: the official S2 handbook (`bitget-ai.gitbook.io/bitgetai_hackathons2`), rendered and
quoted on 2026-09-11.

Entry: **Track 2, Agentic Trading**, sub-theme **Cross-Asset Execution Agent**.

## Why this track and sub-theme

| Handbook line | Omni |
|---|---|
| "The LLM is the primary trading decision-maker, not just an assistant. The Agent must sense the environment, make independent judgments, and autonomously place orders with risk controls." | The LLM senses a structured risk state and chooses one action; deterministic policy enforces risk controls; the executor places the order. |
| Sub-theme core question: "How does the Agent manage rToken and Crypto positions simultaneously?" | Omni's entire purpose. rToken collateral is modelled and monitored, crypto and stock perpetuals are executed, and the interaction between the two is what drives the decision. |
| Sub-theme example: "Hedge Crypto when rToken anomalies; dynamic cross-market allocation after macro shocks" | The primary action is a mapped stock-perpetual hedge against an rToken collateral gap. |
| "Simulated or paper trading acceptable" | Execution is real paper execution on the futures leg; the rToken leg is real data with simulated fills, labelled as such. |

Sub-themes are optional per the handbook ("optional, not mandatory"). Omni chooses a named one
because the concept fits it exactly.

## Required materials

| Requirement | Status | Where |
|---|---|---|
| Runnable Demo | **Met** | `demo/run_demo.sh`, `python3 -m omni.cli demo` |
| Event → decision → execution flow | **Met** | the seven-step cycle, reproduced in `evidence/demo-run-*.log` |
| Paper trading log, run during the competition period | **Started 2026-09-11** | `logs/paper-log-*.jsonl` |
| Compliant X post | **Outstanding, author action** | must include `#BitgetHackathon` and `@Bitget_AI` and introduce the product |

Honest note on log duration: the handbook recommends at least two weeks and says that starting
on 9/3 meets the minimum. Omni's log starts on 9/11, so it will hold roughly ten days of runs by
the 9/21 deadline. The log is real and continuous; the shortfall against the *recommendation* is
stated here rather than hidden.

## Form fields

| Field | Status | Source |
|---|---|---|
| Project Description, part 1 Thesis | Ready | [problem.md](problem.md) |
| part 2 Target user and product value | Ready | [problem.md](problem.md), "Named user" |
| part 3 Validation data and key metrics | Partly ready | [evidence.md](evidence.md), and `omni report` |
| part 4 Progress | Ready | this file, plus the repository history |
| part 5 Deliverables | Ready | this file, "Required materials" |
| part 6 View on AI trading | Optional | to be written in the form |
| Role of the LLM in your project | Ready to state | decision maker, see below |
| Submission Materials Link | Ready | repository URL, demo log, paper log |
| X Promotional Post Link | Outstanding | author action |
| Track → Sub-theme | Ready | Agentic Trading → Cross-Asset Execution Agent |
| University Name | Optional | author decision |
| Apply for Demo Day | Optional | author decision |
| Apply for K3 Token Subsidy | Optional | author decision |

### Role of the LLM (the honest answer)

- **Primary model:** `deepseek-ai/DeepSeek-V4.1-Flash`, served through an OpenAI-compatible
  endpoint. It receives the session state, the account state and the structured risk state, and
  returns strict JSON: one action, its parameters, a rationale and a confidence.
- **Secondary model:** `zai-org/GLM-5.3-Flash`, used automatically if the primary returns an
  unusable completion.
- **Deterministic fallback:** used only when both models fail. It is labelled
  `used_fallback: true` in the ledger, so no reader can mistake a rule-based decision for a model
  decision.
- **Qwen credits:** not used. Omni does not claim Qwen usage.

## Judging focus

| Criterion | Position |
|---|---|
| Paper trading Sharpe | **Not reported yet.** Fewer than 20 equity observations. The metric withholds the number and says why instead of publishing a meaningless one. |
| Max drawdown | Computed from the recorded paper equity series. |
| Win rate | Reported as `protective_action_share`, the share of decisions that resulted in an executed protective action. A defensive governor holds most of the time, so a low trade count is expected and stated. |
| Decision explainability | Every decision is recorded with the model, latency, token usage, raw response, rationale and confidence, and with the policy verdict and every veto. |
| Agent architecture quality | [architecture.md](architecture.md): perception, deterministic model, model decision, policy control, execution, evidence. |
| Risk control layer effectiveness | Allowlist, hard vetoes, size caps, forced minimum protection, dry-run gates, no transfer path. Unit tested. |

Scoring is 50 percent quantitative and 50 percent judge scoring. The quantitative side is the
weakest part of this entry today and is stated plainly rather than dressed up.

## What would strengthen this entry before 9/21

1. Keep the paper log running daily so the equity series grows and Sharpe becomes reportable.
2. Publish the compliant X post.
3. Record a short screen video of one complete cycle.
4. Optional: apply for Reality order-book whitelist through Bitget BD, which would replace the
   simulated rToken fills with real depth access.
