"""Public Bitget market and Reality (rToken) data.

Every call here is a public production endpoint. These calls must never carry
the ``paptrading`` header: the demo service does not serve ``reality/*`` routes
and returns 404 when the header is present.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import BITGET_REST, USER_AGENT


class BitgetDataError(RuntimeError):
    pass


def _get(path: str, params: dict | None = None, timeout: int = 30, retries: int = 3) -> Any:
    url = BITGET_REST + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last: Exception | None = None
    payload = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode())
            break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="ignore")[:200]
            last = BitgetDataError(f"GET {path} -> HTTP {exc.code} {body}")
            # 429 and 5xx are retryable; other 4xx responses are not.
            if exc.code != 429 and exc.code < 500:
                raise last
            time.sleep(1.5 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001 - network surface
            last = BitgetDataError(f"GET {path} -> {exc}")
            time.sleep(1.5 * (attempt + 1))
    else:
        raise last if last else BitgetDataError(f"GET {path} failed")

    if not isinstance(payload, dict) or payload.get("code") != "00000":
        raise BitgetDataError(f"GET {path} -> unexpected payload {str(payload)[:200]}")
    return payload.get("data")


# --- Reality (rToken) reference and corporate-action data -------------------


def market_states(timeout: int = 30) -> dict:
    """US session windows: pre_market, regular, after_hours."""
    return _get("/api/v3/reality/market/states", timeout=timeout)


def stock_info(symbol: str, timeout: int = 30) -> list:
    """Per-symbol rToken info: underlying code, trading periods, weekend flag."""
    return _get(
        "/api/v3/reality/market/stock-info", {"symbol": symbol}, timeout=timeout
    )


def market_calendar(code: str, timeout: int = 30) -> dict:
    """Holiday and closure windows for the underlying stock code."""
    return _get("/api/v3/reality/market/calendar", {"code": code}, timeout=timeout)


def dividends(code: str, timeout: int = 30) -> dict:
    """Dividend events: announcement, record, ex-rights and payment dates."""
    return _get("/api/v3/reality/market/dividends", {"code": code}, timeout=timeout)


def company_overview(code: str, timeout: int = 30) -> dict:
    """Company reference data for the underlying stock code."""
    return _get(
        "/api/v3/reality/market/company-overview", {"code": code}, timeout=timeout
    )


# --- rToken market data -----------------------------------------------------


def ticker(symbol: str, timeout: int = 30) -> dict:
    rows = _get(
        "/api/v3/market/tickers", {"category": "SPOT", "symbol": symbol}, timeout=timeout
    )
    if not rows:
        raise BitgetDataError(f"no ticker for {symbol}")
    return rows[0]


def candles(symbol: str, interval: str = "1H", limit: int = 24, timeout: int = 30) -> list:
    return _get(
        "/api/v3/market/candles",
        {"category": "SPOT", "symbol": symbol, "interval": interval, "limit": limit},
        timeout=timeout,
    )


def orderbook(symbol: str, limit: int = 20, timeout: int = 30) -> dict:
    """Level-2 depth. Returns {'a': [[price, size], ...], 'b': [...], 'ts': str}."""
    return _get(
        "/api/v3/market/orderbook",
        {"category": "SPOT", "symbol": symbol, "limit": limit},
        timeout=timeout,
    )
