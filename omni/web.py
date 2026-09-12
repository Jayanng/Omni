"""Live Visual Cockpit Web UI for Omni.

Crafted with the exact visual design language and architectural taste of Floor (usefloor.vercel.app):
- Deep obsidian pitch-black palette (#080808) with subtle radial glows and 1px borders
- Hero spotlight blur, top laser hairline, two-tone display typography
- Embedded dashboard frame with mini sidebar, glowing SVG sparklines, and session countdown
- Real-time polling against Bitget UTA v3 demo account and production reality feeds
- Multi-threaded HTTP server with OPTIONS CORS support
- Interactive shock stress-testing directly triggering real agent decision cycles
- Toast notification system and immediate visual feedback on all buttons
- Live cryptographic evidence ledger table reading from day-scoped JSONL logs
- 1:1 Parity Sentinel Command Deck & Live Terminal Console for every CLI command:
    omni doctor, omni setup, omni decide, omni flatten, omni report, omni daemon
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import bitget_public as bp
from .actions import (
    GLOBAL_DAEMON,
    GLOBAL_TERMINAL_LOGS,
    run_doctor,
    run_flatten,
    run_report,
    run_setup,
)
from .bitget_demo import DemoClient
from .config import ROOT, load_config
from .daemon import DaemonConfig, OmniDaemon
from .ledger import Ledger
from .session import classify

DEFAULT_PORTFOLIO = ROOT / "demo" / "portfolio.example.json"
PORT = 8080

# Multi-page console: static assets + page modules under omni/web/.
# Served at "/", hash-routed client-side. No landing page, no marketing.
_WEB_DIR = Path(__file__).resolve().parent / "web"
_STATIC_TYPES = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".html": "text/html",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}

def _read_web_file(name: str) -> bytes | None:
    """Safely read a file from the web dir. Returns None if missing or unsafe."""
    if "/" in name or ".." in name:
        return None
    p = _WEB_DIR / name
    if not p.exists() or not p.is_file():
        return None
    try:
        return p.read_bytes()
    except OSError:
        return None

_COCKPIT_PATH = Path(__file__).resolve().parent / "cockpit.html"
try:
    COCKPIT_HTML = _COCKPIT_PATH.read_text(encoding="utf-8")
except OSError:
    COCKPIT_HTML = "<!DOCTYPE html><html><body><p>cockpit.html missing</p></body></html>"




_STATUS_CACHE: dict = {
    "ok": False,
    "booting": True,
    "latest_rationale": "Status refresh worker starting; first live fetch in progress.",
    "cached_at": time.time(),
}
_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_WORKER_STARTED = False


def _status_refresh_worker():
    global _STATUS_CACHE
    while True:
        try:
            cfg = load_config()
            client = DemoClient(cfg)
            # Resolve the rToken symbol from the open book, then from the
            # config mapping. No symbol is invented: if none resolves, the
            # symbol-specific reads are skipped and the payload reports nulls,
            # which the UI renders as em dashes.
            from .config import (
                DEFAULT_HEDGE_PERP,
                RTOKEN_TO_STOCK_PERP,
                rtoken_for_stock_perp,
                stock_code_for,
            )
            positions_raw = client.positions()
            rtoken_sym = ""
            for p in (positions_raw if isinstance(positions_raw, list) else []):
                sym = str(p.get("symbol", "")).upper()
                if sym in RTOKEN_TO_STOCK_PERP:
                    rtoken_sym = sym
                    break
            if not rtoken_sym:
                rtoken_sym = rtoken_for_stock_perp(DEFAULT_HEDGE_PERP)

            with ThreadPoolExecutor(max_workers=6) as ex:
                f_states = ex.submit(bp.market_states)
                f_pos = ex.submit(lambda: positions_raw)
                f_overview = ex.submit(client.account_overview)
                f_stock = f_tick = f_cal = None
                if rtoken_sym:
                    f_stock = ex.submit(bp.stock_info, rtoken_sym)
                    f_cal = ex.submit(bp.market_calendar, stock_code_for(rtoken_sym))
                    f_tick = ex.submit(bp.ticker, rtoken_sym)

                stock = (f_stock.result() or [{}])[0] if f_stock is not None else {}
                states = f_states.result()
                cal = f_cal.result() if f_cal is not None else {}
                tick = f_tick.result() if f_tick is not None else {}
                pos = f_pos.result()
                overview = f_overview.result()

            session = classify(states, stock, cal)
            assets = overview.get("assets") or {}

            ledger = Ledger(cfg.log_dir)
            records = ledger.read_all()
            latest_rationale = ""
            for r in reversed(records):
                if r.get("kind") in ("decision", "daemon_cycle"):
                    latest_rationale = r.get("payload", {}).get("decision", {}).get("rationale", "")
                    if latest_rationale:
                        break

            payload = {
                "ok": True,
                "session": session.to_dict(),
                "rtoken_symbol": rtoken_sym or None,
                "rtoken_price": tick.get("lastPrice"),
                "equity": assets.get("effEquity"),
                "mmr": assets.get("mmr"),
                "margin_ratio": float(assets.get("mgnRatio") or 0.0),
                "positions": pos if isinstance(pos, list) else [],
                "latest_rationale": latest_rationale or "Autonomous Governor active.",
                "cached_at": time.time(),
            }
            with _STATUS_CACHE_LOCK:
                _STATUS_CACHE = payload
        except Exception:
            pass
        time.sleep(12)


def start_status_refresher():
    global _STATUS_WORKER_STARTED
    if not _STATUS_WORKER_STARTED:
        _STATUS_WORKER_STARTED = True
        t = threading.Thread(target=_status_refresh_worker, daemon=True, name="StatusRefresher")
        t.start()


def get_cached_status() -> dict:
    start_status_refresher()
    with _STATUS_CACHE_LOCK:
        return dict(_STATUS_CACHE)


def update_status_positions(positions: list) -> None:
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE["positions"] = positions
        _STATUS_CACHE["cached_at"] = time.time()


def invalidate_status_cache() -> None:
    """Clear the cached status so the next request triggers a fresh fetch."""
    global _STATUS_CACHE
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE = {}


class OmniHttpHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # static assets
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            data = _read_web_file(name)
            if data is None:
                self.send_error(404); return
            ext = Path(name).suffix.lower()
            ctype = _STATIC_TYPES.get(ext, "application/octet-stream")
            self.send_response(200)
            charset = "; charset=utf-8" if ext in (".css", ".js", ".html") else ""
            self.send_header("Content-Type", ctype + charset)
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # SPA entry: all page routes serve index.html, client hash-routes
        if path in ("/", "/index.html", "/risk", "/decisions", "/positions", "/ledger", "/controls"):
            data = _read_web_file("index.html") or b"<p>index.html missing</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path in ("/legacy", "/legacy.html"):
            encoded = COCKPIT_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        if parsed.path == "/api/status":
            self._send_json(get_cached_status())
            return

        if parsed.path == "/api/config":
            from .policy import PolicyConfig
            from .config import ALLOWED_ACTIONS, FORBIDDEN_ACTIONS, RTOKEN_FEE_RATE, DEFAULT_HEDGE_PERP
            pol = PolicyConfig()
            self._send_json({
                "ok": True,
                "max_order_notional_usdt": pol.max_order_notional_usdt,
                "max_leverage": pol.max_leverage,
                "force_action_on_breach": pol.force_action_on_breach,
                "allow_hedge": pol.allow_hedge,
                "allowed_actions": list(ALLOWED_ACTIONS),
                "forbidden_actions": list(FORBIDDEN_ACTIONS),
                "rtoken_fee_rate": RTOKEN_FEE_RATE,
                "default_hedge_perp": DEFAULT_HEDGE_PERP,
            })
            return

        if parsed.path == "/api/ledger":
            try:
                cfg = load_config()
                ledger = Ledger(cfg.log_dir)
                records = ledger.read_all()
                payload = {"ok": True, "records": records}
            except Exception as e:  # noqa: BLE001
                payload = {"ok": False, "error": str(e)}

            self._send_json(payload)
            return

        if parsed.path == "/api/action/terminal_logs":
            self._send_json({"ok": True, "logs": GLOBAL_TERMINAL_LOGS.get_all()})
            return

        if parsed.path == "/api/action/daemon":
            self._send_json(GLOBAL_DAEMON.status())
            return

        if parsed.path == "/api/action/report":
            res = run_report()
            self._send_json(res)
            return

        self.send_response(404)
        self.send_header("Connection", "close")
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            params = json.loads(body) if body else {}
        except Exception:  # noqa: BLE001
            params = {}

        if parsed.path == "/api/cycle":
            rtoken_shock = float(params.get("rtoken_shock", -0.25))
            execute_flag = bool(params.get("execute", False))

            try:
                d_cfg = DaemonConfig(
                    execute=execute_flag,
                    portfolio_path=DEFAULT_PORTFOLIO,
                    rtoken_shock=rtoken_shock,
                )
                daemon = OmniDaemon(d_cfg)
                cycle_result = daemon.run_one_cycle()
                invalidate_status_cache()
                now_str = datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                dec = cycle_result.get("decision") or {}
                GLOBAL_TERMINAL_LOGS.append(
                    f"[{now_str}] $ omni decide --execute (shock={rtoken_shock:+.0%}) -> "
                    f"Decision: {dec.get('action', 'HOLD')} | "
                    f"Executed: {cycle_result.get('execution', {}).get('executed')}"
                )
                res = {"ok": True, "result": cycle_result}
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": str(e)}

            self._send_json(res)
            return

        if parsed.path == "/api/action/doctor":
            res = run_doctor()
            self._send_json(res)
            return

        if parsed.path == "/api/action/setup":
            symbol = str(params.get("symbol", "BTCUSDT")).strip().upper()
            qty = str(params.get("qty", "0.05")).strip()
            res = run_setup(symbol=symbol, qty=qty)
            if res.get("positions"):
                update_status_positions(res["positions"])
            self._send_json(res)
            return

        if parsed.path == "/api/action/flatten":
            res = run_flatten()
            update_status_positions([])
            self._send_json(res)
            return

        if parsed.path == "/api/action/report":
            res = run_report()
            self._send_json(res)
            return

        if parsed.path == "/api/action/daemon":
            action = params.get("action", "status")
            if action == "start":
                interval = int(params.get("interval", 30))
                execute = bool(params.get("execute", False))
                shock = float(params.get("shock", -0.25))
                res = GLOBAL_DAEMON.start(interval=interval, execute=execute, shock=shock)
            elif action == "stop":
                res = GLOBAL_DAEMON.stop()
            else:
                res = GLOBAL_DAEMON.status()
            self._send_json(res)
            return

        if parsed.path == "/api/action/terminal_clear":
            GLOBAL_TERMINAL_LOGS.clear()
            self._send_json({"ok": True})
            return

        self.send_response(404)
        self.send_header("Connection", "close")
        self.end_headers()

    def _send_json(self, data: dict):
        encoded = json.dumps(data, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        # Quiet server logs for clean terminal output
        return


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_ui(port: int = PORT):
    print("===============================================================")
    print(f"       Omni Live Visual Cockpit running on port {port}       ")
    print(f"       1:1 CLI Terminal Parity Enabled                       ")
    print(f"       Open: http://localhost:{port}                         ")
    print("===============================================================")
    start_status_refresher()
    server = ThreadingHTTPServer(("127.0.0.1", port), OmniHttpHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[UI] Server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve_ui()
