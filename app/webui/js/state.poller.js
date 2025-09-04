(function () {
  const $ = (sel) => document.querySelector(sel);

  let timer = null;

  async function tick() {
    try {
      const st = await pywebview.api.get_state_snapshot();
      const hp = $("#hp"), cp = $("#cp");
      if (!hp || !cp) return;

      if (st.hp == null) { hp.textContent = "-- %"; cp.textContent = "-- %"; }
      else {
        hp.textContent = `${st.hp} %`;
        cp.textContent = `100 %`;
        hp.style.color = st.hp > 50 ? "#28a745" : (st.hp > 15 ? "#d39e00" : "#e55353");
      }

      if (pywebview.api.watcher_is_running) {
        const running = await pywebview.api.watcher_is_running();
        window.setStatus("#status-watcher", running ? "Мониторинг: вкл" : "Мониторинг: выкл", running ? true : null);
        const chk = $("#chkMonitor");
        if (chk) chk.checked = !!running;
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
