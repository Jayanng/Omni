"""Venue-published risk parameters.

Replaces modelled values with the exchange's own published schedules:

- collateral haircut: ``/api/v3/market/discount-rate`` (discountRate action in
  the agent CLI) returns per-coin, per-tier collateral ratios. A discount rate
  of 0.95 means the venue counts 95% of the coin's value as margin, i.e. a 5%
  haircut. The tier is selected by the holding's USD value.

- maintenance margin tiers: ``/api/v3/market/position-tier`` (positionTier
  action) returns per-symbol tiers: notional band -> leverage cap and MMR.
  Used to sanity-check the per-position ``mmr`` the account API reports and to
  model which tier a new hedge would land in.

- instrument caps: ``market --action instruments`` returns ``maxOrderQty`` and
  ``maxMarketOrderQty``. Orders are pre-clamped to the stricter of the two so
  size limits are queried, not discovered by rejection.

Every value carries its source string so the ledger records provenance. If a
venue read fails, callers fail toward caution or use an explicit operator
override marked unverified. Nothing is silently invented.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bitget_demo import DemoClient


@dataclass
class HaircutQuote:
    haircut_pct: float
    discount_rate: float
    tier_start_usdt: float
    source: str


@dataclass
class TierBand:
    tier: int
    min_usdt: float
    max_usdt: float
    mmr: float
    max_leverage: float


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pick_tier(bands: list[dict], value_usdt: float) -> dict | None:
    """Select the band whose [min, max) contains the position value."""
    best = None
    for band in bands or []:
        lo = _to_float(band.get("tierStartValue", band.get("minTierValue")))
        if value_usdt >= lo:
            if best is None or lo >= _to_float(best.get("tierStartValue", best.get("minTierValue"))):
                best = band
    return best


def _discount_coin(rtoken_symbol: str) -> str:
    """Map a trading symbol (RNVDAUSDT) to the discount-rate coin name (rNVDA)."""
    sym = (rtoken_symbol or "").strip().upper()
    if sym.endswith("USDT"):
        sym = sym[: -len("USDT")]
    return "r" + sym if not sym.startswith("R") else sym


def query_haircut(client: DemoClient, coin: str, holding_value_usdt: float) -> HaircutQuote | None:
    """Venue haircut for ``coin`` at the given holding value, from discount-rate.

    Returns None when the coin is not listed or the call fails; the caller
    must fail toward caution or use an explicitly supplied operator override.
    """
    try:
        result = client.call(
            ["market", "--action", "discountRate", "--productType", "USDT-FUTURES"],
            allow_failure=True,
        )
    except Exception:  # noqa: BLE001 - venue read failure must not crash a cycle
        return None
    data = result.data
    if not isinstance(data, list):
        return None
    wanted = _discount_coin(coin).upper()
    for entry in data:
        if str(entry.get("coin", "")).upper() != wanted:
            continue
        band = _pick_tier(entry.get("list") or [], holding_value_usdt)
        if band is None:
            return None
        discount = _to_float(band.get("discountRate"))
        if not 0.0 < discount <= 1.0:
            return None
        return HaircutQuote(
            haircut_pct=1.0 - discount,
            discount_rate=discount,
            tier_start_usdt=_to_float(band.get("tierStartValue")),
            source=(
                f"venue /api/v3/market/discount-rate coin={coin} "
                f"tierStart={band.get('tierStartValue')}USDT discountRate={discount}"
            ),
        )
    return None


def query_mmr_tiers(client: DemoClient, symbol: str) -> list[TierBand]:
    """Venue maintenance-margin tiers for a futures symbol."""
    try:
        result = client.call(
            ["market", "--action", "positionTier", "--category", "USDT-FUTURES", "--symbol", symbol],
            allow_failure=True,
        )
    except Exception:  # noqa: BLE001
        return []
    data = result.data
    if not isinstance(data, list):
        return []
    bands = []
    for band in data:
        bands.append(
            TierBand(
                tier=int(_to_float(band.get("tier")) or 0),
                min_usdt=_to_float(band.get("minTierValue")),
                max_usdt=_to_float(band.get("maxTierValue")),
                mmr=_to_float(band.get("mmr")),
                max_leverage=_to_float(band.get("leverage")),
            )
        )
    bands.sort(key=lambda b: b.min_usdt)
    return bands


def mmr_for_notional(bands: list[TierBand], notional_usdt: float) -> float | None:
    """Official MMR for a position of the given notional, or None if unknown."""
    for band in bands:
        if band.min_usdt <= notional_usdt < band.max_usdt or band.max_usdt == 0:
            return band.mmr
    return None


def next_tier_above(bands: list[TierBand], notional_usdt: float) -> TierBand | None:
    """The band a larger position would graduate into (tier-jump awareness)."""
    for band in bands:
        if band.min_usdt > notional_usdt:
            return band
    return None


def query_instrument_caps(client: DemoClient, symbol: str) -> dict:
    """Per-symbol order size caps from the instrument metadata."""
    try:
        result = client.call(
            ["market", "--action", "instruments", "--category", "USDT-FUTURES", "--symbol", symbol],
            allow_failure=True,
        )
    except Exception:  # noqa: BLE001
        return {}
    data = result.data
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return {}
    return {
        "max_order_qty": _to_float(data.get("maxOrderQty")),
        "max_market_order_qty": _to_float(data.get("maxMarketOrderQty")),
        "min_order_qty": _to_float(data.get("minOrderQty")),
        "min_order_amount": _to_float(data.get("minOrderAmount")),
        "max_leverage": _to_float(data.get("maxLeverage")),
    }


def query_max_open(client: DemoClient, symbol: str, side: str = "sell") -> dict:
    """Venue-computed maximum additional open size for a market order.

    ``/api/v3/account/max-open-available`` answers, before any order is sent,
    how much size the account may still open on this symbol and side. It folds
    in position tiers, margin availability and existing positions, so it is the
    authoritative pre-trade size check: clamping here means the venue never
    has to reject the order at all.
    """
    try:
        result = client.call(
            [
                "order", "--action", "maxOpen",
                "--category", "USDT-FUTURES", "--symbol", symbol,
                "--orderType", "market", "--side", side,
            ],
            allow_failure=True,
        )
    except Exception:  # noqa: BLE001
        return {}
    data = result.data
    if not isinstance(data, dict):
        return {}
    out = {}
    for key in ("maxBuyOpen", "maxSellOpen", "available"):
        value = _to_float(data.get(key))
        if value > 0:
            out[key] = value
    out["source"] = f"venue /api/v3/account/max-open-available symbol={symbol} side={side}"
    return out


def max_sell_open(client: DemoClient, symbol: str) -> float:
    """Convenience: venue max additional short size, 0.0 when unknown."""
    data = query_max_open(client, symbol, "sell")
    return data.get("maxSellOpen", 0.0)


def effective_order_cap(caps: dict) -> float:
    """The stricter of the limit and market order caps; 0 when unknown."""
    values = [v for v in (caps.get("max_order_qty"), caps.get("max_market_order_qty")) if v and v > 0]
    return min(values) if values else 0.0
