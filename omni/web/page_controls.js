/* controls page: governance cycle, daemon, book, doctor, policy facts */
window.__OMNI_PAGES["/controls"] = {
  render() {
    return `
      <div class="section-label">GOVERNANCE</div>
      <div class="section-title serif">Controls</div>
      <div class="grid2">
        <div class="card">
          <h2>Governance cycle</h2>
          <p style="font-size:13px;color:var(--muted);margin-bottom:16px;line-height:1.6">
            Runs one full observe \u2192 model \u2192 decide \u2192 policy \u2192 execute cycle against the live demo account.
            Dry run by default; check the box to send paper orders.
          </p>
          <p style="font-size:12px;color:var(--muted);margin-bottom:12px;line-height:1.5">
            Scenario shocks are derived from the stressed instruments' live candle history on each cycle.
            No manual market shock is injected here.
          </p>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:13px;color:var(--muted)">
            <input type="checkbox" id="execFlag"><label for="execFlag">execute paper orders</label>
          </div>
          <div id="execWarn" style="font-size:12px;color:#C4787C;margin-bottom:12px;display:none">orders will be sent to the demo account</div>
          <button class="primary" id="btnCycle" style="width:100%">run governance cycle</button>
          <div id="cycleOut" style="margin-top:16px;display:none">
            <div class="dec-action serif" id="cAction"></div>
            <div class="dec-meta" id="cMeta"></div>
            <div class="rationale" id="cRationale"></div>
            <div class="policy-line" id="cPolicy"></div>
          </div>
        </div>
        <div class="card">
          <h2>Daemon</h2>
          <div class="row"><span class="k">state</span><span class="v" id="cDState">\u2014</span></div>
          <div class="row"><span class="k">cycles completed</span><span class="v num" id="cDCycles">\u2014</span></div>
          <div class="row"><span class="k">interval</span><span class="v num" id="cDInterval">\u2014</span></div>
          <button class="sage" id="btnDaemon" style="width:100%;margin-top:16px">start daemon</button>
          <h2 style="margin-top:24px">Book management</h2>
          <div style="display:flex;gap:8px;margin-bottom:10px">
            <input id="setupSymbol" placeholder="symbol" value="BTCUSDT" style="flex:1">
            <input id="setupQty" placeholder="qty" value="2" style="width:80px">
          </div>
          <div style="display:flex;gap:8px">
            <button class="sage" id="btnSetup" style="flex:1">setup book</button>
            <button class="danger" id="btnFlatten" style="flex:1">flatten all</button>
          </div>
          <h2 style="margin-top:24px">Health</h2>
          <button class="sage" id="btnDoctor" style="width:100%">run doctor</button>
        </div>
      </div>
      <div class="card">
        <h2>Policy facts \u00b7 from config</h2>
        <div class="grid3" id="policyFacts"></div>
      </div>
      <div class="modal-bg" id="doctorBg">
        <div class="modal">
          <h3>Doctor <button class="close" id="docClose" style="float:right;width:auto;padding:6px 12px;font-size:12px">close</button></h3>
          <div class="dec-meta" id="docPending">running checks\u2026</div>
          <div id="docBody"></div>
        </div>
      </div>`;
  },
  mount() {
    const { $, state, api, refreshStatus, refreshLedger, refreshDaemon } = OMNI;
    // Shocks are derived by the live scenario engine; the UI does not inject
    // hardcoded market moves into a governance cycle.
    $("execFlag").addEventListener("change", () => { $("execWarn").style.display = $("execFlag").checked ? "block" : "none"; });

    function renderDaemon() {
      const d = state.daemon || {};
      $("cDState").textContent = d.running ? "running" : "idle";
      $("cDState").className = "v " + (d.running ? "ok" : "dim");
      $("cDCycles").textContent = d.cycles_completed != null ? d.cycles_completed : "\u2014";
      $("cDInterval").textContent = d.interval != null ? d.interval + "s" : "\u2014";
      $("btnDaemon").textContent = d.running ? "stop daemon" : "start daemon";
    }
    renderDaemon();
    OMNI.state.timers.push(setInterval(renderDaemon, 5000));

    api("/api/config").then(cfg => {
      const el = $("policyFacts");
      if (!cfg || !cfg.ok) { el.innerHTML = `<div class="empty">config unavailable</div>`; return; }
      const items = [
        ["hedge cap", cfg.max_order_notional_usdt != null ? Number(cfg.max_order_notional_usdt).toLocaleString() + " USDT" : "\u2014"],
        ["max leverage", cfg.max_leverage != null ? cfg.max_leverage + "x" : "\u2014"],
        ["allowed actions", (cfg.allowed_actions || []).length],
        ["forbidden actions", (cfg.forbidden_actions || []).length],
        ["rToken fee rate", cfg.rtoken_fee_rate != null ? (cfg.rtoken_fee_rate * 100).toFixed(2) + "%" : "\u2014"],
        ["mapped hedge perps", (cfg.mapped_stock_perps || []).length],
      ];
      el.innerHTML = items.map(([k, v]) => `<div class="row"><span class="k">${k}</span><span class="v num">${v}</span></div>`).join("");
    }).catch(() => { $("policyFacts").innerHTML = `<div class="empty">config unavailable</div>`; });

    $("btnCycle").addEventListener("click", async () => {
      const btn = $("btnCycle"); btn.disabled = true; btn.textContent = "cycle running\u2026";
      try {
        const d = await api("/api/cycle", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ execute: $("execFlag").checked }) });
        $("cycleOut").style.display = "block";
        if (d.ok) {
          const res = d.result || {}, dec = res.decision || {}, pol = res.policy || {}, ex = res.execution || {};
          $("cAction").textContent = dec.action || "\u2014";
          $("cAction").className = "dec-action serif " + (dec.used_fallback ? "" : "ok");
          $("cMeta").textContent = (dec.model || "\u2014") + " \u00b7 " + (dec.latency_ms || "\u2014") + "ms" + (dec.used_fallback ? " \u00b7 fallback" : "");
          $("cRationale").textContent = dec.rationale || "";
          $("cPolicy").innerHTML = `policy: <b>${pol.approved ? "approved" : "rejected"}</b> \u2192 ${pol.action || "\u2014"}${pol.override ? " \u00b7 override" : ""}`;
        } else { $("cRationale").textContent = "cycle failed: " + (d.error || "unknown"); }
      } catch (e) { $("cRationale").textContent = "cycle failed: " + e; }
      btn.disabled = false; btn.textContent = "run governance cycle";
      refreshLedger(); refreshStatus();
    });

    $("btnDaemon").addEventListener("click", async () => {
      const st = await api("/api/action/daemon");
      const action = st.running ? "stop" : "start";
      await api("/api/action/daemon", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, interval: 60, execute: $("execFlag").checked }) });
      refreshDaemon();
    });
    $("btnSetup").addEventListener("click", async () => {
      $("btnSetup").disabled = true;
      await api("/api/action/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol: $("setupSymbol").value, qty: $("setupQty").value }) });
      $("btnSetup").disabled = false; refreshStatus(); refreshLedger();
    });
    $("btnFlatten").addEventListener("click", async () => {
      $("btnFlatten").disabled = true;
      await api("/api/action/flatten", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      $("btnFlatten").disabled = false; refreshStatus(); refreshLedger();
    });
    $("btnDoctor").addEventListener("click", async () => {
      $("doctorBg").classList.add("open"); $("docPending").style.display = "block"; $("docBody").innerHTML = "";
      const d = await api("/api/action/doctor", { method: "POST" });
      $("docPending").style.display = "none";
      const body = $("docBody"); body.innerHTML = "";
      (d.checks || []).forEach(c => {
        const div = document.createElement("div");
        div.className = "doc-row";
        div.innerHTML = `<span class="st ${c.ok ? "p" : "f"}">${c.ok ? "PASS" : "FAIL"}</span><span class="nm">${c.name}</span><span class="dt">${c.detail || ""}</span>`;
        body.appendChild(div);
      });
      const sum = document.createElement("div");
      sum.style.cssText = "margin-top:12px;font-size:13px;color:" + (d.ok ? "var(--forest)" : "#C4787C");
      sum.textContent = (d.passed || 0) + "/" + (d.total || 0) + " checks passed";
      body.appendChild(sum);
    });
    $("docClose").addEventListener("click", () => $("doctorBg").classList.remove("open"));
    $("doctorBg").addEventListener("click", e => { if (e.target === $("doctorBg")) $("doctorBg").classList.remove("open"); });
  }
};
