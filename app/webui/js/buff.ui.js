// app/webui/js/buff.ui.js
(function () {
  const $ = (sel) => document.querySelector(sel);

  function fillSelect(el, arr, current) {
    if (!el) return;
    el.innerHTML = "";
    const list = Array.isArray(arr) ? arr : [];
    if (!list.length) {
      el.appendChild(new Option("—", "")); // пусто
      el.disabled = true;
      return;
    }
    for (const v of list) el.appendChild(new Option(v, v));
    el.value = (current && list.includes(current)) ? current : list[0];
    el.disabled = false;
  }

  function wire() {
    const chk = $("#chkBuff");
    if (chk) {
      chk.addEventListener("change", e => {
        try { pywebview.api.buff_set_enabled(!!e.target.checked); } catch(_) {}
      });
    }

    const mode = $("#buffMode");
    if (mode) {
      mode.addEventListener("change", e => {
        try { pywebview.api.buff_set_mode(e.target.value); } catch(_) {}
      });
    }

    const method = $("#buffMethod");
    if (method) {
      method.addEventListener("change", e => {
        try {
          if (pywebview.api.buff_set_method) {
            pywebview.api.buff_set_method(e.target.value);
          }
        } catch(_) {}
      });
    }

    const once = $("#btnBuffOnce");
    if (once) {
      once.addEventListener("click", async () => {
        try { await pywebview.api.buff_run_once(); } catch(_) {}
      });
    }
  }

  async function loadInitStateAndFill() {
    try {
      if (!window.pywebview || !pywebview.api || !pywebview.api.get_init_state) return;
      const st = await pywebview.api.get_init_state();
      if (!st) return;

      // методы (обычно один — "dashboard")
      const methods = Array.isArray(st.buff_methods) ? st.buff_methods : [];
      // режимы (profile/mage/fighter/archer и т.п.)
      const modes   = Array.isArray(st.buff_modes)   ? st.buff_modes   : [];
      const current = st.buff_current || "";

      // Заполнить селекты
      fillSelect($("#buffMethod"), methods, methods[0] || "dashboard"); // по умолчанию dashboard, если есть
      fillSelect($("#buffMode"),   modes,   current);
    } catch (_) {
      // молча
    }
  }

  // Публичный API модуля (для апдейтов от Python)
  window.UIBuff = {
    init() { wire(); loadInitStateAndFill(); },
    updateMethods(methods, current) { fillSelect($("#buffMethod"), methods, current); },
    updateModes(modes, current)     { fillSelect($("#buffMode"),   modes,   current); }
  };

  // Совместимость: то, что вызывает Python
  window.ReviveUI = window.ReviveUI || {};
  window.ReviveUI.onBuffMethods = function(methods, current) {
    window.UIBuff.updateMethods(methods, current);
  };
  window.ReviveUI.onBuffModes = function(modes, current) {
    window.UIBuff.updateModes(modes, current);
  };

  // Инициализация: когда pywebview готов — заполняем из get_init_state
  function boot() {
    wire();
    loadInitStateAndFill();
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
