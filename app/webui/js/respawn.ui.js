(function () {
  const $ = (sel) => document.querySelector(sel);

  function wireRespawn() {
    const chkRespawn = $("#chkRespawn");
    if (chkRespawn) {
      chkRespawn.addEventListener("change", e => {
        try { pywebview.api.respawn_set_enabled(!!e.target.checked); } catch (_) {}
      });
    }
  }

  function wireMonitor() {
    const chkMonitor = $("#chkMonitor");
    if (chkMonitor) {
      chkMonitor.addEventListener("change", e => {
        try {
          pywebview.api.respawn_set_monitoring(!!e.target.checked);
          window.setStatus("#status-watcher", e.target.checked ? "Мониторинг: вкл" : "Мониторинг: выкл", e.target.checked ? true : null);
          setTimeout(async () => {
            try {
              if (pywebview.api.watcher_is_running) {
                const running = await pywebview.api.watcher_is_running();
                window.setStatus("#status-watcher", running ? "Мониторинг: вкл" : "Мониторинг: выкл", running ? true : null);
                $("#chkMonitor").checked = !!running;
              }
            } catch (_) {}
          }, 200);
        } catch (_) {}
      });
    }
  }

  window.UIRespawn = {
    init() {
      wireRespawn();
      wireMonitor();
    }
  };
})();
