/* ledger page: full audit trail */
window.__OMNI_PAGES["/ledger"] = {
  render() {
    return `
      <section class="card" style="flex:1;display:flex;flex-direction:column;min-height:0">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h2 style="margin:0">audit ledger \u00b7 immutable jsonl</h2>
          <span class="dec-meta" id="ledCount">\u2014</span>
        </div>
        <div style="overflow-y:auto;flex:1" id="ledBody"></div>
      </section>`;
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
