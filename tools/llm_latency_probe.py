import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omni import llm as llm_mod
from omni.config import load_config
from omni.collateral import RTokenPosition
from omni.risk import FuturesPosition, evaluate
from omni.session import SessionState

cfg = load_config()

btc = FuturesPosition("BTCUSDT", "long", 2.0, 76_973.0, 76_973.0, -12.0, 0.004, 20.0,
                      asset_class="crypto")
risk = evaluate(
    as_of="2026-09-11T11:00:00+00:00",
    observed_effective_equity=96_111.53,
    rtoken_positions=[RTokenPosition("RNVDAUSDT", "NVDA", 500, 219.4)],
    rtoken_marks={"RNVDAUSDT": 220.16},
    futures_positions=[btc],
    haircut_pct=0.15,
    rtoken_shock_pct=-0.08,
    crypto_shock_pct=-0.25,
    hedge_symbol="NVDAUSDT",
).to_dict()

session = SessionState(
    as_of_utc="2026-09-11T11:00:00+00:00",
    as_of_new_york="2026-09-11T07:00:00-04:00",
    weekday="Friday", is_weekend=False, regime="pre_market",
    liquidity_tier="thin", mark_confidence="medium", cash_market_open=False,
    weekend_tradable=True, in_holiday_window=False,
    trading_periods=["overnight", "pre_market", "regular", "after_hours"],
).to_dict()

compact = llm_mod.compact_state(risk, session)
print("compact payload chars:", len(json.dumps(compact)))
print("full risk state chars:", len(json.dumps(risk)))

for attempt in (1, 2):
    started = time.time()
    d = llm_mod.decide(risk, session, cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model,
                       fallback_model=cfg.llm_fallback_model)
    print(
        f"attempt {attempt}: model={d.model} fallback={d.used_fallback} "
        f"wall={time.time() - started:.1f}s reported_latency={d.latency_ms}ms "
        f"action={d.action} tokens={d.prompt_tokens}/{d.completion_tokens}"
    )
    print("  rationale:", d.rationale[:200])
