// app/webui/js/pooldump.ui.js
// Пул-дамп: попап + Ctrl+P с автоподключением стилей
(function () {
  const $ = (sel) => document.querySelector(sel);

  function ensureStyles() {
    if (document.getElementById("pooldump-styles")) return;
    const css = `
      #poolDumpDlg.modal-backdrop{
        position: fixed; inset: 0; background: rgba(0,0,0,.45);
        display: block; z-index: 99999;
      }
      #poolDumpDlg .modal{
        position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
        width: 900px; max-width: 95vw; height: 80vh; max-height: 90vh;
        background:#1a1a1a; color:#ddd; border-radius: 12px;
        box-shadow: 0 20px 60px rgba(0,0,0,.5); display:flex; flex-direction:column;
      }
      #poolDumpDlg .modal-hdr, #poolDumpDlg .modal-ftr{
        padding: 10px 14px; border-bottom: 1px solid #333; display:flex; align-items:center; gap:.5rem;
      }
      #poolDumpDlg .modal-ftr{ border-bottom: 0; border-top: 1px solid #333; justify-content: flex-end; }
      #poolDumpDlg .modal-body{ padding: 0; flex:1; overflow:auto; background:#0e0e0e; }
      #poolDumpDlg pre{
        margin:0; padding:12px; font-size:12px; line-height:1.35; white-space:pre; tab-size:2;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      }
      #poolDumpStatus{ color:#9aa0a6; font-size:12px; margin-left:auto; }
      #poolDumpDlg .btn{
        background:#2b2b2b; border:1px solid #3a3a3a; color:#eee; padding:6px 10px; border-radius:8px; cursor:pointer;
      }
      #poolDumpDlg .btn:hover{ background:#363636; }
    `;
    const s = document.createElement("style");
    s.id = "pooldump-styles";
    s.textContent = css;
    document.head.appendChild(s);
  }

  function ensurePopup() {
    let dlg = $("#poolDumpDlg");
    if (dlg) return dlg;

    ensureStyles();

    dlg = document.createElement("div");
    dlg.id = "poolDumpDlg";
    dlg.className = "modal-backdrop";
    dlg.innerHTML = `
      <div class="modal" role="dialog" aria-label="Dump pool">
        <div class="modal-hdr">
          <strong>Dump pool (state)</strong>
          <span id="poolDumpStatus"></span>
        </div>
        <div class="modal-body">
          <pre id="poolDumpPre">загрузка…</pre>
        </div>
        <div class="modal-ftr">
          <button id="poolDumpCopy" class="btn">Копировать</button>
          <button id="poolDumpRefresh" class="btn">Обновить (Ctrl+P)</button>
          <button id="poolDumpClose" class="btn">Закрыть</button>
        </div>
      </div>
    `;
    document.body.appendChild(dlg);

    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.remove(); });
    $("#poolDumpClose").onclick = () => dlg.remove();
    $("#poolDumpRefresh").onclick = () => refreshDump();
    $("#poolDumpCopy").onclick = async () => {
      try {
        const txt = $("#poolDumpPre")?.textContent || "";
        await navigator.clipboard.writeText(txt);
        setStatus("Скопировано");
      } catch { setStatus("Не удалось скопировать"); }
    };

    return dlg;
  }

  function setStatus(text) {
    const el = document.getElementById("poolDumpStatus");
    if (el) el.textContent = text || "";
  }

  async function refreshDump() {
    const pre = document.getElementById("poolDumpPre");
    if (!pre) return;
    try {
      setStatus("Загрузка…");
      if (!window.pywebview?.api?.pool_dump) {
        pre.textContent = "pywebview.api.pool_dump недоступен";
        setStatus("Нет API");
        return;
      }
      const res = await pywebview.api.pool_dump();
      if (!res || res.ok === false) {
        pre.textContent = `ERROR: ${res && res.error ? res.error : "нет данных"}`;
        setStatus("Ошибка");
        return;
      }
      const json = res.state ?? res;
      pre.textContent = JSON.stringify(json, null, 2);
      setStatus("Обновлено");
    } catch (e) {
      pre.textContent = `ERROR: ${e}`;
      setStatus("Ошибка");
    }
  }

  function openOrRefresh() {
    ensurePopup();
    refreshDump();
  }

  function wireButton() {
    const btn = document.getElementById("btnDumpPool");
    if (btn && !btn._pooldump_wired) {
      btn._pooldump_wired = true;
      btn.addEventListener("click", openOrRefresh);
    }
  }

  const _btnPoll = setInterval(() => {
    if (document.getElementById("btnDumpPool")) {
      wireButton();
      clearInterval(_btnPoll);
    }
  }, 300);

  function wireHotkey() {
    document.addEventListener("keydown", (e) => {
      const key = (e.key || "").toLowerCase();
      if ((e.ctrlKey || e.metaKey) && key === "p") {
        e.preventDefault();
        e.stopPropagation();
        openOrRefresh(); // если попап открыт — просто обновит
      }
    }, true);
  }

  function boot() {
    wireButton();
    wireHotkey();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
