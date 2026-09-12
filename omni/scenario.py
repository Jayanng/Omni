"""Scenario shock derivation from live market history.

The scenario shocks are the loss magnitudes the risk model stresses the book
against. They used to be fixed constants supplied as defaults, which meant the
stress test did not change when the market's own behaviour changed.

This module derives them from the instrument's own realised history instead:
it pulls live candles for the instrument being stressed and takes an empirical
lower-tail quantile of the observed close-to-close returns. The method, the
sample size, the window and the resulting value travel with the number, so a
reader can reproduce or reject it.

This is still a scenario input, not a forecast. The difference is that it is
now anchored to the instrument's realised behaviour rather than to a number
someone typed, and the provenance is recorded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from . import bitget_public as bp

DEFAULT_LOOKBACK_BARS = 30
DEFAULT_INTERVAL = "1D"
DEFAULT_QUANTILE = 0.05
MIN_SAMPLES_FOR_QUANTILE = 20


@dataclass
class ShockEstimate:
    symbol: str
    shock_pct: float
    method: str
    samples: int
    interval: str
    lookback_bars: int
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


def _closes(rows) -> list:
    out = []
    for row in rows or []:
        try:
            out.append(float(row[4]))
        except (IndexError, TypeError, ValueError):
            continue
    return out


def close_to_close_returns(rows) -> list:
    """Daily (or window) returns from OHLC rows shaped [ts, o, h, l, c, ...]."""
    closes = _closes(rows)
    returns = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev > 0:
            returns.append((closes[i] - prev) / prev)
    return returns


def empirical_tail_shock(
    symbol: str,
    interval: str = DEFAULT_INTERVAL,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
    quantile: float = DEFAULT_QUANTILE,
) -> ShockEstimate | None:
    """Lower-tail quantile of the instrument's realised returns.

    Returns None when the candles cannot be read or too few returns exist, so a
    caller can fall back explicitly instead of silently using a stale number.
    """
    try:
        rows = bp.candles(symbol, interval, lookback_bars)
    except Exception:  # noqa: BLE001 - a venue read failure must not crash a cycle
        return None
    returns = close_to_close_returns(rows)
    if len(returns) < 2:
        return None

    ordered = sorted(returns)
    if len(ordered) >= MIN_SAMPLES_FOR_QUANTILE:
        idx = max(0, min(len(ordered) - 1, int(quantile * len(ordered))))
        value = ordered[idx]
        method = (
            f"empirical {quantile:.0%} lower-tail quantile of {interval} close-to-close "
            f"returns over the last {len(ordered)} bars (realised, not forecast)"
        )
    else:
        value = ordered[0]
        method = (
            f"sample minimum of {interval} close-to-close returns over the last "
            f"{len(ordered)} bars; too few samples for a {quantile:.0%} quantile"
        )

    return ShockEstimate(
        symbol=symbol,
        shock_pct=round(value, 6),
        method=method,
        samples=len(ordered),
        interval=interval,
        lookback_bars=lookback_bars,
        source=(
            f"venue /api/v3/market/candles category=SPOT symbol={symbol} "
            f"interval={interval} limit={lookback_bars}"
        ),
    )


def crypto_proxy_symbol(futures_positions: list) -> str:
    """The symbol whose history represents the crypto leg.

    Uses the largest non-stock position by notional so the shock is anchored to
    an instrument the book actually holds. Returns an empty string when the book
    has no crypto exposure, so no shock is invented.
    """
    crypto = [p for p in futures_positions or [] if getattr(p, "asset_class", "crypto") != "stock"]
    if not crypto:
        return ""
    biggest = max(crypto, key=lambda p: abs(getattr(p, "notional", 0.0)))
    return str(getattr(biggest, "symbol", "") or "")
