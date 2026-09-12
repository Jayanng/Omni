/* positions page: open positions, account summary, daemon state */
window.__OMNI_PAGES["/positions"] = {
  render() {
    return `
      <section class="grid3">
        <div class="card metric"><div class="k">effective equity</div><div class="v num" id="pEquity">\u2014</div><div class="s">USDT</div></div>
        <div class="card metric"><div class="k">maintenance margin</div><div class="v num" id="pMmr">\u2014</div><div class="s">USDT</div></div>
        <div class="card metric"><div class="k">margin ratio</div><div class="v num" id="pRatio">\u2014</div><div class="s">maintenance / equity</div></div>
      </section>
      <section class="card">
        <h2>open positions \u00b7 demo account</h2>
        <table>
          <thead><tr><th>symbol</th><th>side</th><th class="r">total</th><th class="r">available</th><th class="r">mark price</th><th class="r">unrealised pnl</th><th class="r">leverage</th></tr></thead>
          <tbody id="posBody"></tbody>
        </table>
      </section>
      <section class="card">
        <h2>daemon</h2>
        <div class="row"><span class="k">state</span><span class="v" id="dState">\u2014</span></div>
        <div class="row"><span class="k">cycles completed</span><span class="v num" id="dCycles">\u2014</span></div>
        <div class="row"><span class="k">interval</span><span class="v num" id="dInterval">\u2014</span></div>
        <div class="row"><span class="k">execute enabled</span><span class="v" id="dExec">\u2014</span></div>
        <div class="row"><span class="k">last cycle</span><span class="v mono" id="dLast">\u2014</span></div>
      </section>`;
  },
  mount() {
    const { $, fmt, state } = OMNI;
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
