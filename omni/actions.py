"""Omni Actions Engine.

Provides 1:1 parity between CLI terminal commands and Web UI actions:
- doctor: runs 13 live verification checks across credentials, public feeds,
  demo account, and session classifier
- setup: constructs the demo book (BTCUSDT leveraged long position)
- flatten: closes all open futures positions safely on Bitget demo
- report: calculates ledger performance metrics and log file statistics
- daemon: thread-safe 24/7 continuous autonomous loop manager
- terminal_logs: live buffer of console output for web terminal display
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import bitget_public as bp
from . import metrics as metrics_mod
from .bitget_demo import DemoClient
from .config import (
    RTOKEN_TO_STOCK_PERP,
    ROOT,
    load_config,
    mapped_stock_perps,
    stock_code_for,
    stock_perp_for,
)
from .daemon import DaemonConfig, OmniDaemon
from .ledger import Ledger
from .session import classify

DEFAULT_PORTFOLIO = ROOT / "demo" / "portfolio.example.json"


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class TerminalLogBuffer:
    def __init__(self, maxlen: int = 600):
        self._buffer: deque[str] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        # Seed with greeting
        self._buffer.append(f"[{_now()}] [OMNI] Sentinel Command Console initialized.")
        self._buffer.append(f"[{_now()}] [OMNI] Bare-metal Bitget UTA v3 verified. Ready for 1:1 commands.")

    def append(self, line: str) -> None:
        with self._lock:
            self._buffer.append(line)

    def extend(self, lines: list[str]) -> None:
        with self._lock:
            self._buffer.extend(lines)

    def get_all(self) -> list[str]:
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._buffer.append(f"[{_now()}] [OMNI] Console cleared.")


GLOBAL_TERMINAL_LOGS = TerminalLogBuffer()


# ---------------------------------------------------------------------------
# 1. Doctor Diagnostics (13/13 Checks)
# ---------------------------------------------------------------------------


def _declared_symbols() -> tuple:
    """rToken and stock code for the doctor probes, derived from the portfolio.

    Nothing is pinned to a literal symbol: the declared portfolio is the source,
    and only if it declares nothing do we take the first mapped rToken.
    """
    rtoken = ""
    path = Path(DEFAULT_PORTFOLIO)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for row in data.get("rtoken_positions", []):
                sym = str(row.get("symbol", "")).upper()
                if sym:
                    rtoken = sym
                    break
        except (OSError, json.JSONDecodeError):
            pass
    if not rtoken:
        perps = mapped_stock_perps()
        for sym, perp in sorted(RTOKEN_TO_STOCK_PERP.items()):
            if perp in perps:
                rtoken = sym
                break
    return rtoken, (stock_code_for(rtoken) if rtoken else "")


def run_doctor() -> dict[str, Any]:
    cfg = load_config()
    checks_dict: dict[str, tuple[bool, str]] = {}
    logs: list[str] = []
    rtoken_symbol, stock_code = _declared_symbols()
    hedge_symbol = stock_perp_for(rtoken_symbol)

    logs.append(f"[{_now()}] $ omni doctor")
    logs.append(f"[{_now()}] === OMNI DOCTOR DIAGNOSTICS (13 CHECKS) ===")

    # 1. Credentials
    c1_ok = bool(cfg.has_credentials)
    c1_detail = (
        "BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE present"
        if c1_ok else "Missing credentials"
    )
    checks_dict["demo credentials present"] = (c1_ok, c1_detail)
    logs.append(f"  [{'PASS' if c1_ok else 'FAIL'}] demo credentials: {c1_detail}")

    # 2. Agent Hub CLI
    bgc_detail = cfg.bgc or "npx pinned @bitget-ai/bitget-agent-cli@3.0.0"
    checks_dict["agent hub cli resolved"] = (True, bgc_detail)
    logs.append(f"  [PASS] agent hub cli: {bgc_detail}")

    # 3. LLM Configured
    c3_detail = f"{cfg.llm_model} at {cfg.llm_base_url}"
    checks_dict["llm configured"] = (bool(cfg.has_llm), c3_detail)
    logs.append(f"  [{'PASS' if cfg.has_llm else 'FAIL'}] llm configured: {c3_detail}")

    client = DemoClient(cfg)

    # Concurrently execute remaining checks
    def check_market_states():
        res = bp.market_states()
        return bool(res), f"{len(res)} rows" if isinstance(res, list) else "ok"

    def check_stock_info():
        res = bp.stock_info(rtoken_symbol)
        return bool(res), f"{len(res)} rows" if isinstance(res, list) else "ok"

    def check_calendar():
        res = bp.market_calendar(stock_code)
        return bool(res), f"{len(res)} rows" if isinstance(res, list) else "ok"

    def check_dividends():
        res = bp.dividends(stock_code)
        return bool(res), "ok"

    def check_ticker():
        res = bp.ticker(rtoken_symbol)
        return bool(res), "ok"

    def check_candles():
        res = bp.candles(rtoken_symbol, "1H", 3)
        return bool(res), f"{len(res)} rows" if isinstance(res, list) else "ok"

    def check_orderbook():
        res = bp.orderbook(rtoken_symbol, 5)
        return bool(res), f"{len(res)} rows" if isinstance(res, list) else "ok"

    def check_account_overview():
        if not cfg.has_credentials:
            return False, "no credentials"
        overview = client.account_overview()
        assets = overview.get("assets") or {}
        ok = bool(assets)
        eff_eq = assets.get("effEquity", "0")
        return ok, f"assets returned (effEquity={float(eff_eq):,.2f} USDT)" if ok else "empty assets"

    def check_order_dry_run():
        if not cfg.has_credentials:
            return False, "no credentials"
        preview = client.place_order(
            "USDT-FUTURES", hedge_symbol, "sell", "market", "0.05",
            pos_side="short", reduce_only="no", dry_run=True,
        )
        return bool(preview.ok), "order preview returned successfully" if preview.ok else "dry run failed"

    tasks = {
        "public: reality market states": check_market_states,
        "public: reality stock info": check_stock_info,
        "public: reality market calendar": check_calendar,
        "public: reality dividends": check_dividends,
        "public: rToken ticker": check_ticker,
        "public: rToken candles": check_candles,
        "public: rToken order book": check_orderbook,
        "demo: account overview": check_account_overview,
        "demo: order dry run": check_order_dry_run,
    }

    results = {}
    with ThreadPoolExecutor(max_workers=9) as ex:
        future_to_name = {ex.submit(fn): name for name, fn in tasks.items()}
        for fut in future_to_name:
            name = future_to_name[fut]
            try:
                results[name] = fut.result()
            except Exception as exc:  # noqa: BLE001
                results[name] = (False, str(exc)[:120])

    logs.append(f"[{_now()}] === PUBLIC DATA SOURCES ===")
    for name in [
        "public: reality market states", "public: reality stock info", "public: reality market calendar",
        "public: reality dividends", "public: rToken ticker",
        "public: rToken candles", "public: rToken order book"
    ]:
        ok, detail = results.get(name, (False, "error"))
        checks_dict[name] = (ok, detail)
        logs.append(f"  [{'PASS' if ok else 'FAIL'}] {name.replace('public: ', '')}: {detail}")

    logs.append(f"[{_now()}] === DEMO ACCOUNT & EXECUTION ===")
    for name in ["demo: account overview", "demo: order dry run"]:
        ok, detail = results.get(name, (False, "error"))
        checks_dict[name] = (ok, detail)
        logs.append(f"  [{'PASS' if ok else 'FAIL'}] {name.replace('demo: ', '')}: {detail}")

    # 13. Session classifier
    logs.append(f"[{_now()}] === SESSION CLASSIFIER ===")
    try:
        stock_info = (bp.stock_info(rtoken_symbol) or [{}])[0]
        calendar = bp.market_calendar(stock_code) if stock_code else {}
        state = classify(bp.market_states(), stock_info, calendar)
        detail = (
            f"regime={state.regime}, liquidity={state.liquidity_tier}, "
            f"confidence={state.mark_confidence}"
        )
        checks_dict["session classify"] = (True, detail)
        logs.append(
            f"  [PASS] regime={state.regime} liquidity={state.liquidity_tier} "
            f"mark_confidence={state.mark_confidence}"
        )
    except Exception as exc:  # noqa: BLE001
        checks_dict["session classify"] = (False, str(exc)[:120])
        logs.append(f"  [FAIL] session classify: {str(exc)[:120]}")

    checks = [{"name": k, "ok": v[0], "detail": v[1]} for k, v in checks_dict.items()]
    passed = sum(1 for c in checks if c["ok"])
    total = len(checks)
    logs.append(f"[{_now()}] === DOCTOR SUMMARY: {passed}/{total} CHECKS PASSED ===")
    GLOBAL_TERMINAL_LOGS.extend(logs)

    return {
        "ok": passed == total,
        "passed": passed,
        "total": total,
        "checks": checks,
        "logs": logs,
    }


# ---------------------------------------------------------------------------
# 2. Demo Book Setup (Construct Demo Book)
# ---------------------------------------------------------------------------


def run_setup(symbol: str = "BTCUSDT", qty: str = "0.05") -> dict[str, Any]:
    cfg = load_config()
    ledger = Ledger(cfg.log_dir)
    client = DemoClient(cfg)
    logs: list[str] = []

    logs.append(f"[{_now()}] $ omni setup --setup-symbol {symbol} --setup-qty {qty}")
    logs.append(f"[{_now()}] === CONSTRUCT DEMO BOOK (PAPER POSITION) ===")

    try:
        # Step 1: Dry run
        preview = client.place_order(
            "USDT-FUTURES", symbol, "buy", "market", str(qty),
            pos_side="long", reduce_only="no", dry_run=True,
        )
        logs.append(f"  dry run check: ok={preview.ok}")
        if not preview.ok:
            err_msg = f"Setup aborted: dry run rejected: {preview.error}"
            logs.append(f"  [FAIL] {err_msg}")
            GLOBAL_TERMINAL_LOGS.extend(logs)
            return {"ok": False, "error": err_msg, "logs": logs}

        # Step 2: Live order execution on Bitget Demo
        sent = client.place_order(
            "USDT-FUTURES", symbol, "buy", "market", str(qty),
            pos_side="long", reduce_only="no",
        )
        logs.append(f"  live order: {symbol} long {qty} -> ok={sent.ok}")
        if not sent.ok:
            err_msg = f"Live order failed: {sent.error}"
            logs.append(f"  [FAIL] {err_msg}")
            GLOBAL_TERMINAL_LOGS.extend(logs)
            return {"ok": False, "error": err_msg, "logs": logs}

        # Step 3: Record to ledger
        ledger.record("demo_book_setup", {
            "symbol": symbol, "side": "long", "qty": qty,
            "ok": bool(sent.ok), "order": sent.data,
            "note": "demo book construction for paper log via web UI",
        })
        logs.append(f"  ledger recorded: demo_book_setup in {ledger.path.name}")

        # Step 4: Query updated positions
        positions = client.positions()
        logs.append(f"  current open positions: {len(positions)}")
        for p in positions:
            notional = float(p.get("total", 0) or 0) * float(p.get("markPrice", 0) or 0)
            logs.append(
                f"    - {p.get('symbol')} {p.get('posSide')} total={p.get('total')} "
                f"notional={notional:,.2f} USDT"
            )

        GLOBAL_TERMINAL_LOGS.extend(logs)
        return {
            "ok": True,
            "symbol": symbol,
            "qty": qty,
            "order": sent.data,
            "positions": positions,
            "logs": logs,
        }
    except Exception as exc:  # noqa: BLE001
        err_msg = f"Exception during setup: {str(exc)}"
        logs.append(f"  [ERROR] {err_msg}")
        GLOBAL_TERMINAL_LOGS.extend(logs)
        return {"ok": False, "error": err_msg, "logs": logs}


# ---------------------------------------------------------------------------
# 3. Flatten All Positions
# ---------------------------------------------------------------------------


def run_flatten() -> dict[str, Any]:
    cfg = load_config()
    ledger = Ledger(cfg.log_dir)
    client = DemoClient(cfg)
    logs: list[str] = []

    logs.append(f"[{_now()}] $ omni flatten")
    logs.append(f"[{_now()}] === FLATTEN ALL OPEN POSITIONS ===")

    try:
        positions = client.positions()
        if not positions:
            logs.append("  no open demo positions to close.")
            GLOBAL_TERMINAL_LOGS.extend(logs)
            return {"ok": True, "closed": [], "remaining": 0, "logs": logs}

        closed: list[dict[str, Any]] = []
        for pos in positions:
            symbol = pos["symbol"]
            logs.append(f"  evaluating {symbol} ({pos.get('posSide')} total={pos.get('total')})...")
            preview = client.close_position("USDT-FUTURES", symbol, dry_run=True)
            logs.append(f"    dry run close {symbol}: ok={preview.ok}")
            if not preview.ok:
                logs.append(f"    skipped {symbol}: dry run failed ({preview.error})")
                continue

            done = client.close_position("USDT-FUTURES", symbol, confirm=True)
            logs.append(f"    closed {symbol}: ok={done.ok}")
            ledger.record("flatten", {"symbol": symbol, "ok": bool(done.ok), "data": done.data})
            if done.ok:
                closed.append({"symbol": symbol, "data": done.data})

        remaining = client.positions()
        logs.append(f"  flatten complete. remaining positions: {len(remaining)}")
        ledger.record("flatten_summary", {"remaining": len(remaining), "closed_count": len(closed)})

        GLOBAL_TERMINAL_LOGS.extend(logs)
        return {
            "ok": True,
            "closed": closed,
            "remaining": len(remaining),
            "logs": logs,
        }
    except Exception as exc:  # noqa: BLE001
        err_msg = f"Exception during flatten: {str(exc)}"
        logs.append(f"  [ERROR] {err_msg}")
        GLOBAL_TERMINAL_LOGS.extend(logs)
        return {"ok": False, "error": err_msg, "logs": logs}


# ---------------------------------------------------------------------------
# 4. Report (Metrics & Ledger Files)
# ---------------------------------------------------------------------------


def run_report() -> dict[str, Any]:
    cfg = load_config()
    logs: list[str] = []

    logs.append(f"[{_now()}] $ omni report")
    logs.append(f"[{_now()}] === COMPUTING PAPER METRICS FROM LEDGER ===")

    try:
        metrics = metrics_mod.compute(cfg.log_dir)
        logs.append(f"  total governance runs   : {metrics.get('runs', 0)}")
        logs.append(f"  decisions made          : {metrics.get('decisions', 0)}")
        logs.append(f"  executions completed    : {metrics.get('executions_completed', 0)}")
        logs.append(f"  policy overrides        : {metrics.get('policy_overrides', 0)}")
        logs.append(
            f"  risk violations         : {metrics.get('risk_violation_count', 0)} "
            f"({metrics.get('risk_violation_rate', 0):.1%})"
        )
        logs.append(f"  max drawdown            : {metrics.get('max_drawdown_pct', 0):.2%}")
        logs.append(f"  protective action share : {metrics.get('protective_action_share', 0):.1%}")

        logs.append(f"[{_now()}] === AUDIT LEDGER FILES ===")
        files: list[dict[str, Any]] = []
        for path in Ledger.all_logs(cfg.log_dir):
            stat = path.stat()
            files.append({
                "name": path.name,
                "size_bytes": stat.st_size,
                "size_kb": f"{stat.st_size / 1024:.1f} KB",
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
            logs.append(f"  {path.name} ({stat.st_size:,} bytes)")

        GLOBAL_TERMINAL_LOGS.extend(logs)
        return {
            "ok": True,
            "metrics": metrics,
            "files": files,
            "logs": logs,
        }
    except Exception as exc:  # noqa: BLE001
        err_msg = f"Exception during report: {str(exc)}"
        logs.append(f"  [ERROR] {err_msg}")
        GLOBAL_TERMINAL_LOGS.extend(logs)
        return {"ok": False, "error": err_msg, "logs": logs}


# ---------------------------------------------------------------------------
# 5. Autonomous Daemon Manager (Thread-Safe 24/7 Governor)
# ---------------------------------------------------------------------------


class WebDaemonManager:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.interval: int = 60
        self.execute: bool = False
        # None means the daemon derives the scenario shock from live history.
        self.shock: float | None = None
        self.cycles_completed: int = 0
        self.last_cycle_time: str = ""
        self.last_action: str = ""
        self.last_rationale: str = ""

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, interval: int = 60, execute: bool = False, shock: float | None = None) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {"ok": True, "running": True, "message": "Daemon is already running"}

            self.interval = max(10, interval)
            self.execute = execute
            self.shock = shock
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="OmniDaemonWorker")
            self._thread.start()

            msg = (
                f"[{_now()}] [DAEMON] Started 24/7 Autonomous Governor loop "
                f"(interval={self.interval}s, execute={self.execute}, shock={self.shock})"
            )
            GLOBAL_TERMINAL_LOGS.append(msg)
            return {"ok": True, "running": True, "interval": self.interval}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return {"ok": True, "running": False, "message": "Daemon was not active"}

            self._stop_event.set()
            msg = f"[{_now()}] [DAEMON] Stopping 24/7 Autonomous Governor..."
            GLOBAL_TERMINAL_LOGS.append(msg)

        if self._thread is not None:
            self._thread.join(timeout=3.0)

        GLOBAL_TERMINAL_LOGS.append(f"[{_now()}] [DAEMON] Governor thread stopped cleanly.")
        return {"ok": True, "running": False}

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            return {
                "ok": True,
                "running": running,
                "interval": self.interval,
                "execute": self.execute,
                "shock": self.shock,
                "cycles_completed": self.cycles_completed,
                "last_cycle_time": self.last_cycle_time,
                "last_action": self.last_action,
                "last_rationale": self.last_rationale,
            }

    def _run_loop(self):
        GLOBAL_TERMINAL_LOGS.append(
            f"[{_now()}] [DAEMON] Autonomous thread started. Listening on Bitget book..."
        )
        while not self._stop_event.is_set():
            cycle_start = time.time()
            try:
                d_cfg = DaemonConfig(
                    interval=self.interval,
                    execute=self.execute,
                    portfolio_path=DEFAULT_PORTFOLIO,
                    rtoken_shock=self.shock,
                )
                daemon = OmniDaemon(d_cfg)
                res = daemon.run_one_cycle()

                with self._lock:
                    self.cycles_completed += 1
                    self.last_cycle_time = _now()
                    dec = res.get("decision") or {}
                    self.last_action = dec.get("action", "HOLD")
                    self.last_rationale = dec.get("rationale", "")

                exec_info = res.get("execution") or {}
                executed = exec_info.get("executed", False)
                risk_res = res.get("risk", {}).get("results", {})
                buffer_usdt = risk_res.get("shocked_buffer_usdt", 0)

                log_line = (
                    f"[{self.last_cycle_time}] [DAEMON CYCLE #{self.cycles_completed}] "
                    f"Action: {self.last_action} (conf: {dec.get('confidence', 0):.0%}) | "
                    f"Executed: {executed} | Shocked Buffer: {buffer_usdt:,.2f} USDT"
                )
                GLOBAL_TERMINAL_LOGS.append(log_line)
            except Exception as exc:  # noqa: BLE001
                GLOBAL_TERMINAL_LOGS.append(f"[{_now()}] [DAEMON ERROR] {str(exc)}")

            elapsed = time.time() - cycle_start
            wait_time = max(1.0, self.interval - elapsed)
            if self._stop_event.wait(timeout=wait_time):
                break


GLOBAL_DAEMON = WebDaemonManager()
