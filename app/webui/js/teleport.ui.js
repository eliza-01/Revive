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

  async function loadInit() {
    if (!window.pywebview || !pywebview.api?.get_init_state) return;

    const st = await pywebview.api.get_init_state();
    const cfg = await pywebview.api.teleport_get_config?.();

    // методы — выбираем текущий из пула
    const methods = st?.teleport_methods || [];
    fillSelect($("#teleportMethod"), methods, cfg?.method || "");

    // включатель и стабилизация
    try {
      if (cfg) {
        const chk = $("#chkTeleport"); if (chk) chk.checked = !!cfg.enabled;
        const stab = $("#teleportStab"); if (stab) stab.checked = !!cfg.stabilize;
      }
    } catch (_) {}
  }

  async function refreshTeleportCats() {
    try {
      const cfg = await pywebview.api.teleport_get_config?.();
      const cats = await pywebview.api.teleport_list_categories?.();
      fillSelect($("#teleportCat"), cats || [], cfg?.category || "");
      await refreshtplocs(cfg?.location || "");
    } catch (_) {}
  }

  async function refreshtplocs(currentLoc) {
    try {
      const cat = $("#teleportCat")?.value || "";
      const locs = await pywebview.api.teleport_list_locations?.(cat);
      fillSelect($("#tploc"), locs || [], currentLoc || "");
    } catch (_) {}
  }

  function wire() {
    // включатель
    $("#chkTeleport")?.addEventListener("change", (e) => {
      try { pywebview.api.teleport_set_enabled?.(!!e.target.checked); } catch (_){}
    });

    // метод
    $("#teleportMethod")?.addEventListener("change", (e) => {
      try { pywebview.api.teleport_set_method?.(String(e.target.value || "")); } catch (_){}
    });

    // категория
    $("#teleportCat")?.addEventListener("change", async () => {
      try {
        const cat = $("#teleportCat")?.value || "";
        await pywebview.api.teleport_set_category?.(cat);
        await refreshtplocs(""); // без автоселекта локации
      } catch (_){}
    });

    // локация
    $("#tploc")?.addEventListener("change", (e) => {
      try { pywebview.api.teleport_set_location?.(String(e.target.value || "")); } catch (_){}
    });

    // стабилизация прибытия
    $("#teleportStab")?.addEventListener("change", (e) => {
      try { pywebview.api.teleport_set_stabilize?.(!!e.target.checked); } catch (_){}
    });

    // ТП сейчас
    $("#btnTeleportNow")?.addEventListener("click", async () => {
      try {
        const r = await pywebview.api.teleport_run_now?.();
        window.setStatus("#status-teleport", r?.ok ? "Телепорт выполняется…" : "Не удалось запустить телепорт", r?.ok || false);
      } catch (_){}
    });
  }

  async function init() {
    wire();
    await loadInit();
    await refreshTeleportCats(); // заполнит категории/локации, но не выберет по умолчанию
  }

  window.UITeleport = { init, refreshTeleportCats };

  if (window.pywebview && window.pywebview.api) init();
  else document.addEventListener("pywebviewready", init);
})();
