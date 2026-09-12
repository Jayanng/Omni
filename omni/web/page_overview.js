/* overview page: two clocks, equity strip, session, latest decision summary */
window.__OMNI_PAGES["/"] = {
  render() {
    return `
      <section class="clocks">
        <div class="clock live">
          <div class="who">crypto \u00b7 24/7</div>
          <div class="read num" id="cryptoClock">--:--:--</div>
          <div class="state">live</div>
        </div>
        <div class="clock frozen">
          <div class="who" id="equityWho">us equity</div>
          <div class="read num" id="equityRead">\u2014</div>
          <div class="state" id="equityState">\u2014</div>
          <div class="reopens">
            <div class="k">cash open</div>
            <div class="v num" id="countdown">\u2014</div>
          </div>
        </div>
      </section>
      <section class="grid3">
        <div class="card metric"><div class="k">effective equity</div><div class="v num" id="mEquity">\u2014</div><div class="s">observed, demo account</div></div>
        <div class="card metric"><div class="k">margin ratio</div><div class="v num" id="mRatio">\u2014</div><div class="s">maintenance / equity</div></div>
        <div class="card metric"><div class="k">maintenance margin</div><div class="v num" id="mMmr">\u2014</div><div class="s">USDT</div></div>
      </section>
      <section class="card">
        <h2>equity history \u00b7 real observations</h2>
        <div id="sparkWrap"><svg id="sparkSvg"></svg></div>
        <div class="spark-note" id="sparkNote">\u2014</div>
      </section>
      <section class="grid2">
        <div class="card">
          <h2>session</h2>
          <div class="row"><span class="k">regime</span><span class="v mono" id="sRegime">\u2014</span></div>
          <div class="row"><span class="k">liquidity</span><span class="v mono" id="sLiq">\u2014</span></div>
          <div class="row"><span class="k">mark confidence</span><span class="v mono" id="sConf">\u2014</span></div>
          <div class="row"><span class="k">cash market</span><span class="v mono" id="sCash">\u2014</span></div>
          <div class="row"><span class="k">weekend tradable</span><span class="v mono" id="sWeekend">\u2014</span></div>
        </div>
        <div class="card">
          <h2>latest decision</h2>
          <div class="dec-action mono" id="dAction">\u2014</div>
          <div class="dec-meta" id="dMeta">no decision recorded yet</div>
          <div class="rationale" id="dRationale" style="display:none"></div>
          <div class="policy-line" id="dPolicy"></div>
        </div>
      </section>`;
  },
  mount() {
    const { $, fmt, state, countdownToCashOpen, equitySeries, latestDecision } = OMNI;
    function tickClock() {
      const now = new Date();
      $("cryptoClock").textContent = now.toISOString().slice(11, 19);
      const cashOpen = state.status && state.status.session && state.status.session.cash_market_open;
      $("equityRead").textContent = cashOpen ? now.toLocaleTimeString("en-US", { timeZone: "America/New_York", hour12: false }) : "16:00:00";
      $("equityState").textContent = cashOpen ? "open" : "closed";
      document.querySelector(".clock.frozen").className = "clock " + (cashOpen ? "live" : "frozen");
      $("countdown").textContent = cashOpen ? "open" : countdownToCashOpen();
      const rtoken = state.status && state.status.rtoken_symbol;
      $("equityWho").textContent = "us equity \u00b7 " + (rtoken ? rtoken.replace(/^R/, "").replace(/USDT$/, "").toLowerCase() : "\u2014");
    }
    tickClock();
    OMNI.state.timers.push(setInterval(tickClock, 1000));

    function renderData() {
      const st = state.status || {};
      const s = st.session || {};
      $("mEquity").textContent = st.equity == null ? "\u2014" : fmt(st.equity, 0);
      $("mMmr").textContent = st.mmr == null ? "\u2014" : fmt(st.mmr);
      const ratio = st.margin_ratio;
      $("mRatio").textContent = ratio == null ? "\u2014" : (ratio * 100).toFixed(4) + "%";
      $("sRegime").textContent = s.regime || "\u2014";
      $("sLiq").textContent = s.liquidity_tier || "\u2014";
      $("sConf").textContent = s.mark_confidence || "\u2014";
      $("sCash").textContent = s.cash_market_open == null ? "\u2014" : (s.cash_market_open ? "open" : "closed");
      $("sCash").className = "v mono " + (s.cash_market_open ? "ok" : "warn");
      $("sWeekend").textContent = s.weekend_tradable == null ? "\u2014" : (s.weekend_tradable ? "yes" : "no");

      const pts = equitySeries();
      const svg = $("sparkSvg");
      if (pts.length < 2) { svg.innerHTML = ""; $("sparkNote").textContent = "collecting equity observations (" + pts.length + ")"; }
      else {
        const W = 600, H = 56, pad = 3, vals = pts.map(p => p.eq);
        const min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
        const xs = pts.map((_, i) => pad + i * (W - 2 * pad) / (pts.length - 1));
        const ys = vals.map(v => H - pad - (v - min) * (H - 2 * pad) / span);
        const d = xs.map((x, i) => (i ? "L" : "M") + x.toFixed(1) + "," + ys[i].toFixed(1)).join(" ");
        const mi = vals.indexOf(min);
        svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
        svg.innerHTML = `<path d="${d}" fill="none" stroke="#58A6FF" stroke-width="1.5"/><circle cx="${xs[mi].toFixed(1)}" cy="${ys[mi].toFixed(1)}" r="3" fill="#FFB020"/>`;
        $("sparkNote").textContent = pts.length + " real observations \u00b7 " + fmt(min, 0) + " \u2013 " + fmt(max, 0) + " USDT";
      }

      const ld = latestDecision();
      if (ld) {
        const dec = ld.decision;
        $("dAction").textContent = dec.action;
        $("dAction").className = "dec-action mono " + (dec.used_fallback ? "" : "ok");
        const lat = dec.latency_ms || 0;
        $("dMeta").textContent = (dec.model || "\u2014") + " \u00b7 " + (dec.latency_ms || "\u2014") + "ms" + (lat > 30000 ? " \u00b7 SLOW" : "") + (dec.used_fallback ? " \u00b7 fallback" : "");
        if (dec.rationale) { $("dRationale").style.display = "block"; $("dRationale").textContent = dec.rationale; }
        const pol = ld.policy;
        if (pol.action) $("dPolicy").innerHTML = `policy: <b>${pol.approved ? "approved" : "rejected"}</b> \u2192 ${pol.action}${pol.override ? " \u00b7 override" : ""}`;
      }
    }
    renderData();
    OMNI.state.timers.push(setInterval(renderData, 5000));
  }
};
