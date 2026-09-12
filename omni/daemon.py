"""Continuous Autonomous Daemon for Omni.

Runs 24/7/365 to guard a Bitget Unified Trading Account (UTA v3),
monitoring cross-asset margin, detecting session regime changes,
and autonomously executing protective actions when risk thresholds are breached.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import bitget_public as bp
from . import collateral as coll
from . import executor as exec_mod
from . import llm as llm_mod
from . import metrics as metrics_mod
from .bitget_demo import DemoClient, DemoCliError
from .collateral import RTokenPosition
from .config import ROOT, load_config, stock_perp_for
from .ledger import Ledger
from .venue_risk import (
    effective_order_cap,
    next_tier_above,
    query_haircut,
    query_instrument_caps,
    query_max_open,
    query_mmr_tiers,
)

DEFAULT_PORTFOLIO = ROOT / "demo" / "portfolio.example.json"
from .policy import PolicyConfig, validate
from .risk import FuturesPosition, evaluate, shock_for
from .session import classify


@dataclass
class DaemonConfig:
    interval: int = 60
    execute: bool = False
    max_iterations: int | None = None
    portfolio_path: Path = DEFAULT_PORTFOLIO
    rtoken: str = "RNVDAUSDT"
    haircut: float = 0.15
    haircut_source: str = ""
    rtoken_shock: float = -0.04
    crypto_shock: float = -0.06
    max_hedge_notional: float = 5_000.0


class OmniDaemon:
    def __init__(self, config: DaemonConfig):
        self.d_cfg = config
        self.app_cfg = load_config()
        self.ledger = Ledger(self.app_cfg.log_dir)
        self.client = DemoClient(self.app_cfg)
        self._running = False
        self._iteration = 0
        self._last_regime = None

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def stop(self, *args):
        print(f"\n[{self._now_iso()}] [DAEMON] Shutdown signal received. Stopping gracefully...")
        self._running = False

    def _stock_perp_symbols(self) -> set:
        """Symbols in the demo futures universe whose instrument type is stock.

        Mirrors the CLI implementation: a stock perpetual takes the equity gap
        shock, a crypto perpetual takes the crypto shock. Hardcoding two names
        misclassifies every other stock perp and misprices the cross-asset book.
        """
        try:
            result = self.client.call(
                ["market", "--action", "instruments", "--category", "USDT-FUTURES"],
                allow_failure=True,
            )
            rows = result.data
            if isinstance(rows, dict):
                rows = rows.get("list") or []
            if not isinstance(rows, list):
                return set()
            return {
                str(r.get("symbol", "")).upper()
                for r in rows
                if isinstance(r, dict) and r.get("symbolType") == "stock"
            }
        except Exception:  # noqa: BLE001
            return set()

    def run_one_cycle(self) -> dict:
        self._iteration += 1
        now_str = self._now_iso()
        print(f"\n=======================================================")
        print(f"[{now_str}] [DAEMON CYCLE #{self._iteration}] Mode={'EXECUTE' if self.d_cfg.execute else 'MONITOR'}")
        print(f"=======================================================")

        # 1. Session & Calendar Intake
        stock_rows = bp.stock_info(self.d_cfg.rtoken) or [{}]
        stock = stock_rows[0] if stock_rows else {}
        code = stock.get("code") or "NVDA"
        calendar = bp.market_calendar(code)
        session = classify(bp.market_states(), stock, calendar)

        regime_changed = (self._last_regime is not None and self._last_regime != session.regime)
        if regime_changed:
            print(f"  [ALERT] Session regime transition: {self._last_regime} -> {session.regime}!")
            self.ledger.record("regime_transition", {
                "from": self._last_regime,
                "to": session.regime,
                "timestamp": now_str,
            })
        self._last_regime = session.regime

        print(f"  Session: {session.regime} (liquidity: {session.liquidity_tier}, confidence: {session.mark_confidence})")

        # 2. Market Data
        portfolio_data = {}
        if self.d_cfg.portfolio_path.exists():
            with open(self.d_cfg.portfolio_path, "r", encoding="utf-8") as f:
                portfolio_data = json.load(f)

        marks: dict[str, float] = {}
        books: dict = {}
        for row in portfolio_data.get("rtoken_positions", []):
            sym = row["symbol"]
            try:
                tick = bp.ticker(sym)
                marks[sym] = float(tick["lastPrice"])
                books[sym] = bp.orderbook(sym, 10)
                print(f"  rToken: {sym} = {marks[sym]:,.2f} USDT")
            except Exception as e:
                print(f"  [WARN] Failed fetching ticker for {sym}: {e}")

        # Tradable stock perpetual reference
        hedge_marks = {}
        for sym in ("NVDAUSDT", "TSLAUSDT", "AAPLUSDT", "GOOGLUSDT"):
            try:
                tick = self.client.call(
                    ["market", "--action", "tickers", "--category", "USDT-FUTURES", "--symbol", sym],
                    allow_failure=True,
                )
                rows = tick.data if isinstance(tick.data, list) else []
                if rows:
                    hedge_marks[sym] = float(rows[0]["lastPrice"])
            except Exception:
                continue

        # 3. Account State
        overview = self.client.account_overview()
        assets = overview.get("assets") or {}
        eff_equity = float(assets.get("effEquity") or 0.0)
        margin_ratio = float(assets.get("mgnRatio") or 0.0)
        raw_positions = self.client.positions()
        stock_perps = self._stock_perp_symbols()

        print(f"  Account: Equity = {eff_equity:,.2f} USDT | Margin Ratio = {margin_ratio:.4f} | Open Positions = {len(raw_positions)}")

        futures = []
        for p in raw_positions:
            futures.append(
                FuturesPosition(
                    symbol=p["symbol"],
                    pos_side=p.get("posSide", "long"),
                    total=float(p.get("total") or 0.0),
                    mark_price=float(p.get("markPrice") or 0.0),
                    avg_price=float(p.get("avgPrice") or 0.0),
                    unrealised_pnl=float(p.get("unrealisedPnl") or 0.0),
                    mmr=float(p.get("mmr") or 0.0),
                    leverage=float(p.get("leverage") or 0.0),
                    asset_class="stock" if p["symbol"].upper() in stock_perps else "crypto",
                )
            )

        # 4. Stress & Risk Evaluation
        rtoken_positions = [
            RTokenPosition(
                symbol=r["symbol"],
                code=r.get("code", ""),
                qty=float(r["qty"]),
                avg_price=float(r.get("avg_price", 0.0)),
            )
            for r in portfolio_data.get("rtoken_positions", [])
        ]
        hedge_symbol = stock_perp_for(self.d_cfg.rtoken)

        # 4a. Venue-published parameters: haircut from the discount-rate
        # schedule, per-symbol MMR tiers, and instrument caps. Each replaces a
        # modelled value with the exchange's own number, and each records its
        # source. On a failed venue read we keep the explicit input and say so.
        haircut_pct = self.d_cfg.haircut
        haircut_source = self.d_cfg.haircut_source or "explicit --haircut input"
        rtoken_holding_value = sum(
            r["qty"] * marks.get(r["symbol"], r.get("avg_price") or 0.0)
            for r in portfolio_data.get("rtoken_positions", [])
        )
        quote = query_haircut(self.client, self.d_cfg.rtoken, rtoken_holding_value)
        if quote is not None:
            haircut_pct = quote.haircut_pct
            haircut_source = quote.source

        mmr_tiers = query_mmr_tiers(self.client, hedge_symbol)
        instrument_caps = query_instrument_caps(self.client, hedge_symbol)
        max_open = query_max_open(self.client, hedge_symbol, "sell")
        post_hedge_band = next_tier_above(mmr_tiers, sum(
            abs(f.total) * f.mark_price for f in futures if f.symbol == hedge_symbol
        ))

        risk = evaluate(
            as_of=datetime.now(timezone.utc),
            observed_effective_equity=eff_equity,
            rtoken_positions=rtoken_positions,
            rtoken_marks=marks,
            futures_positions=futures,
            haircut_pct=haircut_pct,
            rtoken_shock_pct=self.d_cfg.rtoken_shock,
            crypto_shock_pct=self.d_cfg.crypto_shock,
            hedge_symbol=hedge_symbol,
        )
        rd = risk.to_dict()
        rd["modelled"]["haircut_source"] = haircut_source
        rd["modelled"]["haircut_input"] = self.d_cfg.haircut
        if mmr_tiers:
            rd["modelled"]["mmr_tiers_source"] = (
                f"venue /api/v3/market/position-tier symbol={hedge_symbol} bands={len(mmr_tiers)}"
            )
            if post_hedge_band is not None:
                rd["modelled"]["post_hedge_tier"] = {
                    "tier": post_hedge_band.tier,
                    "min_usdt": post_hedge_band.min_usdt,
                    "mmr": post_hedge_band.mmr,
                    "max_leverage": post_hedge_band.max_leverage,
                }
        if instrument_caps:
            cap = effective_order_cap(instrument_caps)
            if cap > 0:
                rd["modelled"]["venue_order_cap_qty"] = cap
                rd["modelled"]["venue_order_cap_source"] = (
                    f"venue instruments symbol={hedge_symbol} maxMarketOrderQty/maxOrderQty"
                )
        if max_open:
            rd["modelled"]["venue_max_sell_open"] = max_open.get("maxSellOpen")
            rd["modelled"]["venue_max_open_source"] = max_open.get("source")

        print(f"  Risk Model: Shocked Buffer = {rd['results']['shocked_buffer_usdt']:,.2f} USDT | Breach = {rd['results']['breach']} | Needs Attention = {rd['results']['needs_attention']}")

        # 5. LLM Decision (Only when attention is needed or periodically)
        decision = llm_mod.decide(
            rd,
            session.to_dict(),
            self.app_cfg.llm_base_url,
            self.app_cfg.llm_api_key,
            self.app_cfg.llm_model,
            fallback_model=self.app_cfg.llm_fallback_model,
        )
        print(f"  AI Decision ({decision.model}): Action = {decision.action} ({decision.latency_ms}ms)")
        print(f"  Rationale: {decision.rationale[:160]}...")

        # 6. Policy Check
        policy_cfg = PolicyConfig(max_order_notional_usdt=self.d_cfg.max_hedge_notional)
        policy = validate(decision.action, decision.params, rd, session.to_dict(), policy_cfg)
        print(f"  Policy Validation: Approved = {policy.approved} | Action = {policy.action}")

        # 7. Execution
        exec_result = None
        if self.d_cfg.execute and policy.action != "HOLD" and policy.approved:
            print(f"  [EXECUTING] Sending live order for action: {policy.action}")
            exec_result = exec_mod.execute(
                policy.action,
                policy.params,
                self.client,
                hedge_marks,
                hedge_symbol=hedge_symbol,
            )
            print(f"  Execution result: ok={exec_result.executed}, reason={exec_result.reason}")
        else:
            print(f"  Execution: {policy.action} (No order required or execute=False)")

        # Record cycle to ledger
        cycle_record = {
            "cycle": self._iteration,
            "timestamp": now_str,
            "session": session.to_dict(),
            "account": {"equity": eff_equity, "margin_ratio": margin_ratio, "positions": len(futures)},
            "risk": {
                "shocked_buffer": rd["results"]["shocked_buffer_usdt"],
                "needs_attention": rd["results"]["needs_attention"],
                "breach": rd["results"]["breach"],
                "modelled": {
                    "haircut_pct": rd["modelled"].get("haircut_pct"),
                    "haircut_source": rd["modelled"].get("haircut_source"),
                    "haircut_input": rd["modelled"].get("haircut_input"),
                    "mmr_tiers_source": rd["modelled"].get("mmr_tiers_source"),
                    "post_hedge_tier": rd["modelled"].get("post_hedge_tier"),
                    "venue_order_cap_qty": rd["modelled"].get("venue_order_cap_qty"),
                    "venue_order_cap_source": rd["modelled"].get("venue_order_cap_source"),
                    "venue_max_sell_open": rd["modelled"].get("venue_max_sell_open"),
                    "venue_max_open_source": rd["modelled"].get("venue_max_open_source"),
                },
            },
            "decision": decision.to_dict(),
            "policy": policy.to_dict(),
            "execution": exec_result.to_dict() if exec_result else {"action": policy.action, "executed": False},
        }
        self.ledger.record("daemon_cycle", cycle_record)

        return cycle_record

    def start(self):
        self._running = True
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        print("===============================================================")
        print("          Omni 24/7 Autonomous Risk Governor Daemon           ")
        print("===============================================================")
        print(f"  PID               : {os.getpid()}")
        print(f"  Interval          : {self.d_cfg.interval} seconds")
        print(f"  Execution Mode    : {'LIVE PAPER TRADING' if self.d_cfg.execute else 'MONITOR ONLY (DRY-RUN)'}")
        print(f"  Portfolio File    : {self.d_cfg.portfolio_path}")
        print(f"  Ledger Directory  : {self.app_cfg.log_dir}")
        print(f"  LLM Endpoint      : {self.app_cfg.llm_base_url} ({self.app_cfg.llm_model})")
        print("===============================================================")

        self.ledger.record("daemon_start", {
            "interval": self.d_cfg.interval,
            "execute": self.d_cfg.execute,
            "pid": os.getpid(),
            "timestamp": self._now_iso(),
        })

        while self._running:
            try:
                self.run_one_cycle()
            except KeyboardInterrupt:
                break
            except Exception as exc:
                print(f"  [ERROR] Cycle #{self._iteration} failed: {exc}", file=sys.stderr)
                self.ledger.record("daemon_error", {
                    "cycle": self._iteration,
                    "error": str(exc),
                    "timestamp": self._now_iso(),
                })

            if self.d_cfg.max_iterations and self._iteration >= self.d_cfg.max_iterations:
                print(f"\n[DAEMON] Reached maximum requested iterations ({self.d_cfg.max_iterations}). Stopping.")
                break

            # Sleep in 1-second chunks for responsive SIGINT handling
            for _ in range(self.d_cfg.interval):
                if not self._running:
                    break
                time.sleep(1)

        self.ledger.record("daemon_stop", {
            "total_cycles": self._iteration,
            "timestamp": self._now_iso(),
        })
        print(f"\n[DAEMON] Stopped successfully. Completed {self._iteration} governance cycles.")
        print(f"All audit events logged to: {self.ledger.path}")


def main():
    parser = argparse.ArgumentParser(prog="omni-daemon", description="Omni 24/7 Autonomous Governor Daemon")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds (default: 60)")
    parser.add_argument("--execute", action="store_true", help="Execute live paper orders on Bitget Demo")
    parser.add_argument("--max-iterations", type=int, default=None, help="Stop after N cycles (optional)")
    parser.add_argument("--portfolio", default=str(DEFAULT_PORTFOLIO), help="Path to portfolio JSON")
    parser.add_argument("--rtoken", default="RNVDAUSDT", help="rToken symbol to monitor")
    parser.add_argument("--haircut", type=float, default=0.15, help="rToken collateral haircut (default: 0.15)")
    parser.add_argument("--rtoken-shock", type=float, default=-0.04, help="Scenario rToken shock")
    parser.add_argument("--crypto-shock", type=float, default=-0.06, help="Scenario crypto shock")
    parser.add_argument("--max-hedge-notional", type=float, default=5000.0, help="Policy cap on hedge size")

    args = parser.parse_args()

    cfg = DaemonConfig(
        interval=args.interval,
        execute=args.execute,
        max_iterations=args.max_iterations,
        portfolio_path=Path(args.portfolio),
        rtoken=args.rtoken,
        haircut=args.haircut,
        rtoken_shock=args.rtoken_shock,
        crypto_shock=args.crypto_shock,
        max_hedge_notional=args.max_hedge_notional,
    )

    daemon = OmniDaemon(cfg)
    daemon.start()


if __name__ == "__main__":
    main()
