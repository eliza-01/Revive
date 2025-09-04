// app/webui/js/state.ui.js
(function () {
  const $ = (sel) => document.querySelector(sel);

  function wireMonitor() {
    const chkMonitor = $("#chkMonitor");
    if (!chkMonitor) return;

    chkMonitor.addEventListener("change", async (e) => {
      try {
        await pywebview.api.watcher_set_enabled(!!e.target.checked);
        window.setStatus("#status-watcher",
          e.target.checked ? "Мониторинг: вкл" : "Мониторинг: выкл",
          e.target.checked ? true : null
        );
        // быстрая перепроверка фактического статуса
        setTimeout(async () => {
          try {
            const running = await pywebview.api.watcher_is_running();
            window.setStatus("#status-watcher", running ? "Мониторинг: вкл" : "Мониторинг: выкл", running ? true : null);
            const chk = $("#chkMonitor"); if (chk) chk.checked = !!running;
          } catch (_) {}
        }, 200);
      } catch (_) {}
    });
  }

  window.UIState = {
    init() {
      wireMonitor();
      // стартовое состояние чекбокса и статус уже заполняются в app.js через init.monitoring / poller
    }
  };
})();
