/* audit ledger page: full immutable record stream */
window.__OMNI_PAGES["/ledger"] = {
  render() {
    return `
      <div class="section-label">AUDIT TRAIL</div>
      <div class="section-title serif">Immutable ledger</div>
      <div class="card" style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
          <h3 style="margin:0">JSONL RECORDS</h3>
          <span class="dec-meta" id="ledCount">\u2014</span>
        </div>
        <div style="overflow-y:auto;flex:1" id="ledBody"></div>
      </div>`;
  },
  mount() {
    const { $, state, esc, summarize } = OMNI;
    function renderData() {
      const body = $("ledBody"); body.innerHTML = "";
      const records = state.ledger.slice().reverse();
      $("ledCount").textContent = records.length + " records";
      if (records.length === 0) { body.innerHTML = `<div class="empty">ledger is empty</div>`; return; }
      records.forEach(rec => {
        const div = document.createElement("div");
        const cls = rec.kind === "decision" ? "dec" : (rec.kind === "execution" ? "exec" : "");
        const ts = String(rec.ts || "").replace("T", " ").slice(0, 19);
        div.className = "entry " + cls;
        div.innerHTML = `<span class="ts mono">${ts}</span><span class="kind mono">${esc(rec.kind || "")}</span><span class="txt">${esc(summarize(rec))}</span>`;
        body.appendChild(div);
      });
    }
    renderData();
    OMNI.state.timers.push(setInterval(renderData, 8000));
  }
};
