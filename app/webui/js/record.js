// app/webui/js/record.js
(function () {
  // ----- DOM build -----
  function buildSection() {
    const grid = document.querySelector('main.container.grid');
    if (!grid || document.getElementById('sec-record')) return;

    const teleport = document.getElementById('sec-teleport');
    const sec = document.createElement('section');
    sec.className = 'card';
    sec.id = 'sec-record';
    sec.dataset.section = 'record';
    sec.innerHTML = `
      <h4>Запись</h4>

      <div class="row compact wrap">
        <label class="switch">
          <input type="checkbox" id="chkRecord">
          <span class="slider"></span>
          <span class="slabel">Включить</span>
        </label>

        <label class="ml mr">Запись:</label>
        <select id="recSelect" class="md"></select>
        <button id="recPlay" class="ml">Запустить сейчас</button>
        <button id="recCreate" class="ml">Создать запись</button>
      </div>

      <div class="row compact">
        <span id="status-record" class="status gray">—</span>
      </div>
    `;
    if (teleport && teleport.nextSibling) grid.insertBefore(sec, teleport.nextSibling);
    else grid.appendChild(sec);
  }
  buildSection();

  // ----- Elements -----
  const $ = (id) => document.getElementById(id);
  const sel = () => $('recSelect');
  const btnPlay = () => $('recPlay');
  const btnCreate = () => $('recCreate');
  const chk = () => $('chkRecord');
  const stEl = () => $('status-record');

  // ----- API ready helper -----
  function whenAPIReady(fn) {
    if (window.pywebview && pywebview.api && pywebview.api.record_list) return void fn();
    const onReady = () => { document.removeEventListener('pywebviewready', onReady); fn(); };
    document.addEventListener('pywebviewready', onReady);
    // страховочный поллинг (на случай, если событие не прилетит)
    let tries = 0;
    const t = setInterval(() => {
      if (window.pywebview && pywebview.api && pywebview.api.record_list) { clearInterval(t); fn(); }
      else if (++tries > 200) { clearInterval(t); } // ~10 секунд
    }, 50);
  }

  // ----- Helpers -----
  async function api(name, ...args) {
    if (!window.pywebview || !pywebview.api || !pywebview.api[name]) return null;
    try { return await pywebview.api[name](...args); }
    catch { return null; }
  }

  function setStatus(text, klass) {
    const el = stEl();
    if (!el) return;
    el.textContent = text || '—';
    el.className = 'status ' + (klass || 'gray');
  }

  function disableControls(disabled) {
    const s = sel(); const p = btnPlay(); const c = btnCreate(); const ch = chk();
    if (s) s.disabled = !!disabled;
    if (p) p.disabled = !!disabled;
    if (c) c.disabled = !!disabled;
    if (ch) ch.disabled = !!disabled;
  }

  async function loadList() {
    const s = sel(); if (!s) return;
    const res = await api('record_list');
    if (!res) return; // API ещё не готов — whenAPIReady перезапустит позже

    s.innerHTML = '';
    if (Array.isArray(res) && res.length) {
      for (const r of res) {
        const opt = document.createElement('option');
        opt.value = r.slug;
        opt.textContent = r.name || r.slug;
        s.appendChild(opt);
      }
    } else {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '— нет записей —';
      s.appendChild(opt);
    }

    // выставим current
    const st = await api('record_state');
    const cur = st && st.current_record ? st.current_record : '';
    if (cur && s.querySelector(`option[value="${cur}"]`)) {
      s.value = cur;
    }
    // тумблер
    if (chk() && st) chk().checked = !!st.enabled;
  }

  async function refreshState() {
    const st = await api('record_state');
    if (!st) return;
    if (chk()) chk().checked = !!st.enabled;

    const busy = !!st.busy;
    const status = String(st.status || 'idle');
    const focused = st.focused;
    disableControls(busy || status === 'playing' || status === 'recording');

    let msg = `Статус: ${status}`;
    if (busy) msg += ' • занято';
    if (focused === false) msg += ' • окно без фокуса';
    setStatus(msg, busy ? 'gray' : 'green');

    // если список пуст и уже есть записи в пуле — перерисуем селект
    const s = sel();
    if (s && s.options.length <= 1) {
      await loadList();
    }
  }

  // ----- Events -----
  document.addEventListener('change', async (e) => {
    if (e.target && e.target.id === 'recSelect') {
      const slug = e.target.value || '';
      if (!slug) return;
      await api('record_set_current', slug);
      setStatus('Выбрана запись: ' + e.target.selectedOptions[0].textContent, 'gray');
    }
    if (e.target && e.target.id === 'chkRecord') {
      await api('record_set_enabled', !!e.target.checked);
      setStatus(e.target.checked ? 'Автовоспроизведение: вкл' : 'Автовоспроизведение: выкл', 'gray');
    }
  });

  document.addEventListener('click', async (e) => {
    if (e.target && e.target.id === 'recCreate') {
      const name = prompt('Название записи:');
      if (!name) return;
      const r = await api('record_create', name);
      if (r && r.ok) {
        await loadList();
        const s = sel();
        if (s) s.value = r.slug;
        setStatus('Создана запись: ' + name, 'green');
      } else {
        setStatus('Не удалось создать запись', 'red');
      }
    }
    if (e.target && e.target.id === 'recPlay') {
      disableControls(true);
      const r = await api('record_play_now');
      disableControls(false);
      if (!r || !r.ok) return setStatus('Ошибка запуска воспроизведения', 'red');
      if (r.mode === 'played') setStatus('Воспроизведение запущено', 'green');
      else if (r.mode === 'queued') setStatus('Ожидание фокуса/очередь пайплайна…', 'gray');
      else setStatus('Не удалось запустить воспроизведение', 'red');
    }
  });

  // Хоткей Ctrl+R — старт/стоп записи
  document.addEventListener('keydown', async (e) => {
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.isComposing) return;
    if ((e.ctrlKey || e.metaKey) && (e.key === 'r' || e.key === 'R')) {
      e.preventDefault();
      await api('record_hotkey', 'ctrlR');
    }
  });

  // ----- Boot -----
  function boot() {
    whenAPIReady(async () => {
      await loadList();      // ← теперь точно после инжекта API
      await refreshState();
      setInterval(refreshState, 1000);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
