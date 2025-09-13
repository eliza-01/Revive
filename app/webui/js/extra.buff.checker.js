// app/webui/js/extra.buff.checker.js
(function () {
  const $ = (sel) => document.querySelector(sel);

  // --- Иконки (ключи должны совпадать с backend: BUFFS/DANCES/SONGS) ---
  const ICONS = {
    Buffs: [
      { key: "mental_shield", label: "Mental Shield", src: "assets/buff-icons/buffs/mental_shield.png" },
    ],
    Dances: [
      { key: "dance_of_concentration", label: "Dance of Concentration", src: "assets/buff-icons/dances/dance_of_concentration.png" },
      { key: "dance_of_siren",         label: "Dance of Siren",         src: "assets/buff-icons/dances/dance_of_siren.png" },
    ],
    Songs: [
      { key: "song_of_earth",    label: "Song of Earth",    src: "assets/buff-icons/songs/song_of_earth.png" },
      { key: "song_of_vitality", label: "Song of Vitality", src: "assets/buff-icons/songs/song_of_vitality.png" },
    ],
  };

  // --- Рендер модалки ---
  function ensureModal() {
    if ($("#buffCheckerModal")) return $("#buffCheckerModal");

    const wrap = document.createElement("div");
    wrap.id = "buffCheckerModal";
    wrap.innerHTML = `
      <style>
        #buffCheckerModal { position: fixed; inset:0; display:none; align-items:center; justify-content:center; z-index:9999; }
        #buffCheckerModal .backdrop { position:absolute; inset:0; background:rgba(0,0,0,0.45); }
        #buffCheckerModal .panel {
          position:relative; width: 560px; max-width: calc(100vw - 40px);
          background:#0f0f13; color:#e6e6ea; border-radius:14px; padding:14px; box-shadow:0 10px 40px rgba(0,0,0,.5);
          border:1px solid #1e1e28;
        }
        #buffCheckerModal .title { font: 700 14px/1.2 system-ui,Segoe UI,Arial; margin:0 0 10px; }
        #buffCheckerModal .tabs { display:flex; gap:8px; margin-bottom:10px; }
        #buffCheckerModal .tab {
          display:flex; align-items:center; gap:8px; padding:6px 10px; border-radius:999px; cursor:pointer;
          border:1px solid #2a2a36; background:#14141b;
        }
        #buffCheckerModal .tab.active { border-color:#2e7d32; box-shadow:0 0 0 2px rgba(46,125,50,.25) inset; }
        #buffCheckerModal .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(110px,1fr)); gap:10px; }
        #buffCheckerModal .item {
          display:flex; align-items:center; gap:8px; padding:6px; border-radius:10px; border:1px solid #20202a; background:#121218; cursor:pointer;
        }
        #buffCheckerModal .item img { width:25px; height:25px; border-radius:6px; object-fit:cover; display:block; }
        #buffCheckerModal .item .name { font: 12px/1.2 system-ui,Segoe UI,Arial; color:#cfd0d6 }
        #buffCheckerModal .item.selected { border-color:#2e7d32; box-shadow:0 0 0 2px rgba(46,125,50,.25) inset; }
        #buffCheckerModal .actions { display:flex; justify-content:flex-end; gap:8px; margin-top:12px; }
        #buffCheckerModal .btn {
          padding:7px 12px; border-radius:10px; border:1px solid #2a2a36; background:#171720; color:#e6e6ea; cursor:pointer;
        }
        #buffCheckerModal .btn.primary { border-color:#2e7d32; background:#1a2d1a; }
      </style>
      <div class="backdrop"></div>
      <div class="panel">
        <div class="title">Проверять бафы</div>
        <div class="tabs"></div>
        <div class="grid"></div>
        <div class="actions">
          <button class="btn" data-act="cancel">Отмена</button>
          <button class="btn primary" data-act="apply">Сохранить</button>
        </div>
      </div>
    `;
    document.body.appendChild(wrap);
    return wrap;
  }

  function showModal() {
    const modal = ensureModal();
    const tabsEl = modal.querySelector(".tabs");
    const gridEl = modal.querySelector(".grid");
    const backdrop = modal.querySelector(".backdrop");
    const btnApply = modal.querySelector('[data-act="apply"]');
    const btnCancel = modal.querySelector('[data-act="cancel"]');

    let activeTab = "Buffs";
    /** @type {Set<string>} */
    let selected = new Set();

    function renderTabs() {
      tabsEl.innerHTML = "";
      Object.keys(ICONS).forEach(tab => {
        const el = document.createElement("div");
        el.className = "tab" + (tab === activeTab ? " active" : "");
        el.textContent = tab;
        el.addEventListener("click", () => { activeTab = tab; renderTabs(); renderGrid(); });
        tabsEl.appendChild(el);
      });
    }

    function renderGrid() {
      gridEl.innerHTML = "";
      (ICONS[activeTab] || []).forEach(item => {
        const el = document.createElement("div");
        el.className = "item" + (selected.has(item.key) ? " selected" : "");
        el.innerHTML = `<img src="${item.src}" alt=""><div class="name">${item.label}</div>`;
        el.addEventListener("click", () => {
          if (selected.has(item.key)) selected.delete(item.key);
          else selected.add(item.key);
          el.classList.toggle("selected");
        });
        gridEl.appendChild(el);
      });
    }

    // загрузить текущее состояние из backend
    (async () => {
      try {
        const cur = await pywebview.api.buff_checker_get();
        if (Array.isArray(cur)) cur.forEach(k => selected.add(k));
      } catch (_) {}
      renderTabs(); renderGrid();
      modal.style.display = "flex";
    })();

    function close() { modal.style.display = "none"; }

    backdrop.onclick = close;
    btnCancel.onclick = close;
    btnApply.onclick = async () => {
      try { await pywebview.api.buff_checker_set(Array.from(selected)); } catch (_) {}
      close();
    };
  }

  // кнопка
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.querySelector("#btnBuffChecker");
    if (btn) btn.addEventListener("click", showModal);
  });

  // экспорт на всякий
  window.UIBuffChecker = { open: showModal };
})();
