"""LLM decision layer.

The LLM is the decision maker for this agent, as the hackathon's Agentic Trading
track requires. It receives the structured risk state and chooses one action
from a fixed allowlist. Deterministic policy code can veto or override the
choice, and both the model output and the policy verdict are recorded.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field

from .config import ALLOWED_ACTIONS, FORBIDDEN_ACTIONS, USER_AGENT

SYSTEM_PROMPT = (
    "You are Omni, a cross-asset risk governor for a Bitget Unified Trading Account.\n"
    "Your job is NOT to find alpha. Your job is to keep the account solvent when tokenized "
    "US stocks (rToken) are posted as collateral and crypto perpetual positions keep moving "
    "while the underlying cash equity market is closed.\n\n"
    "You must choose exactly one action and reply with JSON only, no prose, no markdown.\n\n"
    "Allowed actions:\n"
    "- HOLD: take no market action.\n"
    "- HEDGE_STOCK_PERP: open a short position on a stock perpetual to neutralise rToken "
    "collateral gap risk. Params: symbol (stock perpetual symbol such as NVDAUSDT), "
    "notional_usdt.\n"
    "- REDUCE_PERP: partially reduce an existing crypto perpetual position. "
    "Params: symbol, reduce_pct (0-100).\n"
    "- CLOSE_PERP: fully close an existing crypto perpetual position. Params: symbol.\n\n"
    "Hard rules: never propose withdrawals, transfers, leverage changes, or any new risk. "
    "Only propose actions that reduce modelled liquidation risk.\n\n"
    'Reply with exactly: {"action": "...", "params": {...}, "rationale": "...", '
    '"confidence": 0.0}'
)


@dataclass
class Decision:
    action: str
    params: dict
    rationale: str
    confidence: float
    model: str
    used_fallback: bool
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw_response: str = ""
    error: str | None = None
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _post_chat(base_url: str, api_key: str, model: str, messages: list, timeout: int,
               max_tokens: int = 900) -> tuple[dict | None, str]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), ""
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} {exc.read().decode(errors='ignore')[:200]}"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _extract_json(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def fallback_decision(risk_state: dict, reason: str) -> Decision:
    """Deterministic policy used when the model is unavailable or unusable."""
    results = risk_state.get("results", {})
    needs = bool(results.get("needs_attention"))
    breach = bool(results.get("breach"))
    hedge = results.get("recommended_hedge") or {}
    positions = (risk_state.get("observed") or {}).get("positions") or []

    if breach or needs:
        if hedge.get("notional_usdt"):
            return Decision(
                action="HEDGE_STOCK_PERP",
                params={
                    "symbol": hedge.get("symbol") or "NVDAUSDT",
                    "notional_usdt": hedge["notional_usdt"],
                },
                rationale=(
                    "Deterministic fallback: modelled collateral gap risk is elevated, so "
                    "neutralise the rToken exposure with a stock perpetual short."
                ),
                confidence=0.6,
                model="deterministic-fallback",
                used_fallback=True,
                latency_ms=0,
                notes=[reason],
            )
        if positions:
            return Decision(
                action="REDUCE_PERP",
                params={"symbol": positions[0]["symbol"], "reduce_pct": 50},
                rationale="Deterministic fallback: reduce crypto perpetual exposure.",
                confidence=0.6,
                model="deterministic-fallback",
                used_fallback=True,
                latency_ms=0,
                notes=[reason],
            )
    return Decision(
        action="HOLD",
        params={},
        rationale="Deterministic fallback: no modelled breach, hold and keep observing.",
        confidence=0.55,
        model="deterministic-fallback",
        used_fallback=True,
        latency_ms=0,
        notes=[reason],
    )


def compact_state(risk_state: dict, session: dict) -> dict:
    """The minimal, decision-relevant view of the state handed to the model.

    The full risk state (assumptions, disclaimer, narrative) stays in the ledger
    for auditors. Sending all of it to the model only adds tokens, which on a
    reasoning model means latency and a higher chance of an empty completion.
    """
    observed = risk_state.get("observed") or {}
    modelled = risk_state.get("modelled") or {}
    results = risk_state.get("results") or {}
    return {
        "session": {
            "regime": session.get("regime"),
            "mark_confidence": session.get("mark_confidence"),
            "liquidity_tier": session.get("liquidity_tier"),
            "cash_market_open": session.get("cash_market_open"),
            "weekend_tradable": session.get("weekend_tradable"),
            "liquidation_tier_note": "liquidity_tier none means the venue is closed",
        },
        "account": {
            "effective_equity_usdt": observed.get("demo_effective_equity"),
            "futures_maintenance_usdt": observed.get("futures_maintenance"),
            "futures_notional_usdt": observed.get("futures_notional"),
            "margin_ratio": observed.get("margin_ratio"),
            "buffer_usdt": observed.get("buffer_usdt"),
            "positions": [
                {
                    "symbol": p.get("symbol"),
                    "side": p.get("pos_side"),
                    "notional_usdt": p.get("notional"),
                    "asset_class": p.get("asset_class"),
                    "mmr": p.get("mmr"),
                }
                for p in (observed.get("positions") or [])
            ],
        },
        "collateral": {
            "rtoken_gross_usdt": modelled.get("rtoken_gross_value"),
            "haircut_pct": modelled.get("haircut_pct"),
            "rtoken_effective_usdt": modelled.get("rtoken_effective_collateral"),
            "positions": [
                {"symbol": p.get("symbol"), "qty": p.get("qty")}
                for p in (modelled.get("rtoken_positions") or [])
            ],
        },
        "scenario": {
            "rtoken_shock_pct": (risk_state.get("scenario") or {}).get("rtoken_shock_pct"),
            "crypto_shock_pct": (risk_state.get("scenario") or {}).get("crypto_shock_pct"),
            "shocked_equity_usdt": results.get("shocked_equity"),
            "shocked_margin_ratio": results.get("shocked_margin_ratio"),
            "shocked_buffer_usdt": results.get("shocked_buffer_usdt"),
            "modelled_loss_pct_of_equity": results.get("modelled_loss_pct_of_equity"),
            "risk_budget_pct": results.get("risk_budget_pct"),
            "breach": results.get("breach"),
            "needs_attention": results.get("needs_attention"),
        },
        "recommended_hedge": results.get("recommended_hedge"),
        "allowlist": list(ALLOWED_ACTIONS),
        "never_allowed": list(FORBIDDEN_ACTIONS),
    }


def decide(
    risk_state: dict,
    session: dict,
    base_url: str,
    api_key: str,
    model: str,
    timeout: int = 60,
    fallback_model: str = "",
) -> Decision:
    if not (api_key and model and base_url):
        return fallback_decision(risk_state, "no llm credentials configured")

    user_payload = compact_state(risk_state, session)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, separators=(",", ":"))},
    ]

    # Provider reasoning models occasionally return an empty completion when the
    # reasoning budget is exhausted. Retry with a larger budget, then with an
    # optional secondary model, before dropping to the deterministic policy.
    attempts: list = [(model, 900), (model, 3000)]
    if fallback_model and fallback_model != model:
        attempts.append((fallback_model, 3000))

    started = time.time()
    last_error = ""
    usage: dict = {}
    content = ""
    used_model = model

    for attempt_model, budget in attempts:
        body, error = _post_chat(base_url, api_key, attempt_model, messages, timeout, budget)
        if body is None:
            last_error = error
            continue
        choice = (body.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        usage = body.get("usage") or usage
        used_model = attempt_model
        parsed = _extract_json(content)
        if parsed is not None:
            latency = int((time.time() - started) * 1000)
            return _decision_from_parsed(parsed, used_model, content, usage, latency)
        last_error = f"unusable model output: {content.strip()[:120]!r}"

    latency = int((time.time() - started) * 1000)
    decision = fallback_decision(risk_state, f"llm unusable after retries ({last_error})")
    decision.latency_ms = latency
    decision.raw_response = content
    decision.prompt_tokens = usage.get("prompt_tokens")
    decision.completion_tokens = usage.get("completion_tokens")
    return decision


def _decision_from_parsed(parsed: dict, model: str, content: str, usage: dict,
                          latency: int) -> Decision:
    action = str(parsed.get("action", "")).strip().upper()
    params = parsed.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    rationale = str(parsed.get("rationale", "")).strip()
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return Decision(
        action=action,
        params=params,
        rationale=rationale,
        confidence=confidence,
        model=model,
        used_fallback=action not in ALLOWED_ACTIONS,
        latency_ms=latency,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        raw_response=content,
        notes=(
            [] if action in ALLOWED_ACTIONS
            else [f"model returned disallowed action {action!r}; policy will handle it"]
        ),
    )
