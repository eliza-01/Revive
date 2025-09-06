// app/webui/js/hud.js
(function(){
  const logEl = document.getElementById('hudLog');
  const MAX = 20; // храним последние 20 сообщений, показываем последнее

  const buf = [];

  function set(text){
    if (!logEl) return;
    logEl.textContent = text || "—";
  }
  function push(text){
    const t = `[${new Date().toLocaleTimeString()}] ${text}`;
    buf.push(t);
    while (buf.length > MAX) buf.shift();
    set(text);
  }
  function dump(){
    return buf.slice();
  }

  window.ReviveHUD = { set, push, dump };
})();
