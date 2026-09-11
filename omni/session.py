"""Session regime classification built on real Bitget Reality data.

Inputs are observed Bitget payloads, not assumptions:

* ``/reality/market/states``        session windows (pre_market, regular, after_hours)
* ``/reality/market/stock-info``    per-symbol trading periods and weekend flag
* ``/reality/market/calendar``      holiday and closure windows

The classifier yields the current regime plus an explicit mark-confidence tier,
which is what the risk model uses instead of trusting a stale price.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

# Assumption, stated openly: Bitget publishes window clocks with timeZone "EST".
# We interpret those clocks as New York local time so daylight saving is handled
# by the tz database instead of being hard coded.
CLOCK_TZ_NOTE = "Bitget window clocks interpreted as America/New_York local time"

LIQUIDITY_TIER = {
    "regular": "deep",
    "pre_market": "thin",
    "after_hours": "thin",
    "overnight": "thinnest",
    "weekend_tradable": "thinnest",
    "weekend_frozen": "none",
    "holiday": "none",
    "closed": "none",
}

MARK_CONFIDENCE = {
    "regular": "high",
    "pre_market": "medium",
    "after_hours": "medium",
    "overnight": "low",
    "weekend_tradable": "low",
    "weekend_frozen": "stale",
    "holiday": "stale",
    "closed": "stale",
}


@dataclass
class SessionState:
    as_of_utc: str
    as_of_new_york: str
    weekday: str
    is_weekend: bool
    regime: str
    liquidity_tier: str
    mark_confidence: str
    cash_market_open: bool
    weekend_tradable: bool
    in_holiday_window: bool
    trading_periods: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_clock(value: str) -> time | None:
    try:
        hh, mm = value.strip().split(":")
        return time(int(hh), int(mm))
    except Exception:  # noqa: BLE001
        return None


def _holiday_window(now_ny: datetime, calendar: dict) -> tuple[bool, str | None]:
    """Return whether now falls inside a published closure window."""
    if not calendar:
        return False, None
    for entry in calendar.get("specificConfig") or []:
        start_raw = entry.get("startTime")
        end_raw = entry.get("endTime")
        if not start_raw or not end_raw:
            continue
        try:
            start = datetime.strptime(start_raw, "%Y-%m-%d %H:%M").replace(tzinfo=NY)
            end = datetime.strptime(end_raw, "%Y-%m-%d %H:%M").replace(tzinfo=NY)
        except ValueError:
            continue
        if start <= now_ny <= end:
            remark = entry.get("remark") or f"{start_raw} to {end_raw}"
            return True, remark
    return False, None


def _in_window(now_ny: datetime, start: time, end: time) -> bool:
    """Window match that also handles windows spanning midnight."""
    if start <= end:
        return start <= now_ny.time() <= end
    return now_ny.time() >= start or now_ny.time() <= end


def classify(
    states: dict,
    stock: dict | None,
    calendar: dict | None,
    now: datetime | None = None,
) -> SessionState:
    now_utc = (now or datetime.now(tz=ZoneInfo("UTC"))).astimezone(ZoneInfo("UTC"))
    now_ny = now_utc.astimezone(NY)

    trading_periods = list((stock or {}).get("tradingPeriod") or [])
    weekend_tradable = str((stock or {}).get("weekendTradable", "")).lower() == "yes"

    in_holiday, holiday_note = _holiday_window(now_ny, calendar or {})
    is_weekend_now = now_ny.weekday() >= 5

    # Order matters. The US cash market is always closed at the weekend, so the
    # weekend regime is evaluated before the published weekday clocks, which
    # would otherwise report "regular" on a Saturday afternoon. Holidays are
    # explicit closures and are evaluated before the clocks too.
    if is_weekend_now:
        regime = "weekend_tradable" if weekend_tradable else "weekend_frozen"
    elif in_holiday:
        regime = "holiday"
    else:
        regime = "closed"
        for window in (states or {}).get("stateList") or []:
            start = _parse_clock(str(window.get("startTime", "")))
            end = _parse_clock(str(window.get("endTime", "")))
            state = str(window.get("state", "")).strip()
            if start is None or end is None or not state:
                continue
            if _in_window(now_ny, start, end):
                regime = state
                break
        if regime == "closed" and "overnight" in trading_periods:
            regime = "overnight"

    notes = [CLOCK_TZ_NOTE]
    if in_holiday:
        notes.append(f"closure window active: {holiday_note}")
    if is_weekend_now:
        notes.append(
            "weekend: underlying cash market closed, rToken marks are low confidence"
            if weekend_tradable
            else "weekend: underlying cash market closed and symbol is not weekend tradable"
        )

    cash_open = regime == "regular"

    return SessionState(
        as_of_utc=now_utc.isoformat(timespec="seconds"),
        as_of_new_york=now_ny.isoformat(timespec="seconds"),
        weekday=now_ny.strftime("%A"),
        is_weekend=now_ny.weekday() >= 5,
        regime=regime,
        liquidity_tier=LIQUIDITY_TIER.get(regime, "unknown"),
        mark_confidence=MARK_CONFIDENCE.get(regime, "unknown"),
        cash_market_open=cash_open,
        weekend_tradable=weekend_tradable,
        in_holiday_window=in_holiday,
        trading_periods=trading_periods,
        notes=notes,
    )
