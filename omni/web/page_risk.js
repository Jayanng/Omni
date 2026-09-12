/* risk model page: collateral under stress flow */
window.__OMNI_PAGES["/risk"] = {
  render() {
    return `
      <div class="section-label">RISK MODEL</div>
      <div class="section-title serif">Collateral under stress</div>
      <div class="grid2">
        <div class="card">
          <h2>Scenario analysis</h2>
          <div class="flow-line"><span class="k">rToken gross</span><span class="arrow"></span><span class="v num" id="rGross">\u2014</span></div>
          <div class="flow-line"><span class="k">haircut</span><span class="arrow">applied</span><span class="v num" id="rHaircut">\u2014</span></div>
          <div class="flow-line"><span class="k">effective collateral</span><span class="arrow"></span><span class="v num info" id="rEff">\u2014</span></div>
          <div class="flow-line"><span class="k">scenario rToken / crypto</span><span class="arrow">shock</span><span class="v num" id="rShock">\u2014</span></div>
          <div class="flow-line"><span class="k">shocked equity</span><span class="arrow"></span><span class="v num" id="rShockedEq">\u2014</span></div>
          <div class="flow-line"><span class="k">shocked maintenance</span><span class="arrow"></span><span class="v num" id="rShockedMm">\u2014</span></div>
          <div class="flow-line"><span class="k">shocked buffer</span><span class="arrow"></span><span class="v num" id="rBuffer">\u2014</span></div>
          <div class="flow-line"><span class="k">modelled loss</span><span class="arrow"></span><span class="v num" id="rLoss">\u2014</span></div>
          <div class="verdict neutral" id="rVerdict">no risk state recorded yet</div>
        </div>
        <div class="card">
          <h2>Provenance</h2>
          <div class="row"><span class="k">recorded</span><span class="v mono" id="pTs">\u2014</span></div>
          <div class="row"><span class="k">rToken positions</span><span class="v num" id="pRcount">\u2014</span></div>
          <div class="row"><span class="k">haircut source</span><span class="v" id="pHairSrc">\u2014</span></div>
          <div class="row"><span class="k">shock method</span><span class="v" id="pScenario">\u2014</span></div>
          <h3 style="margin-top:20px">Positions contributing</h3>
          <table><thead><tr><th>symbol</th><th class="r">qty</th><th class="r">value</th></tr></thead>
          <tbody id="pBody"></tbody></table>
        </div>
      </div>
      <div class="card">
        <h3>NOTE</h3>
        <div style="font-size:13px;color:var(--muted);line-height:1.7">
          The collateral haircut is read live from the venue's published discount-rate schedule, the
          maintenance-margin ladder comes from the venue's position-tier endpoint, and the scenario shocks are
          derived from each instrument's realised candle history. The provenance card shows the source and the
          verification state of each. These remain scenario estimates, not exchange guarantees.
        </div>
      </div>`;
  },
  mount() {
    const { $, fmt, latestRisk } = OMNI;
    function renderData() {
      const p = latestRisk();
      const v = $("rVerdict");
      if (!p) { v.textContent = "no risk state recorded yet"; v.className = "verdict neutral"; return; }
      const r = p.results || {}, m = p.modelled || {}, sc = p.scenario || {};
      $("rGross").textContent = m.rtoken_gross_value != null ? fmt(m.rtoken_gross_value, 0) + " USDT" : "\u2014";
      $("rHaircut").textContent = m.haircut_pct != null ? (m.haircut_pct * 100).toFixed(2) + "%" : "\u2014";
      $("rEff").textContent = m.rtoken_effective_collateral != null ? fmt(m.rtoken_effective_collateral, 0) + " USDT" : "\u2014";
      $("rShock").textContent = (sc.rtoken_shock_pct != null) ? (sc.rtoken_shock_pct * 100).toFixed(0) + "% / " + ((sc.crypto_shock_pct || 0) * 100).toFixed(0) + "%" : "\u2014";
      $("rShockedEq").textContent = r.shocked_equity != null ? fmt(r.shocked_equity, 0) + " USDT" : "\u2014";
      $("rShockedMm").textContent = r.shocked_maintenance != null ? fmt(r.shocked_maintenance, 0) + " USDT" : "\u2014";
      $("rBuffer").textContent = r.shocked_buffer_usdt != null ? fmt(r.shocked_buffer_usdt, 0) + " USDT" : "\u2014";
      $("rLoss").textContent = r.modelled_loss_usdt != null ? fmt(r.modelled_loss_usdt, 0) + " USDT (" + ((r.modelled_loss_pct_of_equity || 0) * 100).toFixed(1) + "%)" : "\u2014";
      if (r.breach === true) { v.textContent = "breach \u00b7 scenario exceeds maintenance"; v.className = "verdict warn"; }
      else if (r.needs_attention === true) { v.textContent = "needs attention \u00b7 loss above risk budget"; v.className = "verdict warn"; }
      else if (r.shocked_buffer_usdt != null) { v.textContent = "within budget"; v.className = "verdict ok"; }

      $("pTs").textContent = p.ts || "\u2014";
      const rpos = m.rtoken_positions || [];
      $("pRcount").textContent = rpos.length;
      const src = (m.haircut_source || "").trim();
      const verified = m.haircut_verified === true;
      $("pHairSrc").textContent = src || "\u2014";
      $("pHairSrc").className = "v " + (verified ? "ok" : "warn");
      const prov = (sc.provenance || {});
      const rtokenProv = prov.rtoken || {};
      $("pScenario").textContent = rtokenProv.method
        ? rtokenProv.method + (rtokenProv.samples ? " (n=" + rtokenProv.samples + ")" : "")
        : (sc.rtoken_shock_pct != null ? (sc.rtoken_shock_pct * 100).toFixed(0) + "% rToken shock" : "\u2014");
      $("pHairSrc").title = src;
      const body = $("pBody"); body.innerHTML = "";
      if (rpos.length === 0) body.innerHTML = `<tr><td colspan="3" class="empty">no rToken positions in modelled state</td></tr>`;
      rpos.forEach(pos => {
        const tr = document.createElement("tr");
        const qty = pos.qty != null ? pos.qty : (pos.total != null ? pos.total : null);
        const gross = pos.gross_value != null ? fmt(pos.gross_value, 0) : "\u2014";
        tr.innerHTML = `<td class="mono">${pos.symbol || "\u2014"}</td>` +
          `<td class="r num">${qty != null ? qty : "\u2014"}</td>` +
          `<td class="r num">${gross}</td>`;
        body.appendChild(tr);
      });
    }
    renderData();
    OMNI.state.timers.push(setInterval(renderData, 5000));
  }
};
