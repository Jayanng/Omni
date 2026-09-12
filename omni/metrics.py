"""Metrics computed from the ledger.

Honesty rules applied here:

* Sharpe is reported only when there are enough return observations, and is
  labelled as computed on the recorded paper equity series.
* A defensive governor trades rarely, so trade-count metrics are reported
  alongside an explicit note that a low count is expected.
* A policy override is the containment mechanism working, not a failure, so it
  is reported separately from a genuine risk violation. A risk violation means
  the executor ran something policy had rejected, or ran a non-allowlisted
  action. That count should stay at zero.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from .config import ALLOWED_ACTIONS
from .ledger import Ledger

MIN_SAMPLES_FOR_SHARPE = 20


def _read(path: Path) -> list:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def compute(log_dir: Path) -> dict:
    entries: list = []
    for path in Ledger.all_logs(log_dir):
        entries.extend(_read(path))

    decisions = [e for e in entries if e.get("kind") == "decision"]
    executions = [e for e in entries if e.get("kind") == "execution"]
    snapshots = [e for e in entries if e.get("kind") == "account_snapshot"]
    sessions = [e for e in entries if e.get("kind") == "session"]

    def payload(entry: dict) -> dict:
        value = entry.get("payload")
        return value if isinstance(value, dict) else {}

    def policy_of(entry: dict) -> dict:
        value = payload(entry).get("policy")
        return value if isinstance(value, dict) else {}

    def execution_of(entry: dict) -> dict:
        value = payload(entry).get("execution")
        return value if isinstance(value, dict) else {}

    overrides = [e for e in executions if policy_of(e).get("override")]
    completed = [e for e in executions if execution_of(e).get("executed")]
    blocked = [
        e for e in executions
        if execution_of(e).get("action") not in (None, "HOLD")
        and not execution_of(e).get("executed")
    ]

    # A violation is an executed action that policy rejected, or one that is not
    # allowlisted. Where the policy record has no action at all the state is
    # unverifiable, so it fails closed and counts. A policy override is a
    # different thing and is counted separately above.
    violations = [
        e for e in completed
        if policy_of(e).get("approved") is False
        or policy_of(e).get("action") not in ALLOWED_ACTIONS
    ]

    # Equity observations from both account snapshots and daemon cycles,
    # ordered by timestamp so the return series is a real time series.
    equity_points: list[tuple[str, float]] = []
    for snap in snapshots:
        raw = (payload(snap).get("assets") or {}).get("effEquity")
        if raw is None:
            continue
        try:
            equity_points.append((str(snap.get("ts") or ""), float(raw)))
        except (TypeError, ValueError):
            continue
    for entry in entries:
        if entry.get("kind") != "daemon_cycle":
            continue
        raw = (payload(entry).get("account") or {}).get("equity")
        if raw is None:
            continue
        try:
            equity_points.append((str(entry.get("ts") or ""), float(raw)))
        except (TypeError, ValueError):
            continue
    equity_points.sort(key=lambda point: point[0])
    equity_series = [value for _, value in equity_points]

    max_drawdown_pct = 0.0
    peak = None
    for value in equity_series:
        peak = value if peak is None else max(peak, value)
        if peak:
            max_drawdown_pct = max(max_drawdown_pct, (peak - value) / peak)

    sharpe = None
    sharpe_note = (
        f"not reported: {len(equity_series)} equity observations, "
        f"minimum {MIN_SAMPLES_FOR_SHARPE} required for a meaningful estimate"
    )
    if len(equity_series) >= MIN_SAMPLES_FOR_SHARPE:
        returns = [
            (equity_series[i] - equity_series[i - 1]) / equity_series[i - 1]
            for i in range(1, len(equity_series))
            if equity_series[i - 1]
        ]
        if len(returns) >= 2 and statistics.pstdev(returns) > 0:
            sharpe = statistics.mean(returns) / statistics.pstdev(returns)
            sharpe_note = "computed on the recorded paper equity series, not annualised"
        else:
            sharpe_note = (
                "not reported: enough observations, but the equity series is flat, "
                "so Sharpe is undefined"
            )

    sessions_regimes = sorted(
        {str(payload(e).get("regime")) for e in sessions if payload(e).get("regime")}
    )

    return {
        "runs": len({e.get("run_id") for e in entries}),
        "decisions": len(decisions),
        "executions_attempted": len(executions),
        "executions_completed": len(completed),
        "blocked_or_refused": len(blocked),
        "policy_overrides": len(overrides),
        "risk_violation_count": len(violations),
        "risk_violation_rate": (
            round(len(violations) / len(completed), 4) if completed else 0.0
        ),
        "protective_action_share": (
            round(len(completed) / len(decisions), 4) if decisions else 0.0
        ),
        "session_regimes_observed": sessions_regimes,
        "equity_observations": len(equity_series),
        "max_drawdown_pct": round(max_drawdown_pct, 6),
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "sharpe_note": sharpe_note,
        "notes": [
            "risk_violation_count counts executed actions that policy had rejected, "
            "or that were not allowlisted; it should stay at zero",
            "policy_overrides counts proposals the policy layer overrode or hardened, "
            "which is the risk control layer working as designed",
            "a defensive governor holds most of the time, so low trade counts are expected",
        ],
    }
