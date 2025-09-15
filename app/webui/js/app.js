// app/webui/js/app.js
(function () {
  const $ = (sel) => document.querySelector(sel);
  const create = (tag, attrs = {}, text = "") => {
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "class") el.className = v; else el.setAttribute(k, v);
    });
    if (text) el.textContent = text;
    return el;
  };

  // статусы
  window.setStatus = (sel, text, ok) => {
    const el = $(sel); if (!el) return;
    el.textContent = text || "";
    el.classList.remove("ok", "err", "warn", "gray");
    if (ok === true) el.classList.add("ok");
    else if (ok === false) el.classList.add("err");
    else el.classList.add("gray");
  };

  // UI-шина
  window.ReviveUI = {
    onStatus: ({ scope, text, ok }) => {
      const id = {
        driver:  "#status-driver",
        window:  "#status-window",
        watcher: "#status-watcher",
        update:  "#status-update",
        buff:    "#status-buff",
        macros:  "#status-macros",
        teleport:      "#status-teleport",
        postrow: "#status-postrow",
        respawn: "#status-respawn"
      }[scope] || "#status-driver";
      setStatus(id, text, ok);
    },
    onRows: (rows) => {
      const sel = $("#rows");
      if (!sel) return;
      sel.innerHTML = "";
      sel.appendChild(create("option", { value: "" }, "—"));
      (rows || []).forEach(([rid, title]) => sel.appendChild(create("option", { value: rid }, title)));
    },
    onRowSelected: (rid) => {
      const sel = $("#rows");
      if (sel) sel.value = rid || "";
    },
    onBuffMethods: (methods, current) => {
      if (window.UIBuff && typeof window.UIBuff.updateMethods === "function") {
        window.UIBuff.updateMethods(methods || [], current || "");
      }
    }
  };

  function applySectionsVisibility(sections) {
    const ids = ["system","stream","respawn","buff","macros","teleport","autofarm"];
    ids.forEach(k => {
      const el = document.querySelector(`[data-section="${k}"]`);
      if (!el) return;
      const on = (sections && Object.prototype.hasOwnProperty.call(sections, k)) ? !!sections[k] : true;
      el.style.display = on ? "" : "none";
    });
  }

  function fillSelect(el, values, current) {
    if (!el) return;
    el.innerHTML = "";
    (values || []).forEach(v => el.appendChild(new Option(String(v), String(v))));
    if (current != null && current !== "" && (values || []).includes(current)) {
      el.value = current;
    } else if (values && values.length) {
      el.value = values[0];
    }
  }

  async function refreshInitAndUI() {
    const init = await pywebview.api.get_init_state();

    // версии/языки
    $("#ver").textContent = `Версия: ${init.version}`;

    fillSelect($("#appLang"), ["ru","en"], init.app_language);
    fillSelect($("#l2Lang"), init.system_languages || [], init.language);
    fillSelect($("#server"), init.servers || [], init.server);

    // секции
    applySectionsVisibility(init.sections || {});

    // методы
    fillSelect($("#teleportMethod"), init.teleport_methods || [], (init.teleport_methods && init.teleport_methods[0]) || "");
    window.ReviveUI.onBuffMethods(init.buff_methods || [], init.buff_current || "");

    // мониторинг/драйвер
    if (init.driver_status) window.setStatus("#status-driver", init.driver_status.text, init.driver_status.ok);
    window.setStatus("#status-watcher", init.monitoring ? "Мониторинг: вкл" : "Мониторинг: выкл", init.monitoring ? true : null);

    // респавн
    const r = init.respawn || {};
    const chkRespawn = $("#chkRespawn");
    const chkWait    = $("#chkRespawnWait");
    const sec        = $("#respawnWaitSec");
    if (chkRespawn) chkRespawn.checked = !!r.enabled;
    if (chkWait)    chkWait.checked    = !!r.wait_enabled;
    if (sec)        sec.value          = (typeof r.wait_seconds === "number" ? r.wait_seconds : 120);

    // аккаунт
    try {
      const acc = await pywebview.api.account_get();
      $("#acc-login").value = acc.login || "";
      $("#acc-pass").value = acc.password || "";
      $("#acc-pin").value = acc.pin || "";
    } catch (_){}
  }

  function wireHandlers() {
    $("#appLang")?.addEventListener("change", async (e) => {
      try { await pywebview.api.set_program_language(e.target.value); } catch(_){}
    });

    $("#l2Lang")?.addEventListener("change", async (e) => {
      try { await pywebview.api.set_language(e.target.value); } catch(_){}
    });

    $("#server")?.addEventListener("change", async (e) => {
      try {
        await pywebview.api.set_server(e.target.value);
        // после смены сервера заново читаем init и перерисовываем всё зависящее
        await refreshInitAndUI();
      } catch(_){}
    });

    $("#btnFind")?.addEventListener("click", async () => {
      const res = await pywebview.api.find_window();
      if (res.found) {
        console.log(`Окно найдено: ${res.title}, Размеры: ${res.info.width}x${res.info.height}`);
        window.setStatus("#status-window", `Окно найдено: ${res.title} (${res.info.width}x${res.info.height})`, true);
      } else {
        window.setStatus("#status-window", "Окно не найдено", false);
      }
    });

    $("#btnTest")?.addEventListener("click", async () => { await pywebview.api.test_connect(); });

    $("#btnUpdate")?.addEventListener("click", async () => {
      const r = await pywebview.api.run_update_check();
      if (r && r.update) window.setStatus("#status-update", `Доступно обновление: ${r.remote}`, null);
      else if (r && r.error) window.setStatus("#status-update", `Сбой проверки: ${r.error}`, false);
      else window.setStatus("#status-update", `Последняя версия: ${r.local}`, true);
    });

    $("#btnAccSave")?.addEventListener("click", async () => {
      await pywebview.api.account_save({
        login: $("#acc-login").value,
        password: $("#acc-pass").value,
        pin: $("#acc-pin").value
      });
    });
  }

  async function init() {
    await refreshInitAndUI();

    // Инициализация вынесенных модулей
    if (window.UIBuff)    window.UIBuff.init();
    if (window.UIMacros)  window.UIMacros.init();
    if (window.UIRespawn) window.UIRespawn.init?.();
    if (window.UIState)   window.UIState.init?.();
    if (window.UITeleport)      {
      window.UITeleport.init();
      await window.UITeleport.refreshTeleportCats?.();
    }
    if (window.UIStatePoller) window.UIStatePoller.start?.(); // hp/cp + watcher

    wireHandlers();
  }

  function boot() {
    if (window.pywebview && window.pywebview.api) { init(); return; }
    const onReady = () => { document.removeEventListener('pywebviewready', onReady); init(); };
    document.addEventListener('pywebviewready', onReady);
    let tries = 0;
    const poll = setInterval(() => {
      if (window.pywebview && window.pywebview.api) { clearInterval(poll); init(); }
      else if (++tries > 100) { clearInterval(poll); }
    }, 50);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('btnExit');
    if (btn) {
      btn.addEventListener('click', async () => {
        try { await pywebview.api.exit_app(); } catch (e) {}
      });
    }
  });

  document.addEventListener("DOMContentLoaded", boot);
})();
