// app/webui/js/pipeline.ui.js
(function(){
  const $ = (s)=>document.querySelector(s);

  function ensurePopup() {
    let dlg = $("#pipelineDlg");
    if (dlg) return dlg;
    dlg = document.createElement("div");
    dlg.id = "pipelineDlg";
    dlg.className = "modal-backdrop";
    dlg.innerHTML = `
      <div class="modal">
        <div class="modal-hdr">Порядок действий</div>
        <div class="modal-body">
          <p class="hint">Respawn закреплён сверху. Перетащите остальные.</p>
          <ul id="pipeList" class="pipe-list"></ul>
        </div>
        <div class="modal-ftr">
          <button id="pipeCancel" class="btn">Отмена</button>
          <button id="pipeSave" class="btn primary">Сохранить</button>
        </div>
      </div>`;
    document.body.appendChild(dlg);
    dlg.addEventListener("click", (e)=>{ if (e.target===dlg) dlg.remove(); });
    $("#pipeCancel").onclick = ()=> dlg.remove();
    $("#pipeSave").onclick = saveOrder;
    return dlg;
  }

  function li(key, text, fixed=false){
    const el = document.createElement("li");
    el.draggable = !fixed;
    el.dataset.key = key;
    el.className = "pipe-item" + (fixed ? " fixed":"");
    el.innerHTML = `<span class="grip">☰</span><span>${text}</span>`;
    if (!fixed) {
      el.addEventListener("dragstart", (ev)=>{ ev.dataTransfer.setData("k", key); el.classList.add("drag"); });
      el.addEventListener("dragend", ()=> el.classList.remove("drag"));
      el.addEventListener("dragover", (ev)=>{ ev.preventDefault(); el.classList.add("over"); });
      el.addEventListener("dragleave", ()=> el.classList.remove("over"));
      el.addEventListener("drop", (ev)=>{
        ev.preventDefault();
        el.classList.remove("over");
        const k = ev.dataTransfer.getData("k");
        const src = [...el.parentNode.children].find(x=>x.dataset.key===k);
        if (src && src!==el) {
          el.parentNode.insertBefore(src, el.nextSibling);
        }
      });
    }
    return el;
  }

  function keyTitle(k){
    return {
      "respawn":"Respawn",
      "macros":"Макросы",
      "buff":"Баф",
      "tp":"Телепорт",
      "autofarm":"Автофарм",
    }[k] || k;
  }

  async function openDialog(){
    const dlg = ensurePopup();
    const list = $("#pipeList");
    list.innerHTML = "";

    let cfg = {enabled:true, order:["respawn","macros"], allowed:["respawn","macros","buff","tp","autofarm"]};
    try { cfg = await pywebview.api.pipeline_get_order(); } catch(_){}

    // Respawn (fixed)
    list.appendChild(li("respawn", keyTitle("respawn"), true));
    // остальные — в порядке из конфига
    cfg.order.filter(k=>k!=="respawn").forEach(k=>{
      if (cfg.allowed.includes(k)) list.appendChild(li(k, keyTitle(k), false));
    });
    // добавим отсутствующие разрешённые (новые фичи)
    cfg.allowed.forEach(k=>{
      if (k!=="respawn" && ![...list.children].some(n=>n.dataset.key===k)) {
        list.appendChild(li(k, keyTitle(k), false));
      }
    });

    dlg.style.display = "block";
  }

  async function saveOrder(){
    const list = $("#pipeList");
    const order = ["respawn", ...[...list.children].map(n=>n.dataset.key).filter(k=>k!=="respawn")];
    try {
      await pywebview.api.pipeline_set_order(order);
    } catch(_){}
    $("#pipelineDlg")?.remove();
  }

  // кнопка в блоке «Респавн»
  function wireButton(){
    const host = document.querySelector("#respawnBlock .actions") || document.querySelector("#respawnBlock");
    if (!host) return;
    let btn = document.getElementById("btnPipeline");
    if (!btn){
      btn = document.createElement("button");
      btn.id = "btnPipeline";
      btn.className = "btn";
      btn.textContent = "Установить порядок действий";
      host.appendChild(btn);
      btn.addEventListener("click", openDialog);
    }
  }

  window.UIPipeline = { init(){ wireButton(); } };
  document.addEventListener("DOMContentLoaded", ()=> setTimeout(()=>window.UIPipeline.init(), 0));
})();
