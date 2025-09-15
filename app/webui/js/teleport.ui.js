// app/webui/js/teleport.ui.js
(function () {
  const $ = (sel) => document.querySelector(sel);

  function fillSelect(el, values, current) {
    if (!el) return;
    el.innerHTML = "";
    const list = Array.isArray(values) ? values : [];
    if (!list.length) {
      el.appendChild(new Option("—", ""));
      el.disabled = true;
      el.value = "";
      return;
    }
    // плейсхолдер + опции
    el.appendChild(new Option("—", ""));
    for (const v of list) el.appendChild(new Option(String(v), String(v)));
    const cur = (current != null && current !== "" && list.includes(current)) ? current : "";
    el.value = cur; // если пусто — остаётся placeholder
    el.disabled = false;
  }

  // ---------- Стабилизация: обёртки и поиск ⚠️ ----------
  function stabWrapEl() {
    // основной wrap, затем типовые контейнеры формы, затем родитель чекбокса
    return document.getElementById("teleportStabWrap")
      || $("#teleportStab")?.closest(".form-check, .form-row, .form-group, .row, .group")
      || $("#teleportStab")?.parentElement
      || $("#teleportStab");
  }

  function stabLabelEl() {
    return document.querySelector('label[for="teleportStab"]')
      || $("#teleportStab")?.closest(".form-check, .form-row, .form-group")?.querySelector("label");
  }

  // максимально терпеливый поиск «⚠️» рядом с чекбоксом
  function findStabWarnEl() {
    const chk = $("#teleportStab");
    const wrap = stabWrapEl();

    // 1) прямые селекторы
    let warn = document.getElementById("teleportStabWarn")
      || wrap?.querySelector?.(".tp-stab-warn, [data-role='stab-warn'], .stab-warn")
      || chk?.closest?.(".form-check, .form-row, .form-group, .row, .group")
             ?.querySelector?.(".tp-stab-warn, [data-role='stab-warn'], .stab-warn");
    if (warn) return warn;

    // 2) ближайшие соседи вокруг wrap / родителя чекбокса
    const neighborCandidates = [];
    if (wrap) {
      neighborCandidates.push(wrap.previousElementSibling, wrap.nextElementSibling);
      if (wrap.parentElement) {
        neighborCandidates.push(wrap.parentElement.previousElementSibling, wrap.parentElement.nextElementSibling);
      }
    }
    const parentOfChk = chk?.parentElement;
    if (parentOfChk) {
      neighborCandidates.push(parentOfChk.previousElementSibling, parentOfChk.nextElementSibling);
    }
    for (const el of neighborCandidates) {
      if (el && typeof el.textContent === "string" && el.textContent.includes("⚠️")) return el;
    }

    // 3) последний шанс: поиск элемента с «⚠️» среди соседних детей общего родителя
    const scope = wrap?.parentElement || chk?.closest(".form-row, .form-group, .row, .group") || document.body;
    if (scope) {
      const kids = Array.from(scope.children || []);
      for (const el of kids) {
        if (el === wrap) continue;
        if (typeof el.textContent === "string" && el.textContent.includes("⚠️")) return el;
      }
    }
    return null;
  }

  function showStabUI(show) {
    const wrap = stabWrapEl();
    const chk  = $("#teleportStab");
    const lbl  = stabLabelEl();
    const warn = findStabWarnEl();

    // если есть общий wrap — прячем его; иначе прячем составляющие по отдельности
    if (wrap) wrap.style.display = show ? "" : "none";
    if (!wrap) {
      if (chk) chk.style.display = show ? "" : "none";
      if (lbl) lbl.style.display = show ? "" : "none";
    }
    if (warn) warn.style.display = show ? "" : "none";
  }

  async function updateStabVisibility() {
    const stab = $("#teleportStab");
    const loc = $("#tploc")?.value || "";

    if (!loc) {
      showStabUI(false);
      if (stab) {
        stab.checked = false;
        try { pywebview.api.teleport_set_stabilize?.(false); } catch (_){}
      }
      return;
    }

    try {
      const hasOpt = await pywebview.api.teleport_has_optional_stabilize?.(loc);
      if (hasOpt) {
        showStabUI(true);
        if (stab && !stab.checked) {
          stab.checked = true;
          try { pywebview.api.teleport_set_stabilize?.(true); } catch (_){}
        } else {
          try { pywebview.api.teleport_set_stabilize?.(true); } catch (_){}
        }
      } else {
        showStabUI(false);
        if (stab) stab.checked = false;
        try { pywebview.api.teleport_set_stabilize?.(false); } catch (_){}
      }
    } catch (_) {
      showStabUI(false);
      if (stab) stab.checked = false;
      try { pywebview.api.teleport_set_stabilize?.(false); } catch (_){}
    }
  }

  // ---------- Инициализация формы ----------
  async function loadInit() {
    if (!window.pywebview || !pywebview.api?.get_init_state) return;

    const st  = await pywebview.api.get_init_state();
    const cfg = await pywebview.api.teleport_get_config?.();

    // методы — выбираем текущий из пула
    const methods = st?.teleport_methods || [];
    fillSelect($("#teleportMethod"), methods, cfg?.method || "");

    // включатель и состояние стабилизации (видимость решит updateStabVisibility)
    try {
      if (cfg) {
        const chk = $("#chkTeleport"); if (chk) chk.checked = !!cfg.enabled;
        const stab = $("#teleportStab"); if (stab) stab.checked = !!cfg.stabilize;
      }
    } catch (_) {}

    // пока локация не выбрана — всё скрыто
    showStabUI(false);
  }

  async function refreshTeleportCats() {
    try {
      const cfg  = await pywebview.api.teleport_get_config?.();
      const cats = await pywebview.api.teleport_list_categories?.();
      fillSelect($("#teleportCat"), cats || [], cfg?.category || "");
      await refreshtplocs(cfg?.location || "");
    } catch (_){}
  }

  async function refreshtplocs(currentLoc) {
    try {
      const cat  = $("#teleportCat")?.value || "";
      const locs = await pywebview.api.teleport_list_locations?.(cat);
      fillSelect($("#tploc"), locs || [], currentLoc || "");
      await updateStabVisibility(); // подтянет и чекбокс, и ⚠️
    } catch (_){}
  }

  // ---------- Слушатели ----------
  function wire() {
    $("#chkTeleport")?.addEventListener("change", (e) => {
      try { pywebview.api.teleport_set_enabled?.(!!e.target.checked); } catch (_){}
    });

    $("#teleportMethod")?.addEventListener("change", (e) => {
      try { pywebview.api.teleport_set_method?.(String(e.target.value || "")); } catch (_){}
    });

    $("#teleportCat")?.addEventListener("change", async () => {
      try {
        const cat = $("#teleportCat")?.value || "";
        await pywebview.api.teleport_set_category?.(cat);
        await refreshtplocs(""); // без автоселекта локации
      } catch (_){}
    });

    $("#tploc")?.addEventListener("change", async (e) => {
      try {
        const val = String(e.target.value || "");
        await pywebview.api.teleport_set_location?.(val);
        await updateStabVisibility(); // авто-вкл/выкл + синх пула
      } catch (_){}
    });

    $("#teleportStab")?.addEventListener("change", (e) => {
      try { pywebview.api.teleport_set_stabilize?.(!!e.target.checked); } catch (_){}
    });

    $("#btnTeleportNow")?.addEventListener("click", async () => {
      try {
        const r = await pywebview.api.teleport_run_now?.();
        window.setStatus("#status-teleport", r?.ok ? "Телепорт выполняется…" : "Не удалось запустить телепорт", r?.ok || false);
      } catch (_){}
    });
  }

  // ---------- Старт ----------
  async function init() {
    wire();
    await loadInit();
    await refreshTeleportCats();
    await updateStabVisibility();
  }

  window.UITeleport = { init, refreshTeleportCats };

  if (window.pywebview && window.pywebview.api) init();
  else document.addEventListener("pywebviewready", init);
})();
