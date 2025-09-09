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
  // делаем setStatus доступным модулям
  window.setStatus = (sel, text, ok) => {
    const el = $(sel); if (!el) return;
    el.textContent = text || "";
    el.classList.remove("ok", "err", "warn", "gray");
    if (ok === true) el.classList.add("ok");
    else if (ok === false) el.classList.add("err");
    else el.classList.add("gray");
  };
  const setStatus = window.setStatus;

  // public sink для Python
  // Общий «синк» для статусов/данных. Пусть модули дергают его по необходимости.
  window.ReviveUI = {
    onStatus: ({ scope, text, ok }) => {
      const id = {
        driver:  "#status-driver",
        window:  "#status-window",
        watcher: "#status-watcher",
        update:  "#status-update",
        buff:    "#status-buff",
        macros:  "#status-macros",
        tp:      "#status-tp",
        postrow: "#status-postrow",
        respawn: "#status-respawn"
      }[scope] || "#status-driver";
      setStatus(id, text, ok);
    },
    onRows: (rows) => {
      const sel = document.querySelector("#rows");
      if (!sel) return;
      sel.innerHTML = "";
      sel.appendChild(create("option", { value: "" }, "—"));
      rows.forEach(([rid, title]) => sel.appendChild(create("option", { value: rid }, title)));
    },
    onRowSelected: (rid) => {
      const sel = document.querySelector("#rows");
      if (sel) sel.value = rid || "";
    },
    onBuffMethods: (methods, current) => {
      // просто пробрасываем в BUFF-модуль
      if (window.UIBuff && typeof window.UIBuff.updateMethods === "function") {
        window.UIBuff.updateMethods(methods || [], current || "");
      }
    }
  };

  async function init() {
    const init = await pywebview.api.get_init_state();

    const r = init.respawn || {};
    const chkRespawn = document.querySelector("#chkRespawn");
    const chkWait    = document.querySelector("#chkRespawnWait");
    const sec        = document.querySelector("#respawnWaitSec");

    if (chkRespawn) chkRespawn.checked = !!r.enabled;
    if (chkWait)    chkWait.checked    = !!r.wait_enabled;
    if (sec)        sec.value          = (typeof r.wait_seconds === "number" ? r.wait_seconds : 120);

    $("#ver").textContent = `Версия: ${init.version}`;
    $("#lang").value = init.language;

    const serverSel = $("#server");
    serverSel.innerHTML = "";
    (init.servers || []).forEach(s => serverSel.appendChild(create("option", { value: s }, s)));
    serverSel.value = init.server;

    const tpMethodSel = $("#tpMethod");
    tpMethodSel.innerHTML = "";
    (init.tp_methods || []).forEach(m => tpMethodSel.appendChild(create("option", { value: m }, m)));
    tpMethodSel.value = (init.tp_methods && init.tp_methods[0]) || "dashboard";

    if (init.driver_status) setStatus("#status-driver", init.driver_status.text, init.driver_status.ok);
    setStatus("#status-watcher", init.monitoring ? "Мониторинг: вкл" : "Мониторинг: выкл", init.monitoring ? true : null);
    $("#chkMonitor").checked = !!init.monitoring;

    // account preload
    try {
      const acc = await pywebview.api.account_get();
      $("#acc-login").value = acc.login || "";
      $("#acc-pass").value = acc.password || "";
      $("#acc-pin").value = acc.pin || "";
    } catch (_) {}

    // Инициализация вынесенных модулей (порядок важен минимально)
    if (window.UIBuff)    window.UIBuff.init();
    if (window.UIMacros)  window.UIMacros.init();
    if (window.UIRespawn) window.UIRespawn.init();
    if (window.UIState)   window.UIState.init();
    if (window.UITP)      {
      window.UITP.init();
      await window.UITP.refreshTPCats();
    }
    if (window.UIStatePoller) window.UIStatePoller.start(); // hp/cp + watcher статус

    // теперь безопасно пробросить методы бафа — модуль уже инициализирован
    window.ReviveUI.onBuffMethods(init.buff_methods || [], init.buff_current || "");

    // handlers
    $("#lang").addEventListener("change", async e => {
      await pywebview.api.set_language(e.target.value);
      if (window.UITP) await window.UITP.refreshTPCats();
    });

    serverSel.addEventListener("change", async e => {
      await pywebview.api.set_server(e.target.value);
      if (window.UITP) await window.UITP.refreshTPCats();
    });

    $("#btnFind").addEventListener("click", async () => {
      const res = await pywebview.api.find_window();
      if (res.found) {
        console.log(`Окно найдено: ${res.title}, Размеры: ${res.info.width}x${res.info.height}`);
        setStatus("#status-window", `Окно найдено: ${res.title} (${res.info.width}x${res.info.height})`, true);
      } else {
        setStatus("#status-window", "Окно не найдено", false);
      }
    });

    $("#btnTest").addEventListener("click", async () => { await pywebview.api.test_connect(); });

    $("#btnUpdate").addEventListener("click", async () => {
      const r = await pywebview.api.run_update_check();
      if (r && r.update) setStatus("#status-update", `Доступно обновление: ${r.remote}`, null);
      else if (r && r.error) setStatus("#status-update", `Сбой проверки: ${r.error}`, false);
      else setStatus("#status-update", `Последняя версия: ${r.local}`, true);
    });

    document.getElementById("btnDumpPool")?.addEventListener("click", async ()=>{
      try {
        const d = await pywebview.api.pool_dump();
        const out = document.getElementById("poolOut");
        if (out) out.textContent = JSON.stringify(d.state || d, null, 2);
        else alert(JSON.stringify(d.state || d, null, 2));
      } catch (e) { console.error(e); }
    });

    $("#btnAccSave").addEventListener("click", async () => {
      await pywebview.api.account_save({
        login: $("#acc-login").value,
        password: $("#acc-pass").value,
        pin: $("#acc-pin").value
      });
    });
  }

  // --- ждать готовности pywebview ---
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
  document.addEventListener("DOMContentLoaded", boot);
})();
