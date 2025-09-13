// app/webui/js/record.ui.js
// app/webui/js/record.js )(переименовал прокинул)
(function () {
  // ----- DOM build: вставляем секцию «Запись» после секции Телепорт -----
  function buildSection() {
    const grid = document.querySelector('main.container.grid');
    if (!grid || document.getElementById('sec-record')) return;

    const tp = document.getElementById('sec-tp');
    const sec = document.createElement('section');
    sec.className = 'card';
    sec.id = 'sec-record';
    sec.dataset.section = 'record';
    sec.innerHTML = `
      <h4>Запись</h4>

      <div class="row compact wrap">
        <label class="mr">Запись:</label>
        <select id="recSelect" class="md"></select>
        <button id="recPlay" class="ml">Запустить сейчас</button>
        <button id="recCreate" class="ml">Создать запись</button>
      </div>

      <div class="row compact">
        <span id="status-record" class="status gray">—</span>
      </div>
    `;

    if (tp && tp.nextSibling) grid.insertBefore(sec, tp.nextSibling);
    else grid.appendChild(sec);
  }

  buildSection();

  // ----- Elements -----
  const sel = () => document.getElementById('recSelect');
  const btnPlay = () => document.getElementById('recPlay');
  const btnCreate = () => document.getElementById('recCreate');
  const stEl = () => document.getElementById('status-record');

  // ----- Helpers -----
  async function api(name, ...args) {
    if (!window.pywebview || !pywebview.api || !pywebview.api[name]) {
      console.warn('[record.ui] api not ready:', name);
      return null;
    }
    try { return await pywebview.api[name](...args); }
    catch (e) { console.warn('[record.ui] api error:', name, e); return null; }
  }

  function setStatus(text, klass) {
    const el = stEl();
    if (!el) return;
    el.textContent = text || '—';
    el.className = 'status ' + (klass || 'gray');
  }

  function disableControls(disabled) {
    const s = sel(); const p = btnPlay(); const c = btnCreate();
    if (s) s.disabled = !!disabled;
    if (p) p.disabled = !!disabled;
    if (c) c.disabled = !!disabled;
  }

  async function loadList() {
    const s = sel();
    if (!s) return;
    const res = await api('record_list');
    s.innerHTML = '';
    if (res && Array.isArray(res) && res.length) {
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
  }

  async function refreshState() {
    const st = await api('record_state');
    if (!st) return;
    // статус/индикаторы
    const busy = !!st.busy;
    const status = String(st.status || 'idle');
    const focused = st.focused;
    disableControls(busy || status === 'playing' || status === 'recording');

    let msg = `Статус: ${status}`;
    if (busy) msg += ' • занято';
    if (focused === false) msg += ' • окно без фокуса';
    setStatus(msg, busy ? 'gray' : 'green');
  }

  // ----- Events -----
  document.addEventListener('change', async (e) => {
    if (e.target && e.target.id === 'recSelect') {
      const slug = e.target.value || '';
      if (!slug) return;
      await api('record_set_current', slug);
      setStatus('Выбрана запись: ' + e.target.selectedOptions[0].textContent, 'gray');
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
      if (!r || !r.ok) {
        setStatus('Ошибка запуска воспроизведения', 'red');
        return;
      }
      if (r.mode === 'played') {
        setStatus('Воспроизведение запущено', 'green');
      } else if (r.mode === 'queued') {
        setStatus('Ожидание фокуса/очередь пайплайна…', 'gray');
      } else {
        setStatus('Не удалось запустить воспроизведение', 'red');
      }
    }
  });

  // Хоткей Ctrl+R — старт/стоп записи
  document.addEventListener('keydown', async (e) => {
    // уважаем фокус на инпутах/селектах — не перехватываем
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.isComposing) return;

    if ((e.ctrlKey || e.metaKey) && (e.key === 'r' || e.key === 'R')) {
      e.preventDefault();
      await api('record_hotkey', 'ctrlR');
      // статус обновится поллером
    }
  });

  // ----- Boot -----
  async function boot() {
    await loadList();
    await refreshState();
    // лёгкий поллер на состояние
    setInterval(refreshState, 1000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
