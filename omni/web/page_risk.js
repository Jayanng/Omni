/* risk page: collateral under stress flow, modelled numbers, verdict */
window.__OMNI_PAGES["/risk"] = {
  render() {
    return `
      <section class="grid2">
        <div class="card">
          <h2>collateral under stress</h2>
          <div class="flow-line"><span class="k">rToken gross</span><span class="arrow"></span><span class="v num" id="rGross">\u2014</span></div>
          <div class="flow-line"><span class="k">haircut</span><span class="arrow">applied</span><span class="v num" id="rHaircut">\u2014</span></div>
          <div class="flow-line"><span class="k">effective collateral</span><span class="arrow"></span><span class="v num info" id="rEff">\u2014</span></div>
          <div class="flow-line"><span class="k">scenario rToken / crypto</span><span class="arrow">shock</span><span class="v num" id="rShock">\u2014</span></div>
          <div class="flow-line"><span class="k">shocked equity</span><span class="arrow"></span><span class="v num" id="rShockedEq">\u2014</span></div>
          <div class="flow-line"><span class="k">shocked maintenance</span><span class="arrow"></span><span class="v num" id="rShockedMm">\u2014</span></div>
          <div class="flow-line"><span class="k">shocked buffer</span><span class="arrow"></span><span class="v num" id="rBuffer">\u2014</span></div>
          <div class="flow-line"><span class="k">modelled loss</span><span class="arrow"></span><span class="v num" id="rLoss">\u2014</span></div>
          <div class="verdict" id="rVerdict">no risk state recorded yet</div>
        </div>
        <div class="card">
          <h2>provenance</h2>
          <div class="row"><span class="k">recorded</span><span class="v mono" id="pTs">\u2014</span></div>
          <div class="row"><span class="k">rToken positions</span><span class="v num" id="pRcount">\u2014</span></div>
          <div class="row"><span class="k">haircut source</span><span class="v" id="pHairSrc">\u2014</span></div>
          <div class="row"><span class="k">scenario</span><span class="v" id="pScenario">\u2014</span></div>
          <h2 style="margin-top:16px">positions contributing</h2>
          <table><thead><tr><th>symbol</th><th class="r">qty</th><th class="r">value</th></tr></thead>
          <tbody id="pBody"></tbody></table>
        </div>
      </section>
      <section class="card">
        <h2>note</h2>
        <div style="font-size:12px;color:var(--muted);line-height:1.6">
          All values on this page are scenario estimates computed from the live portfolio, the published
          rToken fee schedule, and the current session classification. They are not guarantees of liquidation
          outcomes. Haircut values are modelled from the exchange fee schedule, not official Bitget rToken haircuts.
        </div>
      </section>`;
  },
  mount() {
    const { $, fmt, latestRisk } = OMNI;
    function renderData() {
      const p = latestRisk();
      const v = $("rVerdict");
      if (!p) { v.textContent = "no risk state recorded yet"; v.className = "verdict"; return; }
      const r = p.results || {}, m = p.modelled || {}, sc = p.scenario || {};
      $("rGross").textContent = m.rtoken_gross_value != null ? fmt(m.rtoken_gross_value, 0) + " USDT" : "\u2014";
      $("rHaircut").textContent = m.haircut_pct != null ? (m.haircut_pct * 100).toFixed(2) + "%" : "\u2014";
      $("rEff").textContent = m.rtoken_effective_collateral != null ? fmt(m.rtoken_effective_collateral, 0) + " USDT" : "\u2014";
      $("rShock").textContent = (sc.rtoken_shock_pct != null) ? (sc.rtoken_shock_pct * 100).toFixed(0) + "% / " + ((sc.crypto_shock_pct || 0) * 100).toFixed(0) + "%" : "\u2014";
      $("rShockedEq").textContent = r.shocked_equity != null ? fmt(r.shocked_equity, 0) + " USDT" : "\u2014";
      $("rShockedMm").textContent = r.shocked_maintenance != null ? fmt(r.shocked_maintenance, 0) + " USDT" : "\u2014";
      $("rBuffer").textContent = r.shocked_buffer_usdt != null ? fmt(r.shocked_buffer_usdt, 0) + " USDT" : "\u2014";
      $("rLoss").textContent = r.modelled_loss_usdt != null ? fmt(r.modelled_loss_usdt, 0) + " USDT (" + ((r.modelled_loss_pct_of_equity || 0) * 100).toFixed(1) + "%)" : "\u2014";
      if (r.breach === true) { v.textContent = "breach \u00b7 scenario exceeds maintenance"; v.className = "verdict"; }
      else if (r.needs_attention === true) { v.textContent = "needs attention \u00b7 loss above risk budget"; v.className = "verdict"; }
      else if (r.shocked_buffer_usdt != null) { v.textContent = "within budget"; v.className = "verdict ok"; }

      $("pTs").textContent = p.ts || "\u2014";
      const rpos = m.rtoken_positions || [];
      $("pRcount").textContent = rpos.length;
      $("pHairSrc").textContent = "modelled from published rToken fee schedule";
      $("pScenario").textContent = sc.rtoken_shock_pct != null ? (sc.rtoken_shock_pct * 100).toFixed(0) + "% rToken shock" : "\u2014";
      const body = $("pBody"); body.innerHTML = "";
      if (rpos.length === 0) body.innerHTML = `<tr><td colspan="3" class="empty">no rToken positions in modelled state</td></tr>`;
      rpos.forEach(pos => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td class="mono">${pos.symbol || "\u2014"}</td><td class="r num">${pos.total || pos.qty || "\u2014"}</td><td class="r num">${pos.value_usdt != null ? fmt(pos.value_usdt, 0) : "\u2014"}</td>`;
        body.appendChild(tr);
      });
    }
    renderData();
    OMNI.state.timers.push(setInterval(renderData, 5000));
  }
};
