(function(){
  const api = window.pywebview?.api;
  const $ = id => document.getElementById(id);

  async function refreshVersion(){
    try{
      const r = await api.app_version();
      $('ver').textContent = 'Версия: ' + (r?.version || 'unknown');
    }catch(e){
      $('ver').textContent = 'Версия: ошибка';
    }
  }

  async function testPing(){
    $('conn').textContent = 'Тест...';
    try{
      const r = await api.ping_arduino();
      if(r.ok){
        $('conn').innerHTML = '<span class="ok">Arduino: pong</span>';
      }else{
        $('conn').innerHTML = '<span class="err">Ошибка: ' + (r.error||r.resp||'') + '</span>';
      }
    }catch(e){
      $('conn').innerHTML = '<span class="err">'+e+'</span>';
    }
  }

  $('btn-ping').addEventListener('click', testPing);
  $('btn-quit').addEventListener('click', () => api.quit());

  refreshVersion();
})();
