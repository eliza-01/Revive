// app/webui/js/extra.buff.profile.js
(function () {
  const $ = (sel) => document.querySelector(sel);

  const ICON_ID = "buffProfileHintIcon";
  const TIP_ID  = "buffProfileHintTooltip";

  // Вернёт Promise<string> с data: URI (если backend реализован) или "".
//  function resolveProfileImageURL() {
//    try {
//      const api = window.pywebview?.api?.image_access;
//      if (api && typeof api.get_image_uri === "function") {
//        // Относительная ссылка на изображение, которую передаём в backend
//        const rel = "app/webui/assets/lineage/BOH/interface/dashboard_buffer_profile.png";
//        return api.get_image_uri(rel).then(...);
//          .then(r => (r && r.ok && r.uri) ? r.uri : "")
//          .catch(() => "");
//      }
//    } catch (_) {}
//    return Promise.resolve("");
//  }
  function resolveProfileImageURL() {
    // файл лежит в app/webui/assets/...
    return Promise.resolve("assets/lineage/BOH/interface/dashboard_buffer_profile.png");
  }

  let hideTipTimer = null;

  function create(tag, attrs = {}, text = "") {
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => (k === "class" ? (el.className = v) : el.setAttribute(k, v)));
    if (text) el.textContent = text;
    return el;
  }

  function ensureTooltip() {
    let tip = document.getElementById(TIP_ID);
    if (tip) return tip;

    tip = create("div", { id: TIP_ID });
    Object.assign(tip.style, {
      position: "fixed",
      zIndex: "99999",
      maxWidth: "420px",
      background: "rgba(20,20,20,0.96)",
      color: "#eee",
      borderRadius: "10px",
      padding: "12px 12px 10px",
      boxShadow: "0 6px 24px rgba(0,0,0,0.35)",
      border: "1px solid rgba(255,255,255,0.08)",
      display: "none",
    });

    // «Как текст ошибки»
    const title = create("div", { class: "tip-title" }, "Название профиля должно быть \"profile\"");
    Object.assign(title.style, {
      color: "#ffb84d",
      marginBottom: "8px",
      fontSize: "13px",
      fontWeight: "600"
    });

    const img = create("img", { alt: "Пример профиля 'profile'" });
    Object.assign(img.style, {
      display: "block",
      maxWidth: "160px",
      width: "100%",
      height: "auto",
      borderRadius: "8px",
      border: "1px solid rgba(255,255,255,0.1)",
      background: "#111",
      margin: "0 auto", // центрирование по горизонтали
    });

    // загрузка изображения подсказки
    resolveProfileImageURL().then((url) => {
      if (url) img.src = url;
    });

    img.onerror = () => {
      const warn = create("div", { class: "tip-warn" }, "Не удалось загрузить изображение подсказки.");
      const small = create("div", { class: "tip-path" }, img.src || "(путь неизвестен)");
      Object.assign(warn.style, { color: "#ffb84d", marginTop: "8px", fontSize: "13px" });
      Object.assign(small.style, { color: "#aaa", fontSize: "11px", marginTop: "4px", wordBreak: "break-all" });
      img.replaceWith(warn);
      warn.appendChild(small);
      console.warn("[extra.buff.profile] image load failed:", img.src);
    };

    tip.appendChild(title);
    tip.appendChild(img);
    document.body.appendChild(tip);
    return tip;
  }

  function showTooltipNear(target) {
    const tip = ensureTooltip();
    if (!target) return;

    const rect = target.getBoundingClientRect();
    const margin = 8;
    const top = Math.max(8, rect.bottom + margin);
    const left = Math.min(
      Math.max(8, rect.left),
      Math.max(8, window.innerWidth - 8 - 420)
    );

    tip.style.top = `${top}px`;
    tip.style.left = `${left}px`;
    tip.style.display = "block";
  }

  function hideTooltip() {
    const tip = document.getElementById(TIP_ID);
    if (tip) tip.style.display = "none";
  }

  function ensureIcon() {
    let icon = document.getElementById(ICON_ID);
    if (icon) return icon;

    // Иконка: отступ 2px справа от селекта, контент по центру
    icon = create("button", { id: ICON_ID, type: "button", title: "" }, "⚠️");
    Object.assign(icon.style, {
      marginLeft: "2px",
      cursor: "pointer",
      border: "0",
      background: "transparent",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      width: "24px",
      lineHeight: "1",
      fontSize: "16px",
      padding: "0",
    });

    icon.addEventListener("mouseenter", () => {
      if (hideTipTimer) { clearTimeout(hideTipTimer); hideTipTimer = null; }
      showTooltipNear(icon);
    });
    icon.addEventListener("mouseleave", () => {
      if (hideTipTimer) clearTimeout(hideTipTimer);
      hideTipTimer = setTimeout(hideTooltip, 140);
    });

    const tip = ensureTooltip();
    tip.addEventListener("mouseenter", () => {
      if (hideTipTimer) { clearTimeout(hideTipTimer); hideTipTimer = null; }
    });
    tip.addEventListener("mouseleave", () => {
      if (hideTipTimer) clearTimeout(hideTipTimer);
      hideTipTimer = setTimeout(hideTooltip, 120);
    });

    return icon;
  }

  function attachIconNextToMode() {
    const modeSel = $("#buffMode");
    if (!modeSel) return;

    const icon = ensureIcon();
    if (icon.parentElement !== modeSel.parentElement) {
      modeSel.parentElement.insertBefore(icon, modeSel.nextSibling);
    }
    // высота = высоте селекта
    requestAnimationFrame(() => {
      try {
        const h = modeSel.offsetHeight || 28;
        icon.style.height = `${h}px`;
      } catch(_) {}
    });
  }

  function removeHint() {
    const icon = document.getElementById(ICON_ID);
    if (icon && icon.parentElement) icon.parentElement.removeChild(icon);
    hideTooltip();
  }

  function shouldShow() {
    const server = ($("#server")?.value || "").toLowerCase();
    const mode = ($("#buffMode")?.value || "").toLowerCase();
    return server === "boh" && mode === "profile";
  }

  function update() {
    if (shouldShow()) attachIconNextToMode();
    else removeHint();
  }

  function wire() {
    // реагируем на смену сервера/режима
    const serverSel = $("#server");
    if (serverSel && !serverSel.__buffProfileHintWired) {
      serverSel.addEventListener("change", update);
      serverSel.__buffProfileHintWired = true;
    }
    const modeSel = $("#buffMode");
    if (modeSel && !modeSel.__buffProfileHintWired) {
      modeSel.addEventListener("change", update);
      modeSel.__buffProfileHintWired = true;
    }

    // ресайз
    window.addEventListener("resize", () => {
      const icon = document.getElementById(ICON_ID);
      const ms = $("#buffMode");
      if (icon && ms) icon.style.height = `${ms.offsetHeight || 28}px`;
    });

    // патч ReviveUI.onBuffMethods — обновляемся после программной смены
    const patch = () => {
      if (!window.ReviveUI) return false;
      if (window.ReviveUI.__profileHintPatched) return true;

      const orig = window.ReviveUI.onBuffMethods;
      window.ReviveUI.onBuffMethods = function (methods, current) {
        try { if (typeof orig === "function") orig.call(window.ReviveUI, methods, current); } catch(_) {}
        setTimeout(update, 0);
      };
      window.ReviveUI.__profileHintPatched = true;
      return true;
    };

    if (!patch()) {
      let tries = 0;
      const h = setInterval(() => {
        if (patch() || ++tries > 40) clearInterval(h);
      }, 50);
    }

    // первый прогон
    setTimeout(update, 150);
  }

  function boot() {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", wire, { once: true });
    } else {
      wire();
    }
  }

  boot();
})();
