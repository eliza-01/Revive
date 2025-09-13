// app/webui/js/hud.js
(function(){
  const logEl = document.getElementById('hudLog');
  const MAX = 20; // храним последние 20 сообщений, показываем последнее

  const buf = [];

  function set(text){
    if (!logEl) return;
    logEl.textContent = text || "—";
  }
  function push(arg){
    const attEl = document.getElementById('hudAttention');
    let status = 'ok', text = '';
    if (arg && typeof arg === 'object'){
      status = String(arg.status || 'ok').toLowerCase();
      text = String(arg.text ?? '');
    } else {
      text = String(arg ?? '');
    }

    if (status === 'att'){
      if (attEl){
        attEl.innerHTML = `<span class="att-ico blink">⚠️</span><span class="att-text"></span>`;
        const span = attEl.querySelector('.att-text');
        if (span) span.textContent = text;
      }
      return;
    }

    const t = `[${new Date().toLocaleTimeString()}] ${text}`;
    buf.push(t);
    while (buf.length > MAX) buf.shift();
    set(text);
  }
  function dump(){
    return buf.slice();
  }

  function stop_attention(){
    const attEl = document.getElementById('hudAttention');
    if (attEl) attEl.textContent = '';
  }

  window.ReviveHUD = { set, push, dump, stop_attention };
})();
