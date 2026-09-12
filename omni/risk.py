"""Deterministic cross-asset margin and shock engine.

This module performs arithmetic only. It does not predict prices, and it does
not claim to reproduce Bitget's official liquidation engine. Every output is a
scenario result under the stated inputs, and the assumptions travel with the
result so a reader can audit or reject them.

Modelled identity used here:

    total_equity      = observed demo effective equity + modelled rToken net collateral
    maintenance       = sum over futures positions of (abs(notional) * mmr)
    margin_ratio      = maintenance / total_equity
    buffer            = total_equity - maintenance
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .collateral import RTokenPosition, effective_collateral_value

DISCLAIMER = (
    "Scenario estimate. Not Bitget's official margin or liquidation engine. "
    "Demand Buffer and Liquidation Shock are model outputs, not exchange guarantees."
)

ASSUMPTIONS = (
    "rToken collateral ratio (haircut) is queried from the venue's published "
    "discount-rate schedule when available; the explicit --haircut input is a "
    "documented fallback, and the ledger records which was used",
    "crypto shock is applied to both futures PnL and futures notional",
    "rToken shock is applied to the modelled collateral mark only",
    "fees, funding and further margin-mode effects are not modelled inside the shock",
)


@dataclass
class FuturesPosition:
    symbol: str
    pos_side: str
    total: float
    mark_price: float
    avg_price: float
    unrealised_pnl: float
    mmr: float
    leverage: float
    asset_class: str = "crypto"

    @property
    def side_sign(self) -> int:
        return 1 if self.pos_side.lower() == "long" else -1

    @property
    def notional(self) -> float:
        return abs(self.total) * self.mark_price


def shock_for(asset_class: str, rtoken_shock_pct: float, crypto_shock_pct: float) -> float:
    """The scenario shock that applies to a position.

    Derived from the asset class rather than supplied by the caller, so a call
    site cannot forget to shock a position and silently understate the risk.
    A stock perpetual tracks the equity gap; anything else takes the crypto shock.
    """
    return rtoken_shock_pct if asset_class == "stock" else crypto_shock_pct


@dataclass
class RiskState:
    as_of: str
    scenario: dict
    observed: dict
    modelled: dict
    results: dict
    assumptions: list = field(default_factory=list)
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict:
        return asdict(self)


def _fmt_usdt(value: float) -> str:
    return f"{value:,.2f} USDT"


def evaluate(
    as_of: str,
    observed_effective_equity: float,
    rtoken_positions: list[RTokenPosition],
    rtoken_marks: dict,
    futures_positions: list[FuturesPosition],
    haircut_pct: float,
    rtoken_shock_pct: float,
    crypto_shock_pct: float,
    hedge_symbol: str,
    risk_threshold_usdt: float = 250.0,
    risk_budget_pct: float = 0.10,
) -> RiskState:
    rtoken_gross = 0.0
    rtoken_effective = 0.0
    rtoken_detail = []
    for pos in rtoken_positions:
        mark = float(rtoken_marks.get(pos.symbol, 0.0))
        gross = float(pos.qty) * mark
        effective = effective_collateral_value(pos.qty, mark, haircut_pct)
        rtoken_gross += gross
        rtoken_effective += effective
        # Per-position detail so a reader can see the mark and value each
        # position contributed, rather than only the aggregate.
        rtoken_detail.append({
            **pos.to_dict(),
            "mark_price": round(mark, 6),
            "gross_value": round(gross, 4),
            "effective_collateral": round(effective, 4),
        })

    base_maintenance = sum(p.notional * p.mmr for p in futures_positions)
    base_equity = observed_effective_equity + rtoken_effective
    base_ratio = (base_maintenance / base_equity) if base_equity > 0 else 0.0
    base_buffer = base_equity - base_maintenance

    # --- shocked state -----------------------------------------------------
    # Each position's shock is derived from its asset class: stock perpetuals
    # move with the equity gap, crypto perpetuals move with the crypto shock.
    # Applying one shock to everything would misprice the cross-asset book.
    shocks = {
        p.symbol: shock_for(p.asset_class, rtoken_shock_pct, crypto_shock_pct)
        for p in futures_positions
    }
    futures_pnl_delta = sum(
        p.notional * shocks[p.symbol] * p.side_sign for p in futures_positions
    )
    shocked_rtoken_effective = rtoken_effective * (1.0 + rtoken_shock_pct)
    shocked_equity = base_equity + futures_pnl_delta + (shocked_rtoken_effective - rtoken_effective)
    shocked_maintenance = sum(
        (p.notional * (1.0 + shocks[p.symbol])) * p.mmr for p in futures_positions
    )
    shocked_ratio = (shocked_maintenance / shocked_equity) if shocked_equity > 0 else 1.0
    shocked_buffer = shocked_equity - shocked_maintenance

    # --- liquidation shock estimate ---------------------------------------
    # rToken shock at which the buffer reaches zero, holding the crypto shock fixed.
    # Only reported when the rToken leg alone can plausibly drive the buffer to
    # zero. A figure beyond -100% would mean the shortfall comes from elsewhere,
    # so it is withheld instead of publishing a meaningless number.
    liquidation_shock_pct = None
    liquidation_shock_note = ""
    if rtoken_effective > 0:
        estimate = (shocked_maintenance - shocked_equity) / rtoken_effective
        if estimate >= -1.0:
            liquidation_shock_pct = estimate
        else:
            liquidation_shock_note = (
                "The buffer cannot be driven to zero by the rToken leg alone under this "
                "crypto shock; the modelled shortfall originates in the futures leg"
            )
    else:
        liquidation_shock_note = (
            "No rToken collateral is modelled, so no rToken shock solves the buffer"
        )

    modelled_loss = base_equity - shocked_equity
    loss_pct_of_equity = (modelled_loss / base_equity) if base_equity > 0 else 0.0
    risk_budget_usdt = base_equity * risk_budget_pct

    needs_attention = (
        shocked_buffer <= 0
        or shocked_ratio >= 0.5
        or base_buffer <= risk_threshold_usdt
        or modelled_loss >= risk_budget_usdt
    )

    # --- recommended neutralising hedge on the mapped stock perpetual -----
    hedge_notional = rtoken_gross
    hedge_side = "sell" if hedge_notional > 0 else None

    observed = {
        "demo_effective_equity": round(observed_effective_equity, 4),
        "futures_maintenance": round(base_maintenance, 4),
        "futures_notional": round(sum(p.notional for p in futures_positions), 4),
        "futures_unrealised_pnl": round(sum(p.unrealised_pnl for p in futures_positions), 4),
        "margin_ratio": round(base_ratio, 6),
        "buffer_usdt": round(base_buffer, 4),
        "positions": [
            {
                "symbol": p.symbol,
                "pos_side": p.pos_side,
                "total": p.total,
                "mark_price": p.mark_price,
                "notional": round(p.notional, 4),
                "mmr": p.mmr,
                "leverage": p.leverage,
                "unrealised_pnl": p.unrealised_pnl,
                "asset_class": p.asset_class,
                "applied_shock_pct": shocks.get(p.symbol, 0.0),
            }
            for p in futures_positions
        ],
    }

    modelled = {
        "rtoken_positions": rtoken_detail,
        "rtoken_gross_value": round(rtoken_gross, 4),
        "haircut_pct": haircut_pct,
        "rtoken_effective_collateral": round(rtoken_effective, 4),
        "total_equity_used": round(base_equity, 4),
    }

    results = {
        "futures_pnl_delta": round(futures_pnl_delta, 4),
        "shocked_rtoken_effective_collateral": round(shocked_rtoken_effective, 4),
        "shocked_equity": round(shocked_equity, 4),
        "shocked_maintenance": round(shocked_maintenance, 4),
        "shocked_margin_ratio": round(shocked_ratio, 6),
        "shocked_buffer_usdt": round(shocked_buffer, 4),
        "modelled_loss_usdt": round(modelled_loss, 4),
        "modelled_loss_pct_of_equity": round(loss_pct_of_equity, 6),
        "risk_budget_pct": risk_budget_pct,
        "risk_budget_usdt": round(risk_budget_usdt, 4),
        "breach": shocked_buffer <= 0,
        "needs_attention": needs_attention,
        "liquidation_shock_pct": (
            round(liquidation_shock_pct, 6) if liquidation_shock_pct is not None else None
        ),
        "liquidation_shock_note": liquidation_shock_note,
        "recommended_hedge": {
            "instrument": "mapped stock perpetual",
            "symbol": hedge_symbol,
            "side": hedge_side,
            "notional_usdt": round(hedge_notional, 4),
        },
        "narrative": _narrative(
            shocked_buffer, shocked_ratio, liquidation_shock_pct, hedge_notional,
            modelled_loss, loss_pct_of_equity, risk_budget_pct, liquidation_shock_note,
        ),
    }

    return RiskState(
        as_of=as_of,
        scenario={
            "rtoken_shock_pct": rtoken_shock_pct,
            "crypto_shock_pct": crypto_shock_pct,
        },
        observed=observed,
        modelled=modelled,
        results=results,
        assumptions=list(ASSUMPTIONS),
    )


def _narrative(
    shocked_buffer: float,
    shocked_ratio: float,
    liquidation_shock_pct: float | None,
    hedge_notional: float,
    modelled_loss: float = 0.0,
    loss_pct: float = 0.0,
    risk_budget_pct: float = 0.10,
    liquidation_shock_note: str = "",
) -> str:
    if shocked_buffer <= 0:
        head = "Scenario breaches maintenance. The account does not survive this path."
    elif loss_pct >= risk_budget_pct:
        head = (
            f"Scenario consumes {loss_pct:.1%} of account equity, above the "
            f"{risk_budget_pct:.0%} risk budget."
        )
    elif shocked_ratio >= 0.5:
        head = "Scenario consumes most of the buffer. Risk is elevated."
    else:
        head = "Scenario is survivable with buffer remaining."
    parts = [head, f"Shocked margin ratio {shocked_ratio:.2%}."]
    if liquidation_shock_pct is not None:
        parts.append(
            f"Buffer reaches zero at an rToken shock of {liquidation_shock_pct:+.2%} "
            f"under the same crypto shock."
        )
    elif liquidation_shock_note:
        parts.append(liquidation_shock_note.rstrip(".") + ".")
    if hedge_notional > 0:
        parts.append(
            f"Neutralising hedge on the mapped stock perpetual: {_fmt_usdt(hedge_notional)} short."
        )
    return " ".join(parts)
