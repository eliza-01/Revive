// app/webui/js/macros.ui.js
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

  function buildKeySelect(val) {
    const sel = create("select", { class: "key", "data-scope": "macros-key" });
    KEYS.forEach(k => sel.appendChild(create("option", { value: k }, k)));
    sel.value = (val && KEYS.includes(String(val))) ? String(val) : "1";
    sel.addEventListener("change", pushRowsToBackend);
    return sel;
  }

  function buildNumberInput({min, max, step, ds, placeholder}) {
    const inp = create("input", { type: "number", "data-scope": ds });
    inp.min = String(min);
    inp.max = String(max);
    inp.step = String(step);
    if (placeholder) inp.placeholder = placeholder;
    inp.addEventListener("change", ()=>{
      const v = parseFloat(inp.value || "0");
      const clamped = isFinite(v) ? Math.max(min, Math.min(max, v)) : 0;
      inp.value = String(clamped);
      pushRowsToBackend();
    });
    return inp;
  }

  function buildRow(row) {
    // row: { key, cast_s, repeat_s }
    const wrap = create("div", { class: "macros-grid macros-row" });

    // col1: удалить
    const colDel = create("div");
    const btnDel = create("button", { class: "icon-btn danger", title: "Удалить" }, "−");
    btnDel.addEventListener("click", () => {
      const cont = $("#macrosRows");
      if (!cont) return;
      cont.removeChild(wrap);
      ensureAtLeastOneRow();
      pushRowsToBackend();
    });
    colDel.appendChild(btnDel);

    // col2: выбор кнопки
    const colKey = create("div");
    const keySel = buildKeySelect(row && row.key);
    colKey.appendChild(keySel);

    // col3: кастуется (сек)
    const colCast = create("div");
    const castWrap = create("div", { class: "macros-field" });
    const castInp = buildNumberInput({min:0, max:99, step:1, ds:"macros-cast", placeholder:"0..99"});
    castInp.value = (row && Number.isFinite(row.cast_s)) ? String(row.cast_s) : "0";
    castWrap.appendChild(castInp);
    castWrap.appendChild(create("span", { class:"hint" }, "сек."));
    colCast.appendChild(castWrap);

    // col4: повторять через (сек)
    const colRep = create("div");
    const repWrap = create("div", { class: "macros-field" });
    const repInp = buildNumberInput({min:0, max:9999, step:1, ds:"macros-repeat", placeholder:"0..9999"});
    repInp.value = (row && Number.isFinite(row.repeat_s)) ? String(row.repeat_s) : "0";
    repWrap.appendChild(repInp);
    repWrap.appendChild(create("span", { class:"hint" }, "сек."));
    colRep.appendChild(repWrap);

    wrap.appendChild(colDel);
    wrap.appendChild(colKey);
    wrap.appendChild(colCast);
    wrap.appendChild(colRep);

    return wrap;
  }

  function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }

  function readRows() {
    const cont = $("#macrosRows");
    if (!cont) return [];
    const rows = [];
    cont.querySelectorAll(".macros-row").forEach(r=>{
      const key = (r.querySelector('[data-scope="macros-key"]')||{}).value || "1";
      const cast = parseFloat((r.querySelector('[data-scope="macros-cast"]')||{}).value || "0") || 0;
      const rep  = parseFloat((r.querySelector('[data-scope="macros-repeat"]')||{}).value || "0") || 0;
      rows.push({ key, cast_s: clamp(cast, 0, 99), repeat_s: clamp(rep, 0, 9999) });
    });
    return rows;
  }

  function pushRowsToBackend(){
    try {
      const rows = readRows();
      pywebview.api.macros_set_rows(rows);
    } catch(_){}
  }

  function ensureAtLeastOneRow() {
    const cont = $("#macrosRows");
    if (!cont) return;
    if (!cont.children.length) cont.appendChild(buildRow({ key:"1", cast_s:0, repeat_s:0 }));
  }

  function wire() {
    const add = $("#btnAddRow");
    if (add) add.addEventListener("click", () => {
      const cont = $("#macrosRows");
      if (!cont) return;
      cont.appendChild(buildRow({ key:"1", cast_s:0, repeat_s:0 }));
      pushRowsToBackend();
    });

    const chk = $("#chkMacros");
    if (chk) chk.addEventListener("change", e => {
      const enabled = !!e.target.checked;
      try {
        // ВАЖНО: новый бэкенд разделяет флаги; включаем оба.
        pywebview.api.macros_set_enabled(enabled);
        pywebview.api.macros_set_repeat_enabled(enabled);
      } catch(_){}
    });
  }

  window.UIMacros = {
    init() {
      const cont = $("#macrosRows");
      if (cont) {
        cont.appendChild(buildRow({ key:"1", cast_s:0, repeat_s:0 }));
        // синхронизируем пул сразу после первичной отрисовки
        pushRowsToBackend();
      }
      wire();
    }
  };
})();
