/* global pywebview */
const $ = (s) => document.querySelector(s);
const logEl = $('#log');
const log = (m) => { if (!m) return; logEl.textContent += m + '\n'; logEl.scrollTop = logEl.scrollHeight; };

async function whenApiReady() {
  if (window.pywebview?.api) return;
  await new Promise(resolve => {
    const onReady = () => {
      if (window.pywebview?.api) {
        window.removeEventListener('pywebviewready', onReady);
        resolve();
      }
    };
    window.addEventListener('pywebviewready', onReady);
  });
}

async function call(name, args = []) {
  try {
    await whenApiReady();
    const api = window.pywebview?.api;
    const fn = api?.[name];
    if (typeof fn !== 'function') {
      const err = `pywebview.api.${name} is not a function`;
      log(`[err] ${name}: ${err}`);
      return { ok: false, error: err };
    }
    const res = await fn(...args);
    return res || {};
  } catch (e) {
    log(`[err] ${name}: ${e}`);
    return { ok: false, error: String(e) };
  }
}

async function init() {
  await whenApiReady();

  // версия
  const v = await call('app_version');
  $('#appVersion').textContent = v.version || '—';

  // сервера
  const s = await call('list_servers');
  const sel = $('#serverSel');
  sel.innerHTML = '';
  (s.items || []).forEach(x => {
    const o = document.createElement('option'); o.value = o.textContent = x; sel.appendChild(o);
  });

  await call('set_language', [$('#langSel').value]);
  await call('set_server', [sel.value]);

  // баф методы (из профиля)
  await refreshBuffMethods();

  // категории
  await refreshCats();
  await refreshRows();

  // периодика: hp и окно
  setInterval(updateHP, 1500);
}

async function refreshBuffMethods() {
  const m = await call('buff_supported_methods');
  const bm = $('#buffMethod'); bm.innerHTML = '';
  (m.methods || []).forEach(x => {
    const o = document.createElement('option'); o.value = o.textContent = x; bm.appendChild(o);
  });
  if (m.current) bm.value = m.current;
}

async function refreshCats() {
  const r = await call('list_categories');
  const cat = $('#catSel'); cat.innerHTML = '';
  (r.items || []).forEach(x => {
    const o = document.createElement('option'); o.value = x.id; o.textContent = (x.display_rus || x.id); cat.appendChild(o);
  });
  await refreshLocs();
}

async function refreshLocs() {
  const cat = $('#catSel').value;
  const r = await call('list_locations', [cat]);
  const loc = $('#locSel'); loc.innerHTML = '';
  (r.items || []).forEach(x => {
    const o = document.createElement('option'); o.value = x.id; o.textContent = (x.display_rus || x.id); loc.appendChild(o);
  });
}

async function refreshRows() {
  const cat = $('#catSel').value;
  const loc = $('#locSel').value;
  const r = await call('rows_list', [cat, loc]);
  const rows = $('#rowsSel'); rows.innerHTML = '';
  (r.items || []).forEach(x => {
    const o = document.createElement('option'); o.value = x.id; o.textContent = x.title || x.id; rows.appendChild(o);
  });
}

async function updateHP() {
  const w = await call('get_window');
  $('#winStatus').textContent = w.info ? `[✓] ${w.info.width}×${w.info.height}` : '[×] окно не найдено';
  const st = await call('state_last');
  if (typeof st.hp_ratio === 'number') {
    const p = Math.max(0, Math.min(100, Math.round(st.hp_ratio * 100)));
    $('#hpVal').textContent = `${p} %`;
  } else {
    $('#hpVal').textContent = '-- %';
  }
}

// ─── handlers ───
$('#btnQuit').onclick = () => call('quit');

$('#langSel').onchange = async (e) => {
  await call('set_language', [e.target.value]);
  await refreshCats(); await refreshRows();
};
$('#serverSel').onchange = async (e) => {
  await call('set_server', [e.target.value]);
  await refreshBuffMethods();
  await refreshCats(); await refreshRows();
};

$('#btnFindWindow').onclick = async () => {
  const r = await call('find_window_now');
  $('#winStatus').textContent = r.found ? '[✓] окно найдено' : '[×] не найдено';
};

$('#btnPing').onclick = async () => {
  const r = await call('test_connection');
  $('#pingStatus').textContent = r.ok ? 'Связь OK' : 'Нет ответа';
};

$('#chkWatch').onchange = async (e) => {
  const r = e.target.checked ? await call('watcher_start') : await call('watcher_stop');
  if (!r.ok && r.error) log(`[watcher] ${r.error}`);
};

$('#btnRiseNow').onclick = async () => {
  const r = await call('to_village_now', [14000]);
  log(`[rise] ${r.ok ? 'OK' : 'FAIL'}`);
};

$('#chkBuff').onchange = (e) => call('buff_enable', [e.target.checked]);
$('#buffMode').onchange = (e) => call('buff_set_mode', [e.target.value]);
$('#buffMethod').onchange = (e) => call('buff_set_method', [e.target.value]);
$('#btnBuffNow').onclick = async () => {
  const r = await call('buff_run_once');
  log(`[buff] ${r.ok ? 'OK' : 'FAIL'}`);
};

function collectMacros() {
  const seq = ($('#macrosSeq').value || '').split(',').map(s => s.trim()).filter(Boolean);
  const delay_s = parseFloat($('#macrosDelay').value || '0') || 0;
  const dur_s = parseFloat($('#macrosDur').value || '0') || 0;
  const en = $('#chkMacros').checked;
  const always = $('#chkMacrosAlways').checked;
  return { enabled: en, seq, delay_s, dur_s, always };
}
async function syncMacros() {
  const m = collectMacros();
  await call('macros_config', [m.enabled, m.seq, m.delay_s, m.dur_s, m.always]);
}
$('#chkMacros').onchange = syncMacros;
$('#chkMacrosAlways').onchange = syncMacros;
$('#macrosSeq').onblur = syncMacros;
$('#macrosDelay').onblur = syncMacros;
$('#macrosDur').onblur = syncMacros;
$('#btnMacrosNow').onclick = async () => {
  await syncMacros();
  const r = await call('macros_run_once');
  log(`[macros] ${r.ok ? 'OK' : 'FAIL'}`);
};

$('#tpMethod').onchange = () => {/* сохраняем при кнопке Save */};
$('#catSel').onchange = async () => { await refreshLocs(); await refreshRows(); };
$('#locSel').onchange = refreshRows;

$('#btnSaveTP').onclick = async () => {
  const cfg = { method: $('#tpMethod').value, cat: $('#catSel').value, loc: $('#locSel').value };
  const r = await call('tp_configure', [cfg.cat, cfg.loc, cfg.method]);
  log(`[tp] config → ${JSON.stringify(r)}`);
};
$('#btnTPNow').onclick = async () => {
  const r = await call('tp_now');
  log(`[tp] ${r.ok ? 'OK' : 'FAIL'}`);
};

$('#btnRowsRefresh').onclick = refreshRows;
$('#btnRowsClear').onclick = () => { $('#rowsSel').value = ''; };

$('#btnAcc').onclick = async () => {
  const dlg = $('#accDlg');
  const cur = await call('account_get');
  $('#accLogin').value = (cur.account && cur.account.login) || '';
  $('#accPass').value = (cur.account && cur.account.password) || '';
  $('#accPin').value = (cur.account && cur.account.pin) || '';
  dlg.showModal();
};
$('#accSave').onclick = async (ev) => {
  ev.preventDefault();
  const r = await call('account_set', [
    $('#accLogin').value, $('#accPass').value, $('#accPin').value
  ]);
  if (r.ok) {
    $('#accDlg').close();
    $('#accInfo').textContent = '✓ сохранено';
  }
};

document.addEventListener('DOMContentLoaded', init);
