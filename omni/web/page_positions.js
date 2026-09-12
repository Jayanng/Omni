/* positions & decisions page: merged view */
window.__OMNI_PAGES["/positions"] = {
  render() {
    return `
      <div class="section-label">YOUR ACCOUNT</div>
      <div class="section-title serif">Positions & decisions</div>
      <div class="grid3">
        <div class="stat-card"><div class="label">EFFECTIVE EQUITY</div><div class="value num" id="pEquity">\u2014</div><div class="sub">USDT</div></div>
        <div class="stat-card"><div class="label">MAINTENANCE MARGIN</div><div class="value num" id="pMmr">\u2014</div><div class="sub">USDT</div></div>
        <div class="stat-card"><div class="label">MARGIN RATIO</div><div class="value num" id="pRatio">\u2014</div><div class="sub">maintenance / equity</div></div>
      </div>
      <div class="card">
        <h2>Open positions \u00b7 demo account</h2>
        <table>
          <thead><tr><th>symbol</th><th>side</th><th class="r">total</th><th class="r">available</th><th class="r">mark price</th><th class="r">unrealised pnl</th><th class="r">leverage</th></tr></thead>
          <tbody id="posBody"></tbody>
        </table>
      </div>
      <div class="grid2">
        <div class="card">
          <h2>Decision history</h2>
          <table>
            <thead><tr><th>time</th><th>action</th><th>model</th><th class="r">latency</th><th>policy</th></tr></thead>
            <tbody id="decBody"></tbody>
          </table>
        </div>
        <div class="card">
          <h2>Daemon</h2>
          <div class="row"><span class="k">state</span><span class="v" id="dState">\u2014</span></div>
          <div class="row"><span class="k">cycles completed</span><span class="v num" id="dCycles">\u2014</span></div>
          <div class="row"><span class="k">interval</span><span class="v num" id="dInterval">\u2014</span></div>
          <div class="row"><span class="k">execute enabled</span><span class="v" id="dExec">\u2014</span></div>
          <div class="row"><span class="k">last cycle</span><span class="v mono" id="dLast">\u2014</span></div>
        </div>
      </div>`;
  },
  mount() {
    const { $, fmt, state, esc } = OMNI;
    function renderData() {
      const st = state.status || {};
      $("pEquity").textContent = st.equity == null ? "\u2014" : fmt(st.equity, 0);
      $("pMmr").textContent = st.mmr == null ? "\u2014" : fmt(st.mmr);
      $("pRatio").textContent = st.margin_ratio == null ? "\u2014" : (st.margin_ratio * 100).toFixed(4) + "%";
      const body = $("posBody"); body.innerHTML = "";
      const positions = st.positions || [];
      if (positions.length === 0) {
        body.innerHTML = `<tr><td colspan="7" class="empty">no open positions</td></tr>`;
      }
      positions.forEach(p => {
        const side = (p.posSide || p.holdSide || "").toLowerCase();
        const tr = document.createElement("tr");
        tr.innerHTML = `<td class="mono">${p.symbol || "\u2014"}</td>
          <td><span class="pos-side ${side}">${side || "\u2014"}</span></td>
          <td class="r num">${p.total || "\u2014"}</td>
          <td class="r num">${p.available || "\u2014"}</td>
          <td class="r num">${p.markPrice || "\u2014"}</td>
          <td class="r num">${p.unrealizedPL || "\u2014"}</td>
          <td class="r num">${p.leverage || "\u2014"}</td>`;
        body.appendChild(tr);
      });

      const decs = state.ledger.filter(r => {
        const p = r.payload || {};
        return (r.kind === "decision" && p.decision) || (r.kind === "daemon_cycle" && p.decision);
      }).reverse();
      const decBody = $("decBody"); decBody.innerHTML = "";
      if (decs.length === 0) {
        decBody.innerHTML = `<tr><td colspan="5" class="empty">no decisions recorded yet</td></tr>`;
      }
      decs.slice(0, 20).forEach(rec => {
        const p = rec.payload || {};
        const d = p.decision || {}, pol = p.policy || {};
        const tr = document.createElement("tr");
        const ts = String(rec.ts || "").replace("T", " ").slice(5, 19);
        tr.innerHTML = `<td class="mono" style="color:var(--faint)">${ts}</td>
          <td class="mono">${esc(d.action || "\u2014")}${d.used_fallback ? ' <span style="color:#C4787C;font-size:10px">FB</span>' : ""}</td>
          <td class="mono" style="color:var(--muted);font-size:11px">${esc((d.model || "\u2014").split("/").pop())}</td>
          <td class="r num">${d.latency_ms || "\u2014"}ms</td>
          <td>${pol.action ? `<b style="color:${pol.approved ? "var(--forest)" : "#C4787C"};font-weight:500">${pol.approved ? "approved" : "rejected"}</b>` : "\u2014"}</td>`;
        decBody.appendChild(tr);
      });

      const d = state.daemon || {};
      $("dState").textContent = d.running ? "running" : "idle";
      $("dState").className = "v " + (d.running ? "ok" : "dim");
      $("dCycles").textContent = d.cycles_completed != null ? d.cycles_completed : "\u2014";
      $("dInterval").textContent = d.interval != null ? d.interval + "s" : "\u2014";
      $("dExec").textContent = d.execute == null ? "\u2014" : (d.execute ? "yes" : "no");
      $("dExec").className = "v " + (d.execute ? "warn" : "ok");
      $("dLast").textContent = d.last_cycle_at || "\u2014";
    }
    renderData();
    OMNI.state.timers.push(setInterval(renderData, 5000));
  }
};
