(function () {
  const $ = (sel) => document.querySelector(sel);

  function wire() {
    const chk = $("#chkBuff");
    if (chk) chk.addEventListener("change", e => { try { pywebview.api.buff_set_enabled(!!e.target.checked); } catch(_){} });

    const mode = $("#buffMode");
    if (mode) mode.addEventListener("change", e => { try { pywebview.api.buff_set_mode(e.target.value); } catch(_){} });

    const method = $("#buffMethod");
    if (method) method.addEventListener("change", e => { try { pywebview.api.buff_set_method(e.target.value); } catch(_){} });

    const once = $("#btnBuffOnce");
    if (once) once.addEventListener("click", async () => { try { await pywebview.api.buff_run_once(); } catch(_){} });
  }

  window.UIBuff = {
    init() { wire(); },
    updateMethods(methods, current) {
      const m = document.querySelector("#buffMethod");
      if (!m) return;
      m.innerHTML = "";
      if (!methods || !methods.length) {
        m.appendChild(new Option("—", ""));
        m.disabled = true;
      } else {
        methods.forEach(x => m.appendChild(new Option(x, x)));
        m.value = current || methods[0];
        m.disabled = false;
      }
    }
  };
})();
