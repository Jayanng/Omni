"""Omni command line interface.

    omni doctor                 verify every live dependency
    omni status                 session, account and market snapshot
    omni decide [--execute]     full event to decision to execution loop
    omni demo                   one scripted judge-facing run
    omni flatten                close any open demo positions
    omni report                 paper metrics from the ledger
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import bitget_public as bp
from . import collateral as coll
from . import llm as llm_mod
from . import metrics as metrics_mod
from .bitget_demo import DemoClient, DemoCliError
from .collateral import RTokenPosition
from .config import ROOT, load_config, stock_perp_for
from .executor import execute
from .ledger import Ledger
from .policy import PolicyConfig, validate
from .risk import FuturesPosition, evaluate, shock_for
from .session import classify

DEFAULT_PORTFOLIO = ROOT / "demo" / "portfolio.example.json"


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _print(title: str) -> None:
    print(f"\n=== {title} ===")


def _stock_perp_symbols(client: DemoClient) -> set:
    """Symbols in the demo futures universe whose instrument type is stock.

    Used to decide which scenario shock applies to a position: a stock perpetual
    tracks the equity gap, a crypto perpetual does not.
    """
    try:
        result = client.call(
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


def load_portfolio(path: Path) -> dict:
    if not path.exists():
        return {"rtoken_positions": []}
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def cmd_doctor(args) -> int:
    cfg = load_config()
    checks: list[tuple[str, bool, str]] = []

    checks.append(
        ("demo credentials present", cfg.has_credentials,
         "BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE")
    )
    bgc_detail = cfg.bgc or "npx pinned @bitget-ai/bitget-agent-cli@3.0.0"
    checks.append(("agent hub cli resolved", True, bgc_detail))
    checks.append(("llm configured", cfg.has_llm, f"{cfg.llm_model} at {cfg.llm_base_url}"))

    _print("public data sources")
    for name, fn in (
        ("reality market states", lambda: bp.market_states()),
        ("reality stock info", lambda: bp.stock_info("RNVDAUSDT")),
        ("reality market calendar", lambda: bp.market_calendar("NVDA")),
        ("reality dividends", lambda: bp.dividends("NVDA")),
        ("rToken ticker", lambda: bp.ticker("RNVDAUSDT")),
        ("rToken candles", lambda: bp.candles("RNVDAUSDT", "1H", 3)),
        ("rToken order book", lambda: bp.orderbook("RNVDAUSDT", 5)),
    ):
        try:
            payload = fn()
            ok = bool(payload)
            detail = f"{len(payload)} rows" if isinstance(payload, list) else "ok"
            checks.append((f"public: {name}", ok, detail))
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        except Exception as exc:  # noqa: BLE001
            checks.append((f"public: {name}", False, str(exc)[:120]))
            print(f"  [FAIL] {name}: {str(exc)[:120]}")

    _print("demo account and execution")
    client = DemoClient(cfg)
    if cfg.has_credentials:
        try:
            overview = client.account_overview()
            assets = overview.get("assets") or {}
            ok = bool(assets)
            detail = "assets returned" if ok else (
                f"empty assets payload, sections={overview.get('sections')}, "
                f"keys={overview.get('raw_section_keys')}"
            )
            checks.append(("demo: account overview", ok, detail))
            print(f"  [{'PASS' if ok else 'FAIL'}] account overview: {detail}")
        except Exception as exc:  # noqa: BLE001
            checks.append(("demo: account overview", False, str(exc)[:120]))
            print(f"  [FAIL] account overview: {str(exc)[:120]}")

        try:
            preview = client.place_order(
                "USDT-FUTURES", "NVDAUSDT", "sell", "market", "0.05",
                pos_side="short", reduce_only="no", dry_run=True,
            )
            ok = bool(preview.ok)
            checks.append(("demo: order dry run", ok, "preview returned"))
            print(f"  [{'PASS' if ok else 'FAIL'}] order dry run")
        except Exception as exc:  # noqa: BLE001
            checks.append(("demo: order dry run", False, str(exc)[:120]))
            print(f"  [FAIL] order dry run: {str(exc)[:120]}")
    else:
        checks.append(("demo: account overview", False, "no credentials"))
        print("  [SKIP] no demo credentials configured")

    _print("session classifier")
    try:
        state = classify(bp.market_states(), (bp.stock_info("RNVDAUSDT") or [{}])[0],
                         bp.market_calendar("NVDA"))
        checks.append(("session classify", True, state.regime))
        print(f"  [PASS] regime={state.regime} liquidity={state.liquidity_tier} "
              f"mark_confidence={state.mark_confidence}")
    except Exception as exc:  # noqa: BLE001
        checks.append(("session classify", False, str(exc)[:120]))
        print(f"  [FAIL] {str(exc)[:120]}")

    passed = sum(1 for _, ok, _ in checks if ok)
    _print(f"doctor summary: {passed}/{len(checks)} checks passed")
    for name, ok, detail in checks:
        if not ok:
            print(f"  FAILED -> {name}: {detail}")
    return 0 if passed == len(checks) else 1


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def cmd_status(args) -> int:
    cfg = load_config()
    ledger = Ledger(cfg.log_dir)
    client = DemoClient(cfg)

    stock_rows = bp.stock_info("RNVDAUSDT") or [{}]
    session = classify(bp.market_states(), stock_rows[0], bp.market_calendar("NVDA"))
    tick = bp.ticker("RNVDAUSDT")

    _print("session")
    print(json.dumps(session.to_dict(), indent=2))

    _print("rToken reference")
    print(json.dumps({
        "symbol": tick.get("symbol"),
        "last": tick.get("lastPrice"),
        "bid": tick.get("bid1Price"),
        "ask": tick.get("ask1Price"),
    }, indent=2))

    overview = client.account_overview()
    assets = overview.get("assets") or {}
    _print("demo account")
    print(json.dumps({
        "effective_equity": assets.get("effEquity"),
        "maintenance_margin": assets.get("mmr"),
        "margin_ratio": assets.get("mgnRatio"),
        "positions": client.positions(),
    }, indent=2, default=str)[:1500])

    ledger.record("session", session.to_dict())
    ledger.record("account_snapshot", {"assets": assets, "source": "account_overview"})
    print(f"\nledger: {ledger.path}")
    return 0


# ---------------------------------------------------------------------------
# decide / demo
# ---------------------------------------------------------------------------


def run_cycle(execute_action: bool, args) -> int:
    cfg = load_config()
    ledger = Ledger(cfg.log_dir)
    client = DemoClient(cfg)
    portfolio = load_portfolio(Path(args.portfolio) if args.portfolio else DEFAULT_PORTFOLIO)

    _print("1. event intake: session and calendar")
    stock_rows = bp.stock_info(args.rtoken)
    if not stock_rows:
        raise RuntimeError(f"no Reality stock info returned for {args.rtoken}")
    stock = stock_rows[0]
    code = stock.get("code") or next(
        (r.get("code") for r in portfolio.get("rtoken_positions", []) if r.get("code")), ""
    )
    if not code:
        raise RuntimeError(
            f"cannot determine the underlying stock code for {args.rtoken}; "
            "set 'code' in the declared portfolio"
        )
    session = classify(bp.market_states(), stock, bp.market_calendar(code))
    print(f"  regime={session.regime} liquidity={session.liquidity_tier} "
          f"mark_confidence={session.mark_confidence} weekend_tradable={session.weekend_tradable}")
    print(f"  underlying code={code} trading_periods={','.join(session.trading_periods)}")
    ledger.record("session", session.to_dict())

    try:
        div = bp.dividends(code)
        events = div.get("list") or []
        print(f"  corporate actions observed: {len(events)}")
        ledger.record("corporate_actions", {"code": code, "events": events[:5]})
    except Exception as exc:  # noqa: BLE001
        print(f"  corporate action lookup skipped: {str(exc)[:80]}")

    _print("2. market data: rToken marks and depth")
    marks: dict = {}
    books: dict = {}
    for row in portfolio.get("rtoken_positions", []):
        symbol = row["symbol"]
        tick = bp.ticker(symbol)
        marks[symbol] = float(tick["lastPrice"])
        books[symbol] = bp.orderbook(symbol, 10)
        print(f"  {symbol}: last={marks[symbol]}")

    hedge_marks = {}
    for sym in ("NVDAUSDT", "TSLAUSDT", "AAPLUSDT", "GOOGLUSDT"):
        try:
            tick = client.call(
                ["market", "--action", "tickers", "--category", "USDT-FUTURES", "--symbol", sym],
                allow_failure=True,
            )
            rows = tick.data if isinstance(tick.data, list) else []
            if rows:
                hedge_marks[sym] = float(rows[0]["lastPrice"])
        except Exception:  # noqa: BLE001
            continue
    print(f"  tradable stock perpetual marks: {hedge_marks}")
    ledger.record("marks", {"rtoken": marks, "stock_perps": hedge_marks})

    _print("3. account state")
    overview = client.account_overview()
    assets = overview.get("assets") or {}
    sections = overview.get("sections") or {}
    assets_ok = bool((sections.get("assets") or {}).get("ok", True))
    if not assets_ok:
        raise RuntimeError(
            "account assets section failed: "
            f"{(sections.get('assets') or {}).get('error')}"
        )
    eff_equity = float(assets.get("effEquity") or 0.0)
    if eff_equity <= 0:
        raise RuntimeError(
            "refusing to model risk on a non-positive equity base "
            f"(observed effEquity={eff_equity!r})"
        )
    raw_positions = client.positions()
    stock_perps = _stock_perp_symbols(client)
    hedge_symbol = stock_perp_for(args.rtoken)
    futures = []
    for p in raw_positions:
        symbol = p["symbol"]
        futures.append(
            FuturesPosition(
                symbol=symbol,
                pos_side=p.get("posSide", "long"),
                total=float(p.get("total") or 0.0),
                mark_price=float(p.get("markPrice") or 0.0),
                avg_price=float(p.get("avgPrice") or 0.0),
                unrealised_pnl=float(p.get("unrealisedPnl") or 0.0),
                mmr=float(p.get("mmr") or 0.0),
                leverage=float(p.get("leverage") or 0.0),
                asset_class="stock" if symbol.upper() in stock_perps else "crypto",
            )
        )
    print(f"  effective equity={eff_equity:,.2f} USDT, open futures positions={len(futures)}")
    print(f"  hedge instrument for {args.rtoken}: {hedge_symbol}")
    for pos in futures:
        shock = shock_for(pos.asset_class, args.rtoken_shock, args.crypto_shock)
        print(f"    {pos.symbol} {pos.pos_side} notional={pos.notional:,.2f} "
              f"asset_class={pos.asset_class} shock={shock:+.1%}")
    ledger.record("account_snapshot", {
        "assets": assets, "sections": sections, "source": "account_overview",
    })

    _print("4. rToken collateral stress and margin model")
    rtoken_positions = [
        RTokenPosition(symbol=r["symbol"], code=r.get("code", ""), qty=float(r["qty"]),
                       avg_price=float(r.get("avg_price", 0.0)))
        for r in portfolio.get("rtoken_positions", [])
    ]
    risk = evaluate(
        as_of=_now(),
        observed_effective_equity=eff_equity,
        rtoken_positions=rtoken_positions,
        rtoken_marks=marks,
        futures_positions=futures,
        haircut_pct=args.haircut,
        rtoken_shock_pct=args.rtoken_shock,
        crypto_shock_pct=args.crypto_shock,
        hedge_symbol=hedge_symbol,
    )
    rd = risk.to_dict()

    # Simulated cost of exiting the rToken leg into the stressed book. Bitget's
    # demo service does not execute RWA orders, so this is marked simulated and
    # the depth it walks is the real production order book.
    simulated_exits = []
    for pos in rtoken_positions:
        book = books.get(pos.symbol)
        if not book:
            continue
        fill = coll.simulate_fill(
            pos.symbol, "sell", pos.qty, book, shock_pct=args.rtoken_shock
        )
        simulated_exits.append(fill.to_dict())
    if simulated_exits:
        rd["results"]["simulated_rtoken_exits"] = simulated_exits

    print(f"  modelled rToken gross        : {rd['modelled']['rtoken_gross_value']:,.2f} USDT")
    print(f"  haircut applied              : {args.haircut:.1%}")
    print(f"  effective collateral         : {rd['modelled']['rtoken_effective_collateral']:,.2f} USDT")
    print(f"  scenario rToken / crypto     : {args.rtoken_shock:+.1%} / {args.crypto_shock:+.1%}")
    print(f"  shocked buffer               : {rd['results']['shocked_buffer_usdt']:,.2f} USDT")
    print(f"  breach                       : {rd['results']['breach']}")
    print(f"  {rd['results']['narrative']}")
    for exit_fill in simulated_exits:
        print(f"  simulated rToken exit (labelled simulated): "
              f"{exit_fill['symbol']} {exit_fill['filled_qty']:g} @ {exit_fill['vwap']:,.2f} "
              f"slippage {exit_fill['slippage_bps']:.1f} bps, fee {exit_fill['fee']:.2f} USDT")
    ledger.record("risk_state", rd)

    if args.haircut_source:
        print(f"  haircut source               : {args.haircut_source}")

    _print("5. agent decision (LLM is the decision maker)")
    decision = llm_mod.decide(
        rd, session.to_dict(), cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model,
        fallback_model=cfg.llm_fallback_model,
    )
    print(f"  model={decision.model} fallback={decision.used_fallback} latency={decision.latency_ms}ms")
    print(f"  action={decision.action} params={json.dumps(decision.params)}")
    print(f"  rationale: {decision.rationale[:300]}")
    ledger.record("decision", {"decision": decision.to_dict(), "session_regime": session.regime})

    _print("6. policy layer (allowlist, caps, forced protection)")
    policy_cfg = PolicyConfig(max_order_notional_usdt=args.max_hedge_notional)
    policy = validate(decision.action, decision.params, rd, session.to_dict(), policy_cfg)
    print(f"  approved={policy.approved} action={policy.action} override={policy.override}")
    print(f"  reason: {policy.reason[:300]}")
    for check in policy.checks:
        print(f"    check ok : {check}")
    for veto in policy.vetoes:
        print(f"    veto     : {veto}")

    _print("7. execution: dry run then explicit order then readback")
    if not execute_action:
        print("  execute flag not set, stopping before any order is sent")
        ledger.record("execution", {
            "policy": policy.to_dict(),
            "execution": {"action": policy.action, "executed": False,
                          "reason": "dry cycle, execute flag not set"},
        })
        return 0

    result = execute(policy.action, policy.params, client, hedge_marks,
                     hedge_symbol=hedge_symbol)
    print(f"  executed={result.executed} reason={result.reason[:200]}")
    for step in result.steps:
        print(f"    step {step.name}: ok={step.ok} endpoint={step.endpoint} error={step.error}")
    if result.readback:
        for pos in result.readback.get("open_positions", []):
            print(f"    readback: {pos.get('symbol')} {pos.get('posSide')} "
                  f"total={pos.get('total')} mark={pos.get('markPrice')}")
    ledger.record("execution", {
        "policy": policy.to_dict(),
        "decision": decision.to_dict(),
        "execution": result.to_dict(),
    })
    print(f"\nledger: {ledger.path}")
    return 0


def cmd_decide(args) -> int:
    return run_cycle(args.execute, args)


def cmd_demo(args) -> int:
    args.execute = True
    return run_cycle(True, args)


def cmd_daemon(args) -> int:
    from .daemon import DaemonConfig, OmniDaemon
    d_cfg = DaemonConfig(
        interval=args.interval,
        execute=args.execute,
        max_iterations=args.max_iterations,
        portfolio_path=Path(args.portfolio) if args.portfolio else DEFAULT_PORTFOLIO,
        rtoken=args.rtoken,
        haircut=args.haircut,
        haircut_source=args.haircut_source,
        rtoken_shock=args.rtoken_shock,
        crypto_shock=args.crypto_shock,
        max_hedge_notional=args.max_hedge_notional,
    )
    OmniDaemon(d_cfg).start()
    return 0


def cmd_ui(args) -> int:
    from .web import serve_ui
    serve_ui(port=args.port)
    return 0


# ---------------------------------------------------------------------------
# flatten and report
# ---------------------------------------------------------------------------


def cmd_setup(args) -> int:
    """Construct the demo book: a leveraged crypto perpetual leg.

    This is demo book construction for the paper log, not a trading signal.
    """
    cfg = load_config()
    ledger = Ledger(cfg.log_dir)
    client = DemoClient(cfg)
    symbol = args.setup_symbol
    qty = args.setup_qty

    preview = client.place_order(
        "USDT-FUTURES", symbol, "buy", "market", str(qty), pos_side="long", reduce_only="no",
        dry_run=True,
    )
    print(f"dry run: ok={preview.ok}")
    if not preview.ok:
        print("setup aborted, dry run rejected")
        return 1
    sent = client.place_order(
        "USDT-FUTURES", symbol, "buy", "market", str(qty), pos_side="long", reduce_only="no",
    )
    print(f"opened demo book: {symbol} long {qty} -> ok={sent.ok}")
    ledger.record("demo_book_setup", {
        "symbol": symbol, "side": "long", "qty": qty,
        "ok": bool(sent.ok), "order": sent.data,
        "note": "demo book construction for the paper log, not a trading signal",
    })
    for pos in client.positions():
        print(f"  position: {pos.get('symbol')} {pos.get('posSide')} total={pos.get('total')} "
              f"notional={float(pos.get('total', 0)) * float(pos.get('markPrice', 0)):,.2f}")
    return 0


def cmd_flatten(args) -> int:
    cfg = load_config()
    ledger = Ledger(cfg.log_dir)
    client = DemoClient(cfg)
    positions = client.positions()
    if not positions:
        print("no open demo positions")
        return 0
    for pos in positions:
        symbol = pos["symbol"]
        preview = client.close_position("USDT-FUTURES", symbol, dry_run=True)
        print(f"dry run close {symbol}: ok={preview.ok}")
        if not preview.ok:
            continue
        done = client.close_position("USDT-FUTURES", symbol, confirm=True)
        print(f"closed {symbol}: ok={done.ok}")
        ledger.record("flatten", {"symbol": symbol, "ok": bool(done.ok), "data": done.data})
    remaining = client.positions()
    print(f"remaining positions: {len(remaining)}")
    ledger.record("flatten_summary", {"remaining": len(remaining)})
    return 0


def cmd_report(args) -> int:
    cfg = load_config()
    _print("paper metrics")
    print(json.dumps(metrics_mod.compute(cfg.log_dir), indent=2))
    _print("ledger files")
    for path in Ledger.all_logs(cfg.log_dir):
        print(f"  {path.name} ({path.stat().st_size} bytes)")
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    # Shared options are attached to both the top level parser and every
    # subcommand, so scenarios can be written either before or after the verb.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--portfolio", help="path to the declared portfolio json")
    common.add_argument("--rtoken", default="RNVDAUSDT", help="rToken symbol to monitor")
    common.add_argument("--haircut", type=float, default=0.15,
                        help="rToken collateral ratio applied in the model")
    common.add_argument("--haircut-source", default="", help="documented source of the haircut")
    common.add_argument("--rtoken-shock", type=float, default=-0.04,
                        help="scenario rToken shock, e.g. -0.04")
    common.add_argument("--crypto-shock", type=float, default=-0.06,
                        help="scenario crypto shock, e.g. -0.06")
    common.add_argument("--max-hedge-notional", type=float, default=5_000.0,
                        help="policy cap on a single protective hedge, in USDT")

    parser = argparse.ArgumentParser(
        prog="omni",
        description="Omni cross-asset risk governor",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="verify every live dependency",
                   parents=[common]).set_defaults(func=cmd_doctor)
    sub.add_parser("status", help="session and account snapshot",
                   parents=[common]).set_defaults(func=cmd_status)

    decide = sub.add_parser("decide", help="run one governance cycle", parents=[common])
    decide.add_argument("--execute", action="store_true", help="send the paper order")
    decide.set_defaults(func=cmd_decide)

    sub.add_parser("demo", help="one scripted judge-facing run",
                   parents=[common]).set_defaults(func=cmd_demo)

    setup = sub.add_parser("setup", help="construct the demo book (paper position)",
                           parents=[common])
    setup.add_argument("--setup-symbol", default="BTCUSDT")
    setup.add_argument("--setup-qty", default="2")
    setup.set_defaults(func=cmd_setup)

    sub.add_parser("flatten", help="close open demo positions",
                   parents=[common]).set_defaults(func=cmd_flatten)
    sub.add_parser("report", help="paper metrics from the ledger",
                   parents=[common]).set_defaults(func=cmd_report)

    daemon = sub.add_parser("daemon", help="24/7 continuous autonomous governor loop",
                            parents=[common])
    daemon.add_argument("--interval", type=int, default=60, help="cycle interval in seconds (default: 60)")
    daemon.add_argument("--execute", action="store_true", help="enable autonomous paper order execution")
    daemon.add_argument("--max-iterations", type=int, default=None, help="stop after N cycles")
    daemon.set_defaults(func=cmd_daemon)

    ui = sub.add_parser("ui", help="launch Floor-style live visual cockpit",
                        parents=[common])
    ui.add_argument("--port", type=int, default=8080, help="port to listen on (default: 8080)")
    ui.set_defaults(func=cmd_ui)
    return parser


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DemoCliError as exc:
        print(f"agent hub cli error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
