"""Deterministic policy and guardrail layer.

The LLM proposes. This layer disposes. It enforces the allowlist, size and
leverage caps, position existence, and a forced minimum protection when the
modelled state is dangerous and the model chose to do nothing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import ALLOWED_ACTIONS, FORBIDDEN_ACTIONS


@dataclass
class PolicyConfig:
    # Kept inside the demo exchange's observed per-order contract cap so a
    # protective hedge is not rejected for size. The executor also clamps and
    # retries if an exchange cap is reported, whatever this value is.
    max_order_notional_usdt: float = 5_000.0
    max_leverage: float = 20.0
    force_action_on_breach: bool = True
    allow_hedge: bool = True


@dataclass
class PolicyResult:
    approved: bool
    action: str
    params: dict
    reason: str
    override: bool = False
    vetoes: list = field(default_factory=list)
    checks: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def validate(decision_action: str, decision_params: dict, risk_state: dict,
             session: dict, config: PolicyConfig | None = None) -> PolicyResult:
    cfg = config or PolicyConfig()
    checks: list[str] = []
    vetoes: list[str] = []
    hard_vetoes: list[str] = []
    action = (decision_action or "").strip().upper()
    params = dict(decision_params or {})

    # 1. allowlist
    if action not in ALLOWED_ACTIONS:
        vetoes.append(f"action {action!r} is not in the allowlist {list(ALLOWED_ACTIONS)}")
    else:
        checks.append(f"action {action} is allowlisted")

    # 2. forbidden intents, scanned across the whole proposal. A proposal that
    #    mentions a forbidden operation is a HARD reject: no substitution is
    #    attempted, because the proposal itself cannot be trusted.
    blob = f"{action} {params}".upper()
    for forbidden in FORBIDDEN_ACTIONS:
        if forbidden in blob:
            message = f"proposal mentions forbidden operation {forbidden}"
            vetoes.append(message)
            hard_vetoes.append(message)

    results = risk_state.get("results") or {}
    needs_attention = bool(results.get("needs_attention"))
    breach = bool(results.get("breach"))

    # 3. size and leverage caps
    notional = _num(params.get("notional_usdt"), 0.0)
    if action == "HEDGE_STOCK_PERP":
        if notional <= 0:
            vetoes.append("hedge requires a positive notional_usdt")
        elif notional > cfg.max_order_notional_usdt:
            params["notional_usdt"] = cfg.max_order_notional_usdt
            checks.append(
                f"hedge notional capped to policy maximum {cfg.max_order_notional_usdt:,.0f} USDT"
            )
        if not cfg.allow_hedge:
            vetoes.append("hedging is disabled by policy")

    if action in ("REDUCE_PERP", "CLOSE_PERP"):
        positions = (risk_state.get("observed") or {}).get("positions") or []
        symbols = {str(p.get("symbol", "")).upper() for p in positions}
        symbol = str(params.get("symbol", "")).upper()
        if not symbol:
            vetoes.append("reduce or close requires a symbol")
        elif symbol not in symbols:
            vetoes.append(f"symbol {symbol} is not an open position")

    # 4. session sanity: never open risk into a closed market. Also a hard reject,
    #    because the correct response is to do nothing, not to trade elsewhere.
    if action == "HEDGE_STOCK_PERP" and session.get("liquidity_tier") == "none":
        message = "market is closed for this symbol; no execution permitted"
        vetoes.append(message)
        hard_vetoes.append(message)

    if hard_vetoes:
        return PolicyResult(
            approved=False,
            action="HOLD",
            params={},
            reason="proposal hard rejected: " + "; ".join(hard_vetoes),
            override=False,
            vetoes=vetoes,
            checks=checks,
        )

    if vetoes:
        fallback = _forced_protection(risk_state, cfg)
        reason = "; ".join(vetoes)
        if fallback is not None:
            fb_action, fb_params, fb_reason = fallback
            return PolicyResult(
                approved=True,
                action=fb_action,
                params=fb_params,
                reason=f"proposal rejected ({reason}). Policy applied minimum protection: {fb_reason}",
                override=True,
                vetoes=vetoes,
                checks=checks,
            )
        return PolicyResult(
            approved=False,
            action="HOLD",
            params={},
            reason=f"proposal rejected: {reason}",
            override=False,
            vetoes=vetoes,
            checks=checks,
        )

    # 5. forced minimum protection when the model chose to do nothing
    if cfg.force_action_on_breach and action == "HOLD" and (breach or needs_attention):
        fallback = _forced_protection(risk_state, cfg)
        if fallback is not None:
            fb_action, fb_params, fb_reason = fallback
            return PolicyResult(
                approved=True,
                action=fb_action,
                params=fb_params,
                reason=(
                    "model chose HOLD while the modelled state requires action. "
                    f"Policy applied minimum protection: {fb_reason}"
                ),
                override=True,
                vetoes=[],
                checks=checks,
            )
        checks.append("HOLD accepted, no protective instrument available")

    return PolicyResult(
        approved=True,
        action=action,
        params=params,
        reason="proposal satisfies policy",
        override=False,
        vetoes=[],
        checks=checks,
    )


def _forced_protection(risk_state: dict, cfg: PolicyConfig):
    """Deterministic minimum protection, independent of the model."""
    results = risk_state.get("results") or {}
    hedge = results.get("recommended_hedge") or {}
    if cfg.allow_hedge and _num(hedge.get("notional_usdt"), 0.0) > 0 and hedge.get("symbol"):
        notional = min(_num(hedge.get("notional_usdt")), cfg.max_order_notional_usdt)
        return (
            "HEDGE_STOCK_PERP",
            {"symbol": hedge["symbol"], "notional_usdt": notional},
            f"short {notional:,.0f} USDT of {hedge['symbol']} to neutralise gap risk",
        )
    positions = (risk_state.get("observed") or {}).get("positions") or []
    if positions:
        return (
            "REDUCE_PERP",
            {"symbol": positions[0].get("symbol"), "reduce_pct": 50},
            f"reduce {positions[0].get('symbol')} by 50 percent",
        )
    return None
