// app/webui/js/state.poller.js
// кнопка «Мониторинг»: если выкл — HP/CP не показываем
(function () {
  const $ = (sel) => document.querySelector(sel);

  let timer = null;

  async function tick() {
    try {
      let running = true;
      if (pywebview.api.watcher_is_running) {
        running = !!(await pywebview.api.watcher_is_running());
        window.setStatus("#status-watcher", running ? "Мониторинг: вкл" : "Мониторинг: выкл", running ? true : null);
        const chk = $("#chkMonitor");
        if (chk) chk.checked = !!running;
      }

      const hpEl = $("#hp"), cpEl = $("#cp");
      if (hpEl && cpEl) {
        if (!running) {
          hpEl.textContent = "-- %";
          cpEl.textContent = "-- %";
        } else {
          const st = await pywebview.api.get_state_snapshot();
          if (st && typeof st.hp === "number") {
            hpEl.textContent = `${st.hp} %`;
            cpEl.textContent = `100 %`;
            hpEl.style.color = st.hp > 50 ? "#28a745" : (st.hp > 15 ? "#d39e00" : "#e55353");
          } else {
            hpEl.textContent = "-- %";
            cpEl.textContent = "-- %";
          }
        }
      }
    } catch (_) {}
    timer = setTimeout(tick, 2000);
  }

  window.UIStatePoller = {
    start() {
      if (timer) clearTimeout(timer);
      tick();
    },
    stop() {
      if (timer) clearTimeout(timer);
      timer = null;
    }
  };
})();
