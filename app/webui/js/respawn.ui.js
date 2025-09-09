// app/webui/js/respawn.ui.js
(function () {
  const $ = (sel) => document.querySelector(sel);

  async function initValuesFromInitState() {
    try {
      const init = await pywebview.api.get_init_state();
      const r = (init && init.respawn) || {};
      const chkRespawn = $("#chkRespawn");
      const chkWait = $("#chkRespawnWait");
      const sec = $("#respawnWaitSec");

      if (chkRespawn) chkRespawn.checked = !!r.enabled;
      if (chkWait) chkWait.checked = !!r.wait_enabled;
      if (sec) sec.value = (typeof r.wait_seconds === "number" ? r.wait_seconds : 120);
    } catch (_) {}
  }

  function wireRespawn() {
    const chkRespawn = $("#chkRespawn");
    if (chkRespawn) {
      chkRespawn.addEventListener("change", e => {
        try { pywebview.api.respawn_set_enabled(!!e.target.checked); } catch (_) {}
      });
    }

    const chkWait = $("#chkRespawnWait");
    if (chkWait) {
      chkWait.addEventListener("change", e => {
        try { pywebview.api.respawn_set_wait_enabled(!!e.target.checked); } catch (_) {}
      });
    }

    const sec = $("#respawnWaitSec");
    if (sec) {
      sec.addEventListener("change", e => {
        const v = parseInt(e.target.value || "0", 10);
        try { pywebview.api.respawn_set_wait_seconds(isFinite(v) ? v : 0); } catch (_) {}
      });
    }
  }

  window.UIRespawn = {
    init() {
      wireRespawn();
      initValuesFromInitState();
    }
  };
})();
