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
  const setStatus = (sel, text, ok) => {
    const el = $(sel); if (!el) return;
    el.textContent = text || "";
    el.classList.remove("ok", "err", "warn", "gray");
    if (ok === true) el.classList.add("ok");
    else if (ok === false) el.classList.add("err");
    else el.classList.add("gray");
  };

  // public sink для Python
  window.ReviveUI = {
    onStatus: ({ scope, text, ok }) => {
      const id = {
        driver: "#status-driver",
        window: "#status-window",
        watcher: "#status-watcher",
        update: "#status-update",
        buff: "#status-buff",
        macros: "#status-macros",
        tp: "#status-tp",
        postrow: "#status-postrow"
      }[scope] || "#status-driver";
      setStatus(id, text, ok);
    },
    onRows: (rows) => {
      const sel = $("#rows");
      sel.innerHTML = "";
      sel.appendChild(create("option", { value: "" }, "—"));
      rows.forEach(([rid, title]) => sel.appendChild(create("option", { value: rid }, title)));
    },
    onRowSelected: (rid) => { $("#rows").value = rid || ""; },
    onBuffMethods: (methods, current) => {
      const m = $("#buffMethod");
      m.innerHTML = "";
      if (!methods || !methods.length) {
        m.appendChild(create("option", { value: "" }, "—"));
        m.disabled = true;
      } else {
        methods.forEach(x => m.appendChild(create("option", { value: x }, x)));
        m.value = current || methods[0];
        m.disabled = false;
      }
    }
  };

  // --- macros rows as numeric inputs (1 char, small reserve) ---
  function sanitizeKey(val) {
    const v = (val || "").replace(/[^\d]/g, "").slice(0, 2);
    return v.length ? v : "1";
  }
  function buildMacrosRow(val) {
    const inp = create("input", {
      type: "text",
      class: "key",
      inputmode: "numeric",
      pattern: "[0-9]{1,2}",
      maxlength: "2",
      value: sanitizeKey(val || "1")
    });
    inp.addEventListener("input", () => {
      inp.value = sanitizeKey(inp.value);
      pywebview.api.macros_set_sequence(readMacrosSequence());
    });
    return inp;
  }
  function readMacrosSequence() {
    return Array.from($("#macrosRows").querySelectorAll("input.key")).map(x => x.value || "1");
  }
  function ensureAtLeastOneRow() {
    const cont = $("#macrosRows");
    if (!cont.children.length) cont.appendChild(buildMacrosRow("1"));
  }

  // periodic state poll
  async function tickState() {
    try {
      const st = await pywebview.api.get_state_snapshot();
      const hp = $("#hp"), cp = $("#cp");
      if (st.hp == null) { hp.textContent = "-- %"; cp.textContent = "-- %"; }
      else {
        hp.textContent = `${st.hp} %`;
        cp.textContent = `100 %`;
        hp.style.color = st.hp > 50 ? "#28a745" : (st.hp > 15 ? "#d39e00" : "#e55353");
      }
      if (pywebview.api.watcher_is_running) {
        const running = await pywebview.api.watcher_is_running();
        setStatus("#status-watcher", running ? "Мониторинг: вкл" : "Мониторинг: выкл", running ? true : null);
        $("#chkMonitor").checked = !!running;
      }
    } catch (_) {}
    setTimeout(tickState, 2000);
  }

  async function init() {
    const init = await pywebview.api.get_init_state();

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

    window.ReviveUI.onBuffMethods(init.buff_methods || [], init.buff_current || "");

    if (init.driver_status) setStatus("#status-driver", init.driver_status.text, init.driver_status.ok);
    setStatus("#status-watcher", init.monitoring ? "Мониторинг: вкл" : "Мониторинг: выкл", init.monitoring ? true : null);
    $("#chkMonitor").checked = !!init.monitoring;

    // ранние статусы
    try {
      if (pywebview.api.get_status_snapshot) {
        const snap = await pywebview.api.get_status_snapshot();
        if (snap && snap.window) setStatus("#status-window", snap.window.text, snap.window.ok);
        if (snap && snap.driver && !init.driver_status) setStatus("#status-driver", snap.driver.text, snap.driver.ok);
      }
    } catch (_) {}

    // account preload
    try {
      const acc = await pywebview.api.account_get();
      $("#acc-login").value = acc.login || "";
      $("#acc-pass").value = acc.password || "";
      $("#acc-pin").value = acc.pin || "";
    } catch (_) {}

    await refreshTPCats();

    // ensure one macros row
    ensureAtLeastOneRow();

    // handlers
    $("#lang").addEventListener("change", async e => {
      await pywebview.api.set_language(e.target.value);
      await refreshTPCats();
    });

    serverSel.addEventListener("change", async e => {
      await pywebview.api.set_server(e.target.value);
      await refreshTPCats();
    });

    $("#btnFind").addEventListener("click", async () => { await pywebview.api.find_window(); });
    $("#btnTest").addEventListener("click", async () => { await pywebview.api.test_connect(); });

    $("#btnUpdate").addEventListener("click", async () => {
      const r = await pywebview.api.run_update_check();
      if (r && r.update) setStatus("#status-update", `Доступно обновление: ${r.remote}`, null);
      else if (r && r.error) setStatus("#status-update", `Сбой проверки: ${r.error}`, false);
      else setStatus("#status-update", `Последняя версия: ${r.local}`, true);
    });

    $("#btnAccSave").addEventListener("click", async () => {
      await pywebview.api.account_save({
        login: $("#acc-login").value,
        password: $("#acc-pass").value,
        pin: $("#acc-pin").value
      });
    });

    // respawn
    $("#chkMonitor").addEventListener("change", e => {
      pywebview.api.respawn_set_monitoring(e.target.checked);
      setStatus("#status-watcher", e.target.checked ? "Мониторинг: вкл" : "Мониторинг: выкл", e.target.checked ? true : null);
      setTimeout(async () => {
        try {
          if (pywebview.api.watcher_is_running) {
            const running = await pywebview.api.watcher_is_running();
            setStatus("#status-watcher", running ? "Мониторинг: вкл" : "Мониторинг: выкл", running ? true : null);
            $("#chkMonitor").checked = !!running;
          }
        } catch (_) {}
      }, 200);
    });
    $("#chkRespawn").addEventListener("change", e => pywebview.api.respawn_set_enabled(e.target.checked));

    // buff
    $("#chkBuff").addEventListener("change", e => pywebview.api.buff_set_enabled(e.target.checked));
    $("#buffMode").addEventListener("change", e => pywebview.api.buff_set_mode(e.target.value));
    $("#buffMethod").addEventListener("change", e => pywebview.api.buff_set_method(e.target.value));
    $("#btnBuffOnce").addEventListener("click", async () => { await pywebview.api.buff_run_once(); });

    // macros
    $("#btnAddRow").addEventListener("click", () => {
      $("#macrosRows").appendChild(buildMacrosRow("1"));
      pywebview.api.macros_set_sequence(readMacrosSequence());
    });
    $("#btnDelRow").addEventListener("click", () => {
      const cont = $("#macrosRows");
      if (cont.children.length > 1) cont.removeChild(cont.lastElementChild);
      pywebview.api.macros_set_sequence(readMacrosSequence());
    });
    $("#chkMacros").addEventListener("change", e => pywebview.api.macros_set_enabled(e.target.checked));
    $("#chkMacrosAlways").addEventListener("change", e => pywebview.api.macros_set_run_always(e.target.checked));
    $("#macrosDelay").addEventListener("change", e => pywebview.api.macros_set_delay(parseFloat(e.target.value || "0")));
    $("#macrosDur").addEventListener("change", e => pywebview.api.macros_set_duration(parseFloat(e.target.value || "0")));
    $("#btnMacrosOnce").addEventListener("click", () => pywebview.api.macros_run_once());

    // TP
    $("#chkTP").addEventListener("change", e => pywebview.api.tp_set_enabled(e.target.checked));
    $("#tpMethod").addEventListener("change", e => pywebview.api.tp_set_method(e.target.value));
    $("#tpCat").addEventListener("change", async e => { await pywebview.api.tp_set_category(e.target.value); await refreshTPLocs(); });
    $("#tpLoc").addEventListener("change", e => pywebview.api.tp_set_location(e.target.value));
    $("#btnTPNow").addEventListener("click", () => pywebview.api.tp_teleport_now());

    $("#rows").addEventListener("change", e => pywebview.api.tp_set_selected_row_id(e.target.value || ""));
    $("#btnRowClear").addEventListener("click", () => { $("#rows").value = ""; pywebview.api.tp_set_selected_row_id(""); });

    tickState();
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

  async function refreshTPCats() {
    const cats = await pywebview.api.tp_get_categories();
    const sel = $("#tpCat");
    sel.innerHTML = "";
    sel.appendChild(create("option", { value: "" }, "— не выбрано —"));
    cats.forEach(c => sel.appendChild(create("option", { value: c.id }, c.title)));
    sel.value = "";
    await refreshTPLocs();
  }
  async function refreshTPLocs() {
    const cid = $("#tpCat").value || "";
    const locs = await pywebview.api.tp_get_locations(cid);
    const sel = $("#tpLoc");
    sel.innerHTML = "";
    sel.appendChild(create("option", { value: "" }, "— не выбрано —"));
    locs.forEach(l => sel.appendChild(create("option", { value: l.id }, l.title)));
    sel.value = "";
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
