"""Execution layer.

Every action follows the same auditable sequence:

    dry run  ->  explicit execution  ->  authoritative readback

The demo environment is a paper account, so no real funds are ever at risk.
Withdrawal and transfer operations are not implemented here at all.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import asdict, dataclass, field

from .bitget_demo import DemoClient
from .config import stock_perp_for
from .venue_risk import effective_order_cap, query_instrument_caps, query_max_open

# The demo exchange enforces a per-order contract cap that is not published in
# the instrument metadata (maxOrderQty reports a much larger number). When the
# order is rejected we read the stated cap and retry once at that size.
QUANTITY_CAP_RE = re.compile(
    r"maximum quantity of contract orders\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE
)


@dataclass
class ExecutionStep:
    name: str
    argv: str
    ok: bool
    endpoint: str | None = None
    request_time: str | None = None
    payload: dict | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionResult:
    action: str
    executed: bool
    reason: str
    steps: list = field(default_factory=list)
    orders: list = field(default_factory=list)
    readback: dict | None = None
    simulated_legs: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


SIZE_REJECTION_MARKERS = (
    "maximum quantity",
    "cannot exceed the maximum",
    "exceed the maximum",
    "less than the minimum",
    "minimum amount",
    "size limit",
)


def _error_texts(result) -> list:
    texts = []
    envelope = result.raw_envelope or {}
    error = envelope.get("error")
    if isinstance(error, dict):
        texts.append(str(error.get("message", "")))
    texts.extend([result.stdout or "", result.stderr or ""])
    return texts


def _is_size_rejection(result) -> bool:
    """True when the venue rejected the order for size rather than for validity."""
    blob = " ".join(_error_texts(result)).lower()
    return any(marker in blob for marker in SIZE_REJECTION_MARKERS)


def _quantity_cap(result) -> float | None:
    """Read the exchange's stated per-order contract cap out of a rejection."""
    for text in _error_texts(result):
        match = QUANTITY_CAP_RE.search(text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _step_from_result(name: str, result) -> ExecutionStep:
    envelope = result.raw_envelope or {}
    return ExecutionStep(
        name=name,
        argv=" ".join(result.argv),
        ok=bool(result.ok),
        endpoint=envelope.get("endpoint"),
        request_time=envelope.get("requestTime"),
        payload=(envelope.get("data") if isinstance(envelope.get("data"), dict) else None),
        error=(
            envelope.get("error", {}).get("message")
            if isinstance(envelope.get("error"), dict)
            else None
        ),
    )


def execute(action: str, params: dict, client: DemoClient, marks: dict,
            hedge_symbol: str = "") -> ExecutionResult:
    steps: list[ExecutionStep] = []
    orders: list[dict] = []

    if action == "HOLD":
        return ExecutionResult(
            action=action,
            executed=False,
            reason="no market action required",
            steps=steps,
        )

    if action == "HEDGE_STOCK_PERP":
        notional = float(params.get("notional_usdt") or 0.0)
        # Accept either an rToken symbol or a stock perpetual symbol and map it.
        # An unmapped symbol yields "", and we refuse rather than guess an
        # instrument to short.
        hedge_symbol = stock_perp_for(str(params.get("symbol") or hedge_symbol))
        if not hedge_symbol:
            return ExecutionResult(
                action=action,
                executed=False,
                reason=(
                    "no mapped hedge instrument for "
                    f"{params.get('symbol') or hedge_symbol!r}; refusing to guess"
                ),
                steps=steps,
            )
        mark = float(marks.get(hedge_symbol) or 0.0)
        if mark <= 0:
            return ExecutionResult(
                action=action,
                executed=False,
                reason=f"no mark available for {hedge_symbol}; refusing to size a blind hedge",
            )
        qty = round(notional / mark, 2)
        if qty <= 0:
            return ExecutionResult(
                action=action,
                executed=False,
                reason="computed hedge quantity rounds to zero",
            )

        # Pre-clamp to the venue's own size answers so limits are queried, not
        # discovered by rejection: instrument caps (per-order maximums) and
        # max-open-available (venue-computed additional size including tiers
        # and margin). Falls back to the requested size when reads fail.
        caps = query_instrument_caps(client, hedge_symbol)
        cap = effective_order_cap(caps)
        max_open = query_max_open(client, hedge_symbol, "sell")
        venue_max_sell = max_open.get("maxSellOpen", 0.0)
        clamp_note = ""
        pre_clamp = qty
        if cap > 0 and qty > cap:
            clamp_note = (
                f"clamped to instrument cap: {qty:g} -> {cap:g} {hedge_symbol} "
                f"(instruments maxOrderQty/maxMarketOrderQty)"
            )
            qty = cap
        if venue_max_sell > 0 and qty > venue_max_sell:
            clamp_note = (clamp_note + "; " if clamp_note else "") + (
                f"clamped to venue max-open: {qty:g} -> {venue_max_sell:g} "
                f"{hedge_symbol} (max-open-available)"
            )
            qty = venue_max_sell
        qty = math.floor(qty * 100) / 100.0
        if qty != pre_clamp:
            steps.append(ExecutionStep(
                name="venue_pre_clamp",
                argv=f"venue pre-clamp {hedge_symbol}",
                ok=True,
                payload={"note": clamp_note},
            ))

        preview = client.place_order(
            category="USDT-FUTURES", symbol=hedge_symbol, side="sell", order_type="market",
            qty=str(qty), pos_side="short", reduce_only="no", dry_run=True,
        )
        steps.append(_step_from_result("dry_run", preview))
        if not preview.ok:
            return ExecutionResult(
                action=action, executed=False,
                reason="dry run rejected by the exchange; nothing was sent", steps=steps,
            )

        sent = client.place_order(
            category="USDT-FUTURES", symbol=hedge_symbol, side="sell", order_type="market",
            qty=str(qty), pos_side="short", reduce_only="no",
        )
        steps.append(_step_from_result("execute", sent))

        # The demo exchange additionally enforces position-tier caps not
        # visible in the instrument metadata. When a size rejection still
        # comes back after the pre-clamp, halve the size and retry, so the
        # agent still delivers the largest protective order the venue accepts.
        attempt = 0
        while (not sent.ok) and attempt < 3 and _is_size_rejection(sent):
            stated = _quantity_cap(sent)
            reduced = None
            if stated is not None and 0 < stated < qty:
                reduced = math.floor(stated * 100) / 100.0
            else:
                reduced = math.floor(qty * 0.5 * 100) / 100.0
            if reduced <= 0 or reduced >= qty:
                break
            clamp_note = (
                f"venue size limit reached, reduced {qty:g} to {reduced:g} {hedge_symbol} "
                f"after {attempt + 1} retry" + ("ies" if attempt else "")
            )
            qty = reduced
            preview_retry = client.place_order(
                category="USDT-FUTURES", symbol=hedge_symbol, side="sell",
                order_type="market", qty=str(qty), pos_side="short", reduce_only="no",
                dry_run=True,
            )
            steps.append(_step_from_result(f"dry_run_retry_{attempt + 1}", preview_retry))
            if not preview_retry.ok:
                break
            sent = client.place_order(
                category="USDT-FUTURES", symbol=hedge_symbol, side="sell",
                order_type="market", qty=str(qty), pos_side="short", reduce_only="no",
            )
            steps.append(_step_from_result(f"execute_retry_{attempt + 1}", sent))
            attempt += 1

        if sent.ok and isinstance(sent.data, dict):
            orders.append({"symbol": hedge_symbol, "side": "sell", "qty": qty, **sent.data})

        readback = _readback(client, "USDT-FUTURES")
        reason = f"short {qty:g} {hedge_symbol} to neutralise rToken collateral gap risk"
        if clamp_note:
            reason += f" ({clamp_note})"
        if not sent.ok:
            reason += " (order rejected by the exchange)"
        return ExecutionResult(
            action=action,
            executed=bool(sent.ok),
            reason=reason,
            steps=steps,
            orders=orders,
            readback=readback,
        )

    if action in ("REDUCE_PERP", "CLOSE_PERP"):
        symbol = str(params.get("symbol") or "").upper()
        if not symbol:
            return ExecutionResult(action=action, executed=False, reason="no symbol supplied")

        preview = client.close_position("USDT-FUTURES", symbol, dry_run=True)
        steps.append(_step_from_result("dry_run", preview))
        if not preview.ok:
            return ExecutionResult(
                action=action, executed=False,
                reason="close dry run rejected; nothing was sent", steps=steps,
            )

        confirmed = client.close_position("USDT-FUTURES", symbol, confirm=True)
        steps.append(_step_from_result("execute", confirmed))
        if confirmed.ok and isinstance(confirmed.data, dict):
            for item in confirmed.data.get("list") or []:
                orders.append({"symbol": symbol, "action": "close", **item})

        readback = _readback(client, "USDT-FUTURES")
        return ExecutionResult(
            action=action,
            executed=bool(confirmed.ok),
            reason=f"closed the {symbol} perpetual position",
            steps=steps,
            orders=orders,
            readback=readback,
        )

    return ExecutionResult(
        action=action, executed=False, reason="unsupported action reached the executor",
    )


def _readback(client: DemoClient, category: str) -> dict:
    time.sleep(1.0)
    positions = client.positions(category)
    return {"open_positions": positions, "count": len(positions)}
