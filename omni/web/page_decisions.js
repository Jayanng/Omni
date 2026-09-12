/* decisions page: full history of LLM decisions with policy verdicts */
window.__OMNI_PAGES["/decisions"] = {
  render() {
    return `
      <section class="card">
        <h2>decision history \u00b7 llm proposals with policy verdicts</h2>
        <table>
          <thead><tr><th>time</th><th>action</th><th>model</th><th class="r">latency</th><th>policy</th><th>executed</th></tr></thead>
          <tbody id="decBody"></tbody>
        </table>
      </section>
      <section class="card">
        <h2>latest rationale</h2>
        <div class="rationale" id="decRationale">no decision recorded yet</div>
      </section>`;
  },
  mount() {
    const { $, state, esc } = OMNI;
    function renderData() {
      const body = $("decBody"); body.innerHTML = "";
      const decs = state.ledger.filter(r => {
        const p = r.payload || {};
        return (r.kind === "decision" && p.decision) || (r.kind === "daemon_cycle" && p.decision);
      }).reverse();
      if (decs.length === 0) {
        body.innerHTML = `<tr><td colspan="6" class="empty">no decisions recorded yet</td></tr>`;
        $("decRationale").textContent = "no decision recorded yet";
        return;
      }
      let latestRationale = "";
      decs.slice(0, 50).forEach(rec => {
        const p = rec.payload || {};
        const d = p.decision || {}, pol = p.policy || {}, ex = p.execution || {};
        const tr = document.createElement("tr");
        const ts = String(rec.ts || "").replace("T", " ").slice(5, 19);
        tr.innerHTML = `<td class="mono" style="color:var(--faint)">${ts}</td>
          <td class="mono">${esc(d.action || "\u2014")}${d.used_fallback ? ' <span style="color:var(--risk);font-size:10px">FB</span>' : ""}</td>
          <td class="mono" style="color:var(--muted);font-size:11px">${esc((d.model || "\u2014").split("/").pop())}</td>
          <td class="r num">${d.latency_ms || "\u2014"}ms</td>
          <td>${pol.action ? `<b style="color:${pol.approved ? "var(--safe)" : "var(--risk)"};font-weight:500">${pol.approved ? "approved" : "rejected"}</b> ${esc(pol.action)}` : "\u2014"}</td>
          <td>${ex.reason ? (ex.executed ? '<span style="color:var(--safe)">yes</span>' : '<span style="color:var(--muted)">no</span>') : "\u2014"}</td>`;
        body.appendChild(tr);
        if (!latestRationale && d.rationale) latestRationale = d.rationale;
      });
      $("decRationale").textContent = latestRationale || "no rationale recorded";
    }
    renderData();
    OMNI.state.timers.push(setInterval(renderData, 8000));
  }
};
