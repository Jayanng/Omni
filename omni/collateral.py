"""rToken collateral valuation and depth-aware simulated execution.

Bitget's demo (paper) service rejects RWA/rToken orders, so the rToken leg is
valued from live production data and its fills are simulated against the real
order book. Everything produced here is labelled ``simulated`` so no reader can
mistake it for an executed exchange fill.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import RTOKEN_FEE_RATE


@dataclass
class BookLevel:
    price: float
    size: float


@dataclass
class FillResult:
    symbol: str
    side: str
    requested_qty: float
    filled_qty: float
    unfilled_qty: float
    vwap: float
    notional: float
    fee: float
    fee_rate: float
    levels_consumed: int
    reference_mid: float
    slippage_bps: float
    simulated: bool = True
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RTokenPosition:
    symbol: str
    code: str
    qty: float
    avg_price: float
    source: str = "paper-ledger"

    def to_dict(self) -> dict:
        return asdict(self)


def parse_book(book: dict) -> tuple[list[BookLevel], list[BookLevel]]:
    asks = [BookLevel(float(p), float(s)) for p, s in (book.get("a") or [])]
    bids = [BookLevel(float(p), float(s)) for p, s in (book.get("b") or [])]
    for level_list, reverse in ((asks, False), (bids, True)):
        level_list.sort(key=lambda lv: lv.price, reverse=reverse)
    return asks, bids


def mid_price(asks: list[BookLevel], bids: list[BookLevel]) -> float:
    if asks and bids:
        return (asks[0].price + bids[0].price) / 2.0
    if asks:
        return asks[0].price
    if bids:
        return bids[0].price
    return 0.0


def simulate_fill(
    symbol: str,
    side: str,
    qty: float,
    book: dict,
    fee_rate: float = RTOKEN_FEE_RATE,
    shock_pct: float = 0.0,
) -> FillResult:
    """Walk the real book to estimate a fill. ``shock_pct`` scales book prices.

    A negative ``shock_pct`` models a market move before the exit, which is how
    the pre-mortem estimates the cost of de-risking into a stressed book.
    """
    asks, bids = parse_book(book)
    reference_mid = mid_price(asks, bids)
    levels = asks if side == "buy" else bids

    remaining = float(qty)
    spent = 0.0
    filled = 0.0
    consumed = 0
    scale = 1.0 + float(shock_pct)

    for level in levels:
        if remaining <= 0:
            break
        price = level.price * scale
        take = min(remaining, level.size)
        spent += take * price
        filled += take
        remaining -= take
        consumed += 1

    vwap = (spent / filled) if filled > 0 else 0.0
    notional = spent
    fee = notional * fee_rate
    slippage_bps = 0.0
    if reference_mid > 0 and vwap > 0:
        direction = 1.0 if side == "buy" else -1.0
        slippage_bps = direction * (vwap - reference_mid) / reference_mid * 10_000.0

    notes = [
        "simulated against the live public Bitget order book",
        "rToken spot fee reference 0.05 percent maker and taker",
    ]
    if shock_pct:
        notes.append(f"book prices scaled by {shock_pct:+.2%} to model the stress scenario")
    if remaining > 0:
        notes.append("book depth insufficient for the full size; residual left unfilled")

    return FillResult(
        symbol=symbol,
        side=side,
        requested_qty=float(qty),
        filled_qty=filled,
        unfilled_qty=max(remaining, 0.0),
        vwap=vwap,
        notional=notional,
        fee=fee,
        fee_rate=fee_rate,
        levels_consumed=consumed,
        reference_mid=reference_mid,
        slippage_bps=slippage_bps,
        notes=notes,
    )


def gross_value(qty: float, price: float) -> float:
    return float(qty) * float(price)


def effective_collateral_value(qty: float, price: float, haircut_pct: float) -> float:
    """Collateral-ratio-adjusted value. Bitget applies asset-specific ratios."""
    return gross_value(qty, price) * (1.0 - float(haircut_pct))
