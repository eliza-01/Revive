// app/webui/js/macros.ui.js
(function () {
  const $ = (sel) => document.querySelector(sel);

  const KEYS = ["1","2","3","4","5","6","7","8","9","0"];
  let ac = null;                // AbortController для дедупликации обработчиков
  let _booting = false;         // подавляем любые пуши в пул во время гидратации

  // ---------- helpers ----------
  function create(tag, attrs = {}, text = "") {
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "class") el.className = v; else el.setAttribute(k, v);
    });
    if (text) el.textContent = text;
    return el;
  }
  function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }

  async function waitForApi(methodNames, timeoutMs = 5000, intervalMs = 100) {
    const names = Array.isArray(methodNames) ? methodNames : [methodNames];
    const t0 = Date.now();
    return new Promise(resolve => {
      const tick = () => {
        const ok = window.pywebview && window.pywebview.api && names.every(n => typeof window.pywebview.api[n] === "function");
        if (ok) return resolve(true);
        if (Date.now() - t0 >= timeoutMs) return resolve(false);
        setTimeout(tick, intervalMs);
      };
      tick();
    });
  }

  // ---------- UI builders ----------
  function buildKeySelect(val) {
    const sel = create("select", { class: "key", "data-scope": "macros-key" });
    KEYS.forEach(k => sel.appendChild(create("option", { value: k }, k)));
    sel.value = (val && KEYS.includes(String(val))) ? String(val) : "1";
    sel.addEventListener("change", pushRowsToBackend, { signal: ac?.signal });
    return sel;
  }

  function buildNumberInput({min, max, step, ds, placeholder}) {
    const inp = create("input", { type: "number", "data-scope": ds });
    inp.min = String(min);
    inp.max = String(max);
    inp.step = String(step);
    if (placeholder) inp.placeholder = placeholder;

    const onChange = () => {
      const v = parseFloat(inp.value || "0");
      const clamped = isFinite(v) ? clamp(v, min, max) : 0;
      inp.value = String(clamped);
      pushRowsToBackend();
    };

    inp.addEventListener("change", onChange, { signal: ac?.signal });
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
    }, { signal: ac?.signal });
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

  // ---------- state <-> UI ----------
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

  function setRows(rows) {
    const cont = $("#macrosRows");
    if (!cont) return;
    cont.innerHTML = "";
    (rows && rows.length ? rows : [{ key:"1", cast_s:0, repeat_s:0 }])
      .forEach(r => cont.appendChild(buildRow(r)));
  }

  function ensureAtLeastOneRow() {
    const cont = $("#macrosRows");
    if (!cont) return;
    if (cont.querySelectorAll(".macros-row").length === 0) {
      cont.appendChild(buildRow({ key:"1", cast_s:0, repeat_s:0 }));
    }
  }

  function pushRowsToBackend(){
    if (_booting) return; // не синкаем пул, пока идёт загрузка
    try {
      const rows = readRows();
      if (window.pywebview && window.pywebview.api && typeof pywebview.api.macros_set_rows === "function") {
        pywebview.api.macros_set_rows(rows);
      }
    } catch(_) {}
  }

  // ---------- hydrate ----------
  async function hydrateFromBackend() {
    _booting = true;
    try {
      let enabled = false;
      let repeatEnabled = false;
      let rows = [];

      // 1) предпочтительно — новый API
      if (await waitForApi(["macros_set_rows"], 1) && window.pywebview?.api?.macros_get) {
        try {
          const r = await pywebview.api.macros_get();
          if (r && r.ok) {
            enabled = !!r.enabled;
            repeatEnabled = !!r.repeat_enabled;
            rows = Array.isArray(r.rows) ? r.rows : [];
          }
        } catch (_) { /* fallthrough */ }
      }

      // 2) фолбэк — достаём напрямую из пула
      if (!rows.length && window.pywebview?.api?.pool_dump) {
        try {
          const dump = await pywebview.api.pool_dump();
          const m = dump && dump.state && dump.state.features && dump.state.features.macros;
          if (m) {
            enabled = !!m.enabled;
            repeatEnabled = !!m.repeat_enabled;
            rows = Array.isArray(m.rows) ? m.rows : [];
          }
        } catch (_) { /* ignore */ }
      }

      // применяем в UI
      setRows(rows);
      ensureAtLeastOneRow();

      const chk = $("#chkMacros");
      if (chk) chk.checked = !!enabled;

      // если нужен отдельный чекбокс для повтора — тут можно выставить
      // (сейчас один чекбокс рулит и enabled, и repeat_enabled)
    } finally {
      _booting = false;
    }
  }

  // ---------- events wiring ----------
  function wire() {
    // Снимаем все старые обработчики этого модуля перед перевешиванием
    if (ac) ac.abort();
    ac = new AbortController();
    const signal = ac.signal;

    const add = $("#btnAddRow");
    if (add) add.addEventListener("click", () => {
      const cont = $("#macrosRows");
      if (!cont) return;
      cont.appendChild(buildRow({ key:"1", cast_s:0, repeat_s:0 }));
      pushRowsToBackend();
    }, { signal });

    const chk = $("#chkMacros");
    if (chk) chk.addEventListener("change", e => {
      const on = !!e.target.checked;
      try {
        if (window.pywebview && window.pywebview.api) {
          if (typeof pywebview.api.macros_set_enabled === "function")        pywebview.api.macros_set_enabled(on);
          if (typeof pywebview.api.macros_set_repeat_enabled === "function") pywebview.api.macros_set_repeat_enabled(on);
        }
      } catch(_) {}
    }, { signal });
  }

  // ---------- public API ----------
  window.UIMacros = {
    async init() {
      wire();
      await hydrateFromBackend();   // подтягиваем prefs→pool→UI, НО не перезаписываем пул
    },

    // Полный сброс раздела (и на бэке, и в UI)
    reset() {
      try {
        if (window.pywebview && window.pywebview.api) {
          if (pywebview.api.macros_set_enabled)        pywebview.api.macros_set_enabled(false);
          if (pywebview.api.macros_set_repeat_enabled) pywebview.api.macros_set_repeat_enabled(false);
          if (pywebview.api.macros_set_rows)           pywebview.api.macros_set_rows([]);
        }
      } catch(_) {}

      const cont = $("#macrosRows");
      if (cont) {
        cont.innerHTML = "";
        cont.appendChild(buildRow({ key:"1", cast_s:0, repeat_s:0 }));
      }
      const chk = $("#chkMacros");
      if (chk) chk.checked = false;
    }
  };

  // ---------- boot ----------
  function boot() {
    if (window.UIMacros && typeof window.UIMacros.init === "function") {
      window.UIMacros.init();
    }
  }
  if (window.pywebview && window.pywebview.api) {
    boot();
  } else {
    document.addEventListener("pywebviewready", boot);
    document.addEventListener("DOMContentLoaded", () => {
      // страховочный поллинг, если событие по какой-то причине не пришло
      let tries = 0;
      const t = setInterval(() => {
        if (window.pywebview && window.pywebview.api) {
          clearInterval(t);
          boot();
        } else if (++tries > 60) {
          clearInterval(t);
        }
      }, 100);
    });
  }
})();
