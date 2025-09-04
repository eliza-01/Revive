(function () {
  const $ = (sel) => document.querySelector(sel);

  async function refreshTPCats() {
    try {
      const cats = await pywebview.api.tp_get_categories();
      const sel = $("#tpCat");
      if (!sel) return;
      sel.innerHTML = "";
      sel.appendChild(new Option("— не выбрано —",""));
      (cats || []).forEach(c => sel.appendChild(new Option(c.title, c.id)));
      sel.value = "";
      await refreshTPLocs();
    } catch (_) {}
  }

  async function refreshTPLocs() {
    try {
      const cid = ($("#tpCat")?.value) || "";
      const locs = await pywebview.api.tp_get_locations(cid);
      const sel = $("#tpLoc");
      if (!sel) return;
      sel.innerHTML = "";
      sel.appendChild(new Option("— не выбрано —",""));
      (locs || []).forEach(l => sel.appendChild(new Option(l.title, l.id)));
      sel.value = "";
    } catch (_) {}
  }

  function wire() {
    const chk = $("#chkTP");
    if (chk) chk.addEventListener("change", e => { try { pywebview.api.tp_set_enabled(!!e.target.checked); } catch(_){} });

    const method = $("#tpMethod");
    if (method) method.addEventListener("change", e => { try { pywebview.api.tp_set_method(e.target.value); } catch(_){} });

    const cat = $("#tpCat");
    if (cat) cat.addEventListener("change", async e => {
      try { await pywebview.api.tp_set_category(e.target.value); } catch(_) {}
      await refreshTPLocs();
    });

    const loc = $("#tpLoc");
    if (loc) loc.addEventListener("change", e => { try { pywebview.api.tp_set_location(e.target.value); } catch(_){} });

    const now = $("#btnTPNow");
    if (now) now.addEventListener("click", () => { try { pywebview.api.tp_teleport_now(); } catch(_){} });

    const rows = $("#rows");
    if (rows) rows.addEventListener("change", e => { try { pywebview.api.tp_set_selected_row_id(e.target.value || ""); } catch(_){} });

    const clr = $("#btnRowClear");
    if (clr) clr.addEventListener("click", () => {
      const r = $("#rows");
      if (r) r.value = "";
      try { pywebview.api.tp_set_selected_row_id(""); } catch(_) {}
    });
  }

  window.UITP = {
    init() { wire(); },
    refreshTPCats, refreshTPLocs
  };
})();
