// app/webui/js/autofarm.ui.js
(function () {
  // === API helpers (мягкие фолбэки, без throw) ===
  const api = () => (window.pywebview && window.pywebview.api) ? window.pywebview.api : {};

  // Единая точка истины для языка L2 из селекта #l2Lang
  const getL2Lang = () => (document.getElementById("l2Lang")?.value) || "eng";

  // ---- автосейв в пул ----
  async function saveNow() {
    const a = api();
    const payload = {
      profession: state.profession || "",
      skills: (state.skills || []).map(s => ({
        key: s.key || "1",
        slug: s.slug || "",
        cast_ms: Math.max(0, Number(s.cast_ms) || 0),
        cooldown_ms: Math.max(0, Number(s.cooldown_ms ?? s.cd_ms ?? s.cooldown ?? s.cast_ms) || 0),
      })),
      zone: state.zone || "",
      monsters: (state.monsters || []).slice()
    };
    try {
      if (a.autofarm_save)        await a.autofarm_save(payload);
      else if (a.af_save_settings)await a.af_save_settings(payload);
      else if (a.af_set_config)   await a.af_set_config(payload);
    } catch (e) { console.warn("[AF] autosave error:", e); }
  }
  const saveDebounced = (() => {
    let t;
    return () => {
      if (_booting) return;                 // ← не сейвим во время гидратации
      clearTimeout(t);
      t = setTimeout(saveNow, 250);
    };
  })();

  async function fetchProfessions() {
    try {
      const a = api();
      if (typeof a.af_get_professions === "function") {
        const lang = getL2Lang();
        const list = await a.af_get_professions(lang);
        return Array.isArray(list) ? list : [];
      }
    } catch (e) { console.warn("[AF] professions error:", e); }
    return [];
  }

  async function fetchAttackSkills(prof) {
    try {
      const a = api();
      const lang = getL2Lang();
      if (typeof a.af_get_attack_skills === "function") {
        return await a.af_get_attack_skills(prof, lang);
      }
    } catch (e) { console.warn("[AF] attack skills error:", e); }
    return [];
  }

  async function fetchZones() {
    try {
      const a = api();
      const lang = getL2Lang();
      if (typeof a.af_list_zones_declared_only === "function") {
        const list = await a.af_list_zones_declared_only(lang);
        return Array.isArray(list) ? list : [];
      }
      if (typeof a.af_list_zones === "function") {
        const list = await a.af_list_zones(lang);
        return Array.isArray(list) ? list : [];
      }
    } catch (e) { console.warn("[AF] zones error:", e); }
    return [];
  }

  // === Состояние ===
  const AF_KEYS = ["1","2","3","4","5","6","7","8","9","0"];
  const state = {
    enabled: false,
    mode: "auto",
    profession: "",
    // ↓ добавили cooldown_ms в модель
    skills: [],     // [{key, slug, cast_ms, cooldown_ms}]
    monsters: [],
    zone: ""
  };
  // подавляем автосейв во время первичной гидратации
  let _booting = false;

  // === Утилиты ===
  const $ = (id) => document.getElementById(id);
  const showModal = (id, on) => { const el = $(id); if (el) el.classList.toggle("hidden", !on); };
  const cap = (s)=> (s||"").split("_").map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(" ");
  function slugifyName(s){
    return String(s||"").toLowerCase()
      .replace(/[’`]/g, "'")
      .replace(/[^a-z0-9а-яё_' -]/gi, "")
      .replace(/[\s\-']+/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function validate() {
    const hasProf = !!state.profession;
    const hasSkill = state.skills.some(s => s.key && s.slug && Number(s.cast_ms) > 0);
    const hasZone = !!state.zone;
    return {
      ok: hasProf && hasSkill && hasZone,
      reason: hasProf ? (hasSkill ? (hasZone ? null : "Выберите зону") : "Добавьте атакующий скилл") : "Выберите профессию"
    };
  }

  // селект с иконками
  function buildSkillCombo(skillsList, item){
    const wrap = document.createElement("div"); wrap.className = "combo";
    const btn  = document.createElement("button"); btn.type = "button"; btn.className = "combo-btn";
    const ico  = document.createElement("img"); ico.className = "combo-ico";
    const lab  = document.createElement("span"); lab.className = "combo-label";
    btn.appendChild(ico); btn.appendChild(lab);

    const menu = document.createElement("div"); menu.className = "combo-menu hidden";
    (skillsList || []).forEach(s => {
      const it  = document.createElement("div"); it.className = "combo-item";
      const im  = document.createElement("img"); im.src = s.icon || "";
      const tx  = document.createElement("span"); tx.textContent = s.name || (s.slug || "");
      it.appendChild(im); it.appendChild(tx);
      it.addEventListener("click", () => {
        item.slug = s.slug;
        ico.src = s.icon || "";
        lab.textContent = s.name || s.slug;
        menu.classList.add("hidden");
        saveDebounced();
      });
      menu.appendChild(it);
    });

    btn.addEventListener("click", () => { menu.classList.toggle("hidden"); });
    document.addEventListener("click", (e) => { if (!wrap.contains(e.target)) menu.classList.add("hidden"); });

    const cur = (skillsList || []).find(x => x.slug === item.slug);
    if (cur) { ico.src = cur.icon || ""; lab.textContent = cur.name || cur.slug; }
    else { ico.src = ""; lab.textContent = "— выбрать —"; }

    wrap.appendChild(btn); wrap.appendChild(menu);
    return wrap;
  }

  // строка скилла
  function buildSkillRow(item, skillsList) {
    const row = document.createElement("div");
    row.className = "af-skill";

    const keySel = document.createElement("select");
    AF_KEYS.forEach(k => keySel.appendChild(new Option(k, k)));
    keySel.value = item.key || "1";
    keySel.addEventListener("change", () => { item.key = keySel.value; saveDebounced(); });
    row.appendChild(keySel);

    row.appendChild(buildSkillCombo(skillsList, item));

    const cast = document.createElement("input");
    cast.type = "number"; cast.min = "1"; cast.step = "1"; cast.className = "xs";
    cast.value = item.cast_ms ?? 850;
    cast.addEventListener("change", () => {
      item.cast_ms = Math.max(1, parseInt(cast.value || "0", 10));
      saveDebounced();
    });
    row.appendChild(cast);

    const cd = document.createElement("input");
    cd.type = "number"; cd.min = "0"; cd.step = "1"; cd.className = "xs";
    cd.value = item.cooldown_ms ?? item.cd_ms ?? item.cooldown ?? item.cast_ms ?? 1100;
    cd.addEventListener("change", () => {
      const v = Math.max(0, parseInt(cd.value || "0", 10));
      item.cooldown_ms = Number.isFinite(v) ? v : 0;
      saveDebounced();
    });
    row.appendChild(cd);

    return row;
  }

  async function renderSkillsBlock() {
    const cont = $("afSkillRows"); if (!cont) return;
    cont.innerHTML = "";

    const hdr = document.createElement("div");
    hdr.className = "row compact";
    hdr.innerHTML = '' +
      '<span class="col col-key">Клавиша</span>' +
      '<span class="col col-skill">Скилл</span>' +
      '<span class="col col-cast">Каст, мс</span>' +
      '<span class="col col-cd">КД, мс</span>';
    cont.appendChild(hdr);

    if (!state.skills.length) state.skills.push({ key:"1", slug:"", cast_ms:850 });
    const list = await fetchAttackSkills(state.profession);
    state.skills.forEach(item => cont.appendChild(buildSkillRow(item, list)));
  }

  // монстры
  async function renderMonsters() {
    const box = $("afMonsters"); if (!box) return;
    box.innerHTML = "";
    const zoneId = ($("afZone") && $("afZone").value) || "";
    if (!zoneId) return;

    const lang = getL2Lang();

    let info = null;
    try {
      if (api().af_zone_info) info = await api().af_zone_info(zoneId, lang);
    } catch (e) { console.warn("[AF] zone info error:", e); }
    const list = (info && info.monsters) || [];

    const allSlugs = list.map(m => (typeof m === "string" ? slugifyName(m) : m.slug));
    if (!state.monsters.length) state.monsters = allSlugs.slice();

    list.forEach(m => {
      const slug = (typeof m === "string") ? slugifyName(m) : m.slug;
      const title = (typeof m === "string") ? m : (m.name || m.slug);

      const label = document.createElement("label");
      label.className = "monster";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = state.monsters.includes(slug);
      cb.addEventListener("change", () => {
        if (cb.checked) { if (!state.monsters.includes(slug)) state.monsters.push(slug); }
        else { state.monsters = state.monsters.filter(x => x !== slug); }
        saveDebounced();
      });

      const span = document.createElement("span");
      span.textContent = title;

      label.appendChild(cb);
      label.appendChild(span);
      box.appendChild(label);
    });
  }

  // профы и зоны
  async function fillProfessions() {
    const sel = $("afProf"); if (!sel) return;
    sel.innerHTML = "";
    const profs = await fetchProfessions(); // [{slug,title}]
    if (!profs.length) {
      sel.appendChild(new Option("— нет данных —", ""));
      const st = $("status-af");
      if (st) { st.textContent = "Профессии не найдены"; st.classList.add("warn"); }
      return;
    }
    sel.appendChild(new Option("— выбрать —",""));
    profs.forEach(p => {
      const slug = typeof p === "string" ? p : p.slug;
      const title = typeof p === "string" ? cap(p) : (p.title || slug);
      sel.appendChild(new Option(title, slug));
    });
    sel.disabled = false;
    sel.value = state.profession || "";
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

  // попап инфо по зоне
  async function openZoneInfo() {
    const zoneId = ($("afZone")?.value) || "";
    if (!zoneId) return;
    const lang = getL2Lang();

    let info = { id: zoneId, title: zoneId, about: "", images: [] };
    try {
      if (api().af_zone_info) {
        const r = await api().af_zone_info(zoneId, lang);
        if (r) info = r;
      }
    } catch (e) { console.warn("[AF] zone info error:", e); }

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

  // ждём, пока pywebview.api вообще появится и будет нужный метод
  function waitForApi(methodName = null, timeoutMs = 8000) {
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const tick = () => {
        const a = (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
        const ok = a && (!methodName || typeof a[methodName] === "function");
        if (ok) return resolve(a);
        if (Date.now() - started >= timeoutMs) {
          return reject(new Error("pywebview.api is not ready"));
        }
        setTimeout(tick, 50);
      };
      tick();
    });
  }

  async function hydrateFromPool() {
    _booting = true;
    try {
      const a = await waitForApi("autofarm_get");       // ← ЖДЁМ, а не выходим
      const r = await a.autofarm_get();
      if (!r || !r.ok) return;

      // раскладываем в state
      state.enabled    = !!r.enabled;
      state.mode       = r.mode || "auto";
      const cfg        = r.config || {};
      state.profession = cfg.profession || "";
      state.skills = Array.isArray(cfg.skills) && cfg.skills.length
        ? cfg.skills.map(s => {
            const cast = Number(s?.cast_ms);
            const cd   = Number(s?.cooldown_ms ?? s?.cd_ms ?? s?.cooldown ?? s?.cast_ms);
            return {
              key:  s?.key || "1",
              slug: s?.slug || "",
              cast_ms: Number.isFinite(cast) ? cast : 850,
              cooldown_ms: Number.isFinite(cd) ? cd : (Number.isFinite(cast) ? cast : 850),
            };
          })
        : [{ key:"3", slug:"", cast_ms:850, cooldown_ms:850 }];
      state.zone       = cfg.zone || "";
      state.monsters   = Array.isArray(cfg.monsters) ? cfg.monsters.slice() : [];

      // режимы в селект
      const modeSel = document.getElementById("afMode");
      if (modeSel) {
        const modes = Array.isArray(r.modes) && r.modes.length ? r.modes : ["auto","manual"];
        modeSel.innerHTML = "";
        modes.forEach(m => modeSel.appendChild(new Option(m, m)));
        modeSel.value = state.mode;
      }

      const chk = document.getElementById("chkAF");
      if (chk) chk.checked = state.enabled;

      await fillProfessions();
      const profSel = document.getElementById("afProf");
      if (profSel) profSel.value = state.profession || "";

      await renderSkillsBlock();

      await fillZones();
      const zoneSel = document.getElementById("afZone");
      if (zoneSel) {
        const valid = Array.from(zoneSel.options).some(o => o.value === state.zone);
        zoneSel.value = valid ? state.zone : "";
        if (!valid) state.zone = "";
      }

      await renderMonsters();

      const v  = validate();
      const st = document.getElementById("status-af");
      if (st) {
        st.textContent = v.ok ? "Настроено" : (v.reason || "Не настроено");
        st.classList.toggle("ok", v.ok);
        st.classList.toggle("warn", !v.ok);
      }
    } catch (e) {
      console.warn("[AF] hydrate error:", e);
    } finally {
      _booting = false;
    }
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

    // режим
    if (mode) mode.addEventListener("change", async () => {
      state.mode = mode.value;
      try { await api().autofarm_set_mode(state.mode || "auto"); } catch(e){ console.warn(e); }
    });

    // открыть настройки
    if (btn) btn.addEventListener("click", async () => {
      try {
        await fillProfessions();
        await renderSkillsBlock();
        await fillZones();
        await renderMonsters();
      } catch (e) {
        console.error("[AF] open settings error:", e);
      } finally {
        showModal("afModal", true);
      }
    });

    if (close) close.addEventListener("click", ()=> { showModal("afModal", false); });

    // сохранить настройки (бекенд: любой доступный метод)
    if (save) save.addEventListener("click", async () => {
      const v = validate();
      if (status) {
        status.textContent = v.ok ? "Настроено" : (v.reason || "Не настроено");
        status.classList.toggle("ok", v.ok);
        status.classList.toggle("warn", !v.ok);
      }
      if (!v.ok) return;

      const payload = {
        profession: state.profession,
        skills: state.skills,
        zone: state.zone,
        monsters: state.monsters
      };
      if (!v.ok) return;
      await saveNow();
      showModal("afModal", false);
    });

    // профа/скиллы
    if (prof) prof.addEventListener("change", async () => {
      state.profession = prof.value || "";
      state.skills = [{ key:"1", slug:"", cast_ms:850, cooldown_ms:850 }];
      await renderSkillsBlock();
      saveDebounced();
    });
    if (add) add.addEventListener("click", async ()=> {
      state.skills.push({ key:"1", slug:"", cast_ms:850, cooldown_ms:850 });
      await renderSkillsBlock();
      saveDebounced();
    });
    if (del) del.addEventListener("click", async ()=> {
      if (state.skills.length > 1) state.skills.pop();
      await renderSkillsBlock();
      saveDebounced();
    });

    // зона/монстры
    if (zone) zone.addEventListener("change", async () => {
      state.zone = zone.value || "";
      state.monsters = [];
      await renderMonsters();
      saveDebounced();
    });
    if (infoBtn)   infoBtn.addEventListener("click", openZoneInfo);
    if (infoClose) infoClose.addEventListener("click", ()=> showModal("afZoneInfoModal", false));

    // включение/выключение АФ — поддержка старого и нового API
    async function afEnable(mode) {
      const a = api();
      try {
        if (a.autofarm_set_mode && a.autofarm_set_enabled) {
          await a.autofarm_set_mode(mode || "auto");
          await a.autofarm_set_enabled(true);
          return true;
        }
        if (a.af_start) {
          await a.af_start(mode || "auto");
          return true;
        }
      } catch (e) { console.error("[AF] start error:", e); }
      return false;
    }
    async function afDisable() {
      const a = api();
      try {
        if (a.autofarm_set_enabled) { await a.autofarm_set_enabled(false); return true; }
        if (a.af_stop)              { await a.af_stop(); return true; }
      } catch (e) { console.error("[AF] stop error:", e); }
      return false;
    }

    if (chk) chk.addEventListener("change", async () => {
      const st = document.getElementById("status-af");

      if (chk.checked) {
        const v = validate();
        if (!v.ok) {
          chk.checked = false;
          if (st) { st.textContent = v.reason; st.classList.remove("ok"); st.classList.add("warn"); }
          document.getElementById("afModal")?.classList.remove("hidden");
          return;
        }
        try {
          await pywebview.api.autofarm_set_mode(state.mode || "auto");
          await pywebview.api.autofarm_set_enabled(true);
          if (st) { st.textContent = "Настроено"; st.classList.add("ok"); st.classList.remove("warn"); }
        } catch (e) {
          console.error(e);
          chk.checked = false;
          if (st) { st.textContent = "Ошибка запуска АФ"; st.classList.remove("ok"); st.classList.add("warn"); }
        }
      } else {
        try {
          // используем универсальную остановку
          const a = (window.pywebview && window.pywebview.api) ? window.pywebview.api : {};
          if (a.autofarm_set_enabled) await a.autofarm_set_enabled(false);
          else if (a.af_stop)         await a.af_stop();

          // хард-кансел на случай «висящего» цикла (если есть в бэкенде)
          if (a.autofarm_cancel_cycle) await a.autofarm_cancel_cycle();
          if (a.af_abort)              await a.af_abort();
          if (st) { st.textContent = "Отключено"; st.classList.remove("ok","warn"); }
        } catch (e) {
          console.error(e);
          chk.checked = true; // не врём UI
          if (st) { st.textContent = "Не удалось остановить АФ"; st.classList.remove("ok"); st.classList.add("warn"); }
        }
      }
    });

    // автоинициализация при первом ручном открытии
    const modal = $("afModal");
    if (modal && typeof MutationObserver !== "undefined") {
      let inited = false;
      const mo = new MutationObserver(() => {
        const isOpen = !modal.classList.contains("hidden");
        if (isOpen && !inited) {
          inited = true;
          Promise.resolve().then(async () => {
            await fillProfessions();
            await renderSkillsBlock();
            await fillZones();
            await renderMonsters();
          });
        }
      });
      mo.observe(modal, { attributes: true, attributeFilter: ["class"] });
    }
  }

  let _hydratedOnce = false;
  async function bootOnce() {
    if (_hydratedOnce) return;
    _hydratedOnce = true;
    await hydrateFromPool();
  }

  document.addEventListener("DOMContentLoaded", async () => {
    wireEvents();
    // старта может хватить, если API уже есть
    bootOnce();
  });

  window.addEventListener("pywebviewready", () => {
    // этот эвент гарантирует готовый API — дублируем на всякий
    bootOnce();
  });
})();
