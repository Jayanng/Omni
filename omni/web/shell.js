/* omni console shell: shared design system, sidebar nav, client routing.
   No build step. Pages register themselves on window.__OMNI_PAGES. */
window.__OMNI_PAGES = {};

const OMNI = (() => {
  const $ = id => document.getElementById(id);
  const fmt = (v, d = 2) => (v == null || isNaN(Number(v))) ? "\u2014"
    : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const state = { status: null, ledger: [], daemon: null, timers: [] };

  async function api(path, opts) {
    const r = await fetch(path, opts);
    return r.json();
  }
  async function refreshStatus() { try { state.status = await api("/api/status"); } catch (e) {} }
  async function refreshLedger() { try { const d = await api("/api/ledger"); state.ledger = d.records || []; } catch (e) {} }
  async function refreshDaemon() { try { state.daemon = await api("/api/action/daemon"); } catch (e) {} }

  function latestRisk() {
    for (let i = state.ledger.length - 1; i >= 0; i--) {
      const rec = state.ledger[i], p = rec.payload || {};
      if (rec.kind === "risk_state" && p.results) return { results: p.results, modelled: p.modelled || {}, scenario: p.scenario || {}, ts: rec.ts };
      if (rec.kind === "daemon_cycle" && p.risk) {
        return p.risk.results ? { results: p.risk.results, modelled: p.risk.modelled || {}, scenario: p.risk.scenario || {}, ts: p.timestamp || rec.ts }
          : { results: p.risk, modelled: {}, scenario: {}, ts: p.timestamp || rec.ts };
      }
    }
    return null;
  }
  function latestDecision() {
    for (let i = state.ledger.length - 1; i >= 0; i--) {
      const rec = state.ledger[i], pl = rec.payload || {};
      const dec = (rec.kind === "decision" && pl.decision) || (rec.kind === "daemon_cycle" && pl.decision) || null;
      if (dec && dec.action) return { decision: dec, policy: pl.policy || {}, execution: pl.execution || {}, ts: rec.ts, kind: rec.kind };
    }
    return null;
  }
  function equitySeries() {
    const pts = [];
    for (const rec of state.ledger) {
      const p = rec.payload || {}; let eq = null;
      if (rec.kind === "account_snapshot" && p.assets && p.assets.effEquity != null) eq = Number(p.assets.effEquity);
      if (rec.kind === "daemon_cycle" && p.account && p.account.equity != null) eq = Number(p.account.equity);
      if (eq != null && eq > 0) pts.push({ ts: rec.ts, eq });
    }
    pts.sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
    return pts;
  }
  function summarize(rec) {
    const p = rec.payload || {};
    switch (rec.kind) {
      case "session": return "regime " + (p.regime || "\u2014");
      case "risk_state": { const r = p.results || {}; return "buffer " + (r.shocked_buffer_usdt != null ? fmt(r.shocked_buffer_usdt, 0) : "\u2014"); }
      case "decision": { const d = p.decision || {}; return (d.action || "\u2014") + " \u00b7 " + (d.model || ""); }
      case "execution": { const e = p.execution || {}; return (e.executed ? "executed" : "not executed") + " \u00b7 " + (e.action || "\u2014"); }
      case "daemon_cycle": { const d = p.decision || {}; return "cycle " + (p.cycle || "\u2014") + " \u00b7 " + (d.action || "\u2014"); }
      case "daemon_start": return "daemon started \u00b7 " + (p.interval || "\u2014") + "s \u00b7 execute " + (!!p.execute);
      case "daemon_stop": return "daemon stopped \u00b7 " + (p.total_cycles || 0) + " cycles";
      case "demo_book_setup": return (p.symbol || "\u2014") + " long " + (p.qty || "\u2014");
      case "flatten": return "closed " + (p.symbol || "\u2014");
      case "flatten_summary": return "remaining " + (p.remaining != null ? p.remaining : "\u2014");
      case "regime_transition": return (p.from || "\u2014") + " \u2192 " + (p.to || "\u2014");
      default: return "";
    }
  }

  // next Monday 09:30 New York, computed live
  function countdownToCashOpen() {
    const ny = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
    const target = new Date(ny);
    let add = (8 - target.getDay()) % 7; if (add === 0) add = 7;
    target.setDate(target.getDate() + add); target.setHours(9, 30, 0, 0);
    const ms = target - ny;
    if (ms <= 0) return "open";
    const h = Math.floor(ms / 3.6e6), m = Math.floor(ms % 3.6e6 / 6e4);
    return (h >= 24 ? Math.floor(h / 24) + "d " : "") + (h % 24) + "h " + m + "m";
  }

  const PAGES = [
    ["/", "overview"], ["/risk", "risk model"], ["/decisions", "decisions"],
    ["/positions", "positions"], ["/ledger", "audit ledger"], ["/controls", "controls"],
  ];
  function layout(activeRoute, innerHtml) {
    const nav = PAGES.map(([route, label]) =>
      `<a class="nav-item${route === activeRoute ? " active" : ""}" href="#${route}">${label}</a>`).join("");
    return `
      <aside class="sidenav">
        <div class="snav-brand">omni<span>.</span></div>
        <div class="snav-sub">cross-asset risk governor</div>
        <nav>${nav}</nav>
        <div class="snav-foot" id="snavFoot"></div>
      </aside>
      <div class="page">
        <header class="topbar">
          <span class="badge" id="daemonBadge">daemon: \u2014</span>
          <span class="badge" id="regimeBadge">session: \u2014</span>
          <span class="hspace"></span>
          <span class="mono topclock" id="utcClock">\u2014</span>
        </header>
        <main class="content">${innerHtml}</main>
      </div>`;
  }

  function mountGlobal() {
    const db = $("daemonBadge"), rb = $("regimeBadge"), uc = $("utcClock");
    if (uc) uc.textContent = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
    if (state.daemon && db) {
      db.textContent = state.daemon.running ? "daemon: running \u00b7 " + (state.daemon.cycles_completed || 0) + " cycles" : "daemon: idle";
      db.className = "badge" + (state.daemon.running ? " ok" : "");
    }
    const s = (state.status && state.status.session) || {};
    if (rb && s.regime) { rb.textContent = "session: " + s.regime; rb.className = "badge " + (s.regime === "regular" ? "ok" : "warn"); }
    const foot = $("snavFoot");
    if (foot && state.status) {
      foot.innerHTML = `<div class="foot-row"><span>equity</span><span class="num">${fmt(state.status.equity, 0)}</span></div>
        <div class="foot-row"><span>cached</span><span class="num">${state.status.cached_at ? new Date(state.status.cached_at * 1000).toISOString().slice(11, 19) : "\u2014"}</span></div>`;
    }
  }

  let currentRoute = null;
  function route() {
    const hash = location.hash.replace(/^#/, "") || "/";
    const page = window.__OMNI_PAGES[hash] || window.__OMNI_PAGES["/"];
    if (!page) return;
    state.timers.forEach(clearInterval); state.timers = [];
    document.getElementById("app").innerHTML = layout(hash, page.render());
    currentRoute = hash;
    if (page.mount) page.mount();
    mountGlobal();
  }

  function start() {
    window.addEventListener("hashchange", route);
    route();
    refreshStatus(); refreshLedger(); refreshDaemon();
    state.timers.push(setInterval(async () => { await refreshStatus(); await refreshDaemon(); mountGlobal(); }, 12000));
    state.timers.push(setInterval(async () => { await refreshLedger(); mountGlobal(); }, 15000));
    state.timers.push(setInterval(mountGlobal, 1000)); // clock tick
  }

  return { $, fmt, esc, api, state, latestRisk, latestDecision, equitySeries, summarize, countdownToCashOpen, start, refreshStatus, refreshLedger, refreshDaemon };
})();
