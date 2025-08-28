// app/webui/js/autofarm.ui.js
(function () {
  // === STUB-данные: замените позже вызовами из core/engines/autofarm ===
  const STUB = {
    professions: ["mystic_muse", "sagittarius"],
    attackSkills: {
      mystic_muse: [
        { slug: "hydro_blast", name: "Hydro Blast", icon: null },
        { slug: "solar_flare", name: "Solar Flare", icon: null },
        { slug: "aura_flare",  name: "Aura Flare",  icon: null },
        { slug: "ice_vortex",  name: "Ice Vortex",  icon: null }
      ],
      sagittarius: [
        { slug: "attack",    name: "Attack",    icon: null },
        { slug: "stun_shot", name: "Stun Shot", icon: null }
      ]
    },
    zones: [
      { id: "Varka_1",    title: "Varka 1" },
      { id: "Primeval_1", title: "Primeval Isle 1" }
    ]
  };
  async function fetchProfessions() {
    const api = (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
    if (!api || typeof api.af_get_professions !== "function") {
      throw new Error("[AF] pywebview.api.af_get_professions отсутствует");
    }
    const langEl = document.getElementById("lang");
    const lang = (langEl && langEl.value) ? langEl.value : "eng";
    const list = await api.af_get_professions(lang);
    console.log("[AF] professions ->", list);
    return Array.isArray(list) ? list : [];
  }
  async function fetchAttackSkills(prof) {
    const langEl = document.getElementById("lang");
    const lang = (langEl && langEl.value) ? langEl.value : "eng";
    if (window.pywebview && window.pywebview.api && typeof pywebview.api.af_get_attack_skills === "function") {
      return await pywebview.api.af_get_attack_skills(prof, lang);
    }
    return []; // без API не показываем
  }
  async function fetchZones() {
    const langEl = document.getElementById("lang");
    const lang = (langEl && langEl.value) ? langEl.value : "eng";
    if (window.pywebview && window.pywebview.api && typeof pywebview.api.af_list_zones_declared_only === "function") {
      const list = await pywebview.api.af_list_zones_declared_only(lang);
      return Array.isArray(list) ? list : [];
    }
    // нет API → ничего не показываем, чтобы не было "левых" зон
    return [];
  }

  // === Состояние ===
  const AF_KEYS = ["1","2","3","4","5","6","7","8","9","0"];
  const state = {
    enabled: false,
    mode: "after_tp",
    profession: "",
    skills: [],   // [{key, slug, cast_ms}]
    zone: ""
  };

  // === Утилиты ===
  const $ = (id) => document.getElementById(id);
  const showModal = (id, on) => { const el = $(id); if (el) el.classList.toggle("hidden", !on); };
  const cap = (s)=> (s||"").split("_").map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(" ");

  function validate() {
    const hasProf = !!state.profession;
    const hasSkill = state.skills.some(s => s.key && s.slug && Number(s.cast_ms) > 0);
    const hasZone = !!state.zone;
    return { ok: hasProf && hasSkill && hasZone,
      reason: hasProf ? (hasSkill ? (hasZone ? null : "Выберите зону") : "Добавьте атакующий скилл") : "Выберите профессию" };
  }
  // --- автоинициализация попапа настроек ---
  let afInitedOnce = false;

  async function openAFSettings() {
    await fillProfessions();
    await renderSkillsBlock();
    await fillZones();
    showModal("afModal", true);
    afInitedOnce = true;

    // на всякий случай закрыть инфо-попап, чтобы он не перекрывал селект зоны
    // showModal("afZoneInfoModal", false);
    // showModal("afModal", true);
  }

  //для отображения иконки около выпадающего списка?)
  function buildSkillCombo(skillsList, item){
    const wrap = document.createElement("div"); wrap.className = "combo";
    const btn  = document.createElement("button"); btn.type = "button"; btn.className = "combo-btn";
    const ico  = document.createElement("img"); ico.className = "combo-ico";
    const cap  = document.createElement("span"); cap.className = "combo-label";
    btn.appendChild(ico); btn.appendChild(cap);

    const menu = document.createElement("div"); menu.className = "combo-menu hidden";
    (skillsList || []).forEach(s => {
      const it  = document.createElement("div"); it.className = "combo-item";
      const im  = document.createElement("img"); im.src = s.icon || "";
      const lab = document.createElement("span"); lab.textContent = s.name || (s.slug || "");
      it.appendChild(im); it.appendChild(lab);
      it.addEventListener("click", () => {
        item.slug = s.slug;
        ico.src = s.icon || ""; cap.textContent = s.name || s.slug;
        menu.classList.add("hidden");
      });
      menu.appendChild(it);
    });

    btn.addEventListener("click", () => { menu.classList.toggle("hidden"); });
    document.addEventListener("click", (e) => { if (!wrap.contains(e.target)) menu.classList.add("hidden"); });

    // начальное состояние
    const cur = (skillsList || []).find(x => x.slug === item.slug);
    if (cur) { ico.src = cur.icon || ""; cap.textContent = cur.name || cur.slug; }
    else { ico.src = ""; cap.textContent = "— выбрать —"; }

    wrap.appendChild(btn); wrap.appendChild(menu);
    return wrap;
  }

  // === Рендер строк скиллов ===
  function buildSkillRow(item, skillsList) {
    const row = document.createElement("div");
    row.className = "af-skill";

    // Клавиша
    const keySel = document.createElement("select");
    AF_KEYS.forEach(k => keySel.appendChild(new Option(k, k)));
    keySel.value = item.key || "1";
    keySel.addEventListener("change", () => { item.key = keySel.value; });
    row.appendChild(keySel);

    // Скилл: кастомный дропдаун с иконками
    row.appendChild(buildSkillCombo(skillsList, item));

    // Каст, мс
    const cast = document.createElement("input");
    cast.type = "number"; cast.min = "1"; cast.step = "1"; cast.className = "xs";
    cast.value = item.cast_ms ?? 500;
    cast.addEventListener("change", () => { item.cast_ms = Math.max(1, parseInt(cast.value || "0", 10)); });
    row.appendChild(cast);

    return row;
  }


  async function renderSkillsBlock() {
    const cont = $("afSkillRows"); if (!cont) return;
    cont.innerHTML = "";

    // заголовки
    const hdr = document.createElement("div");
    hdr.className = "row compact";
    hdr.innerHTML = '<span class="col col-key">Клавиша</span><span class="col col-skill">Скилл</span><span class="col col-cast">Каст, мс</span>';
    cont.appendChild(hdr);

    if (!state.skills.length) state.skills.push({ key:"1", slug:"", cast_ms:500 });
    const list = await fetchAttackSkills(state.profession);
    state.skills.forEach(item => cont.appendChild(buildSkillRow(item, list)));
  }

  // === Профы и зоны ===
  async function fillProfessions() {
    const sel = document.getElementById("afProf"); if (!sel) return;
    sel.innerHTML = "";
    try {
      const profs = await fetchProfessions(); // [{slug,title}]
      if (!profs.length) {
        sel.appendChild(new Option("— нет данных —", ""));
        const st = document.getElementById("status-af");
        if (st) { st.textContent = "Профессии не найдены (см. консоль)"; st.classList.add("warn"); }
        return;
      }
      sel.appendChild(new Option("— выбрать —",""));
      profs.forEach(p => {
        const slug = typeof p === "string" ? p : p.slug;
        const title = typeof p === "string" ? (p.split("_").map(s=>s[0].toUpperCase()+s.slice(1)).join(" ")) : (p.title || slug);
        sel.appendChild(new Option(title, slug));
      });
      sel.disabled = false;
      sel.value = state.profession || "";
    } catch (e) {
      console.error(e);
      sel.appendChild(new Option("— API недоступен —", ""));
      const st = document.getElementById("status-af");
      if (st) { st.textContent = "Нет API af_get_professions"; st.classList.add("warn"); }
    }
  }

  async function fillZones() {
    const sel = $("afZone"); if (!sel) return;
    const zones = await fetchZones();
    const current = state.zone;
    sel.innerHTML = "";
    sel.appendChild(new Option("— выбрать —",""));
    zones.forEach(z => sel.appendChild(new Option(z.title, z.id)));
    sel.disabled = false;
    const valid = zones.some(z => z.id === current);
    sel.value = valid ? current : "";
    if (!valid) state.zone = "";
  }

  // === Инфо по зоне ===
  async function openZoneInfo() {
    const zoneId = ($("afZone")?.value) || "";
    if (!zoneId) return;
    const langEl = document.getElementById("lang");
    const lang = (langEl && langEl.value) ? langEl.value : "eng";

    let info = null;
    if (window.pywebview && window.pywebview.api && window.pywebview.api.af_zone_info) {
      info = await pywebview.api.af_zone_info(zoneId, lang);
    } else {
      info = { id: zoneId, title: zoneId, about: "", images: [] };
    }

    const titleEl = $("afZoneInfoTitle");
    const body = $("afZoneInfoBody");
    if (titleEl) titleEl.textContent = info.title || zoneId;

    if (body) {
      body.innerHTML = "";
      (info.images || []).forEach((im, i) => {
        const img = document.createElement("img");
        img.src = im.src; img.alt = im.name || ""; img.className = "zinfo-img";
        body.appendChild(img);
        if (i < info.images.length - 1) {
          const sep = document.createElement("div"); sep.className = "zinfo-sep"; body.appendChild(sep);
        }
      });
      if (info.about) {
        const sep = document.createElement("div"); sep.className = "zinfo-sep"; body.appendChild(sep);
        const txt = document.createElement("div"); txt.className = "zinfo-about"; txt.textContent = info.about; body.appendChild(txt);
      }
    }
    showModal("afZoneInfoModal", true);
  }

  // === События ===
  function wireEvents() {
    const chk   = $("chkAF");
    const mode  = $("afMode");
    const btn   = $("btnAFSettings");
    const close = $("afClose");
    const save  = $("afSave");
    const prof  = $("afProf");
    const add   = $("afAddSkill");
    const del   = $("afDelSkill");
    const zone  = $("afZone");
    const status= $("status-af");
    const infoBtn   = $("btnAFZoneInfo");
    const infoClose = $("afZoneInfoClose");

    if (chk) chk.addEventListener("change", () => {
      const v = validate();
      if (!v.ok) {
        chk.checked = false;
        if (status) { status.textContent = v.reason; status.classList.remove("ok"); status.classList.add("warn"); }
        showModal("afModal", true);
        return;
      }
      state.enabled = chk.checked;
      if (status) { status.textContent = chk.checked ? "Включено" : "Выключено"; status.classList.toggle("ok", chk.checked); }
    });

    if (mode) mode.addEventListener("change", ()=> state.mode = mode.value);

    if (btn) btn.addEventListener("click", async () => {
      try {
        await fillProfessions();
        await renderSkillsBlock();
        await fillZones();
      } catch (e) {
        console.error("[AF] open settings error:", e);
      } finally {
        showModal("afModal", true);
      }
    });

    if (close) close.addEventListener("click", ()=> { showModal("afModal", false); });

    if (save)  save.addEventListener("click", () => {
      const v = validate();
      if (status) {
        status.textContent = v.ok ? "Настроено" : (v.reason || "Не настроено");
        status.classList.toggle("ok", v.ok);
        status.classList.toggle("warn", !v.ok);
      }
      if (v.ok) showModal("afModal", false); // закрываем только если всё настроено
    });

    if (prof) prof.addEventListener("change", async () => {
      state.profession = prof.value || "";
      state.skills = [{ key:"1", slug:"", cast_ms:500 }];
      await renderSkillsBlock();
    });

    if (add) add.addEventListener("click", async ()=> {
      state.skills.push({ key:"1", slug:"", cast_ms:500 });
      await renderSkillsBlock();
    });

    if (del) del.addEventListener("click", async ()=> {
      if (state.skills.length > 1) state.skills.pop();
      await renderSkillsBlock();
    });

    if (zone) zone.addEventListener("change", ()=> {
      // выбор зоны фиксируем в состоянии
      state.zone = zone.value || "";
    });

    if (infoBtn)   infoBtn.addEventListener("click", openZoneInfo);
    if (infoClose) infoClose.addEventListener("click", ()=> showModal("afZoneInfoModal", false));

    // если модал откроют не через кнопку, заполним данные автоматически один раз
    const modal = $("afModal");
    if (modal && typeof MutationObserver !== "undefined") {
      const mo = new MutationObserver(() => {
        const isOpen = !modal.classList.contains("hidden");
        if (isOpen && !afInitedOnce) openAFSettings();
      });
      mo.observe(modal, { attributes: true, attributeFilter: ["class"] });
    }
  }

  document.addEventListener("DOMContentLoaded", wireEvents);
})();
