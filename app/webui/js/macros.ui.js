(function () {
  const $ = (sel) => document.querySelector(sel);

  const KEYS = ["1","2","3","4","5","6","7","8","9","0"];

  function create(tag, attrs = {}, text = "") {
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "class") el.className = v; else el.setAttribute(k, v);
    });
    if (text) el.textContent = text;
    return el;
  }

  function buildMacrosRow(val) {
    const sel = create("select", { class: "key", "data-scope": "macros-key" });
    KEYS.forEach(k => sel.appendChild(create("option", { value: k }, k)));
    sel.value = (val && KEYS.includes(String(val))) ? String(val) : "1";
    sel.addEventListener("change", () => {
      try { pywebview.api.macros_set_sequence(readMacrosSequence()); } catch (_) {}
    });
    return sel;
  }

  function readMacrosSequence() {
    const cont = $("#macrosRows");
    if (!cont) return [];
    return Array.from(cont.querySelectorAll('select[data-scope="macros-key"]')).map(x => x.value);
  }

  function ensureAtLeastOneRow() {
    const cont = $("#macrosRows");
    if (!cont) return;
    if (!cont.children.length) cont.appendChild(buildMacrosRow("1"));
    try { pywebview.api.macros_set_sequence(readMacrosSequence()); } catch (_) {}
  }

  function wire() {
    const add = $("#btnAddRow");
    if (add) add.addEventListener("click", () => {
      const cont = $("#macrosRows");
      if (!cont) return;
      cont.appendChild(buildMacrosRow("1"));
      try { pywebview.api.macros_set_sequence(readMacrosSequence()); } catch (_) {}
    });

    const del = $("#btnDelRow");
    if (del) del.addEventListener("click", () => {
      const cont = $("#macrosRows");
      if (!cont) return;
      if (cont.children.length > 1) cont.removeChild(cont.lastElementChild);
      try { pywebview.api.macros_set_sequence(readMacrosSequence()); } catch (_) {}
    });

    const chk = $("#chkMacros");
    if (chk) chk.addEventListener("change", e => { try { pywebview.api.macros_set_enabled(!!e.target.checked); } catch(_){} });

    const alw = $("#chkMacrosAlways");
    if (alw) alw.addEventListener("change", e => { try { pywebview.api.macros_set_run_always(!!e.target.checked); } catch(_){} });

    const delay = $("#macrosDelay");
    if (delay) delay.addEventListener("change", e => { try { pywebview.api.macros_set_delay(parseFloat(e.target.value || "0")); } catch(_){} });

    const dur = $("#macrosDur");
    if (dur) dur.addEventListener("change", e => { try { pywebview.api.macros_set_duration(parseFloat(e.target.value || "0")); } catch(_){} });

    const once = $("#btnMacrosOnce");
    if (once) once.addEventListener("click", () => { try { pywebview.api.macros_run_once(); } catch(_){} });
  }

  window.UIMacros = {
    init() {
      ensureAtLeastOneRow();
      wire();
    }
  };
})();
