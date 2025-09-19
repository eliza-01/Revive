# app/launcher/prefs.py
from __future__ import annotations
import json
import os
from typing import Any, Dict, List

from core.state.pool import pool_get
from core.logging import console

# ВАЛИДАЦИЯ/ДАННЫЕ из манифеста
from core.config.servers import (
    list_servers,
    get_languages,
    get_section_flags,
    get_buff_methods,
    get_buff_modes,
    get_teleport_methods,
    get_teleport_categories,
    get_teleport_locations,
    get_autofarm_modes,
)

# ------------------------------------------------------
# Где храним prefs: рядом с записями (как ты просил)
# ~/.revive/records/prefs.json
# ------------------------------------------------------
def _prefs_dir() -> str:
    base = os.path.expanduser("~/.revive/records")
    os.makedirs(base, exist_ok=True)
    return base

def _prefs_path() -> str:
    return os.path.join(_prefs_dir(), "prefs.json")


# Что сохраняем (white-list путей пула)
PREF_KEYS: List[str] = [
    "config.server", "config.language", "config.app_language",
    "pipeline.order",
    "features.respawn.enabled", "features.respawn.wait_enabled", "features.respawn.wait_seconds",
    "features.macros.enabled", "features.macros.repeat_enabled", "features.macros.rows",
    "features.buff.enabled", "features.buff.method", "features.buff.mode", "features.buff.checker",
    "features.teleport.enabled", "features.teleport.method", "features.teleport.category", "features.teleport.location",
    "features.autofarm.enabled", "features.autofarm.mode", "features.autofarm.config",
    "features.record.enabled", "features.record.current_record",   # если решишь — добавь
]

def load_prefs() -> Dict[str, Any]:
    path = _prefs_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
            if not isinstance(data, dict):
                console.log(f"[prefs] file exists but not a dict: {path}")
                return {}
            console.log(f"[prefs] loaded {len(data)} keys from {path}")
            return data
    except FileNotFoundError:
        console.log(f"[prefs] not found -> {path} (using manifest defaults)")
        return {}
    except Exception as e:
        console.log(f"[prefs] load error: {e} -> {path}")
        return {}

def save_prefs(state: Dict[str, Any]) -> None:
    out: Dict[str, Any] = {}
    for path in PREF_KEYS:
        val = pool_get(state, path, None)
        if val is not None:
            out[path] = val
    try:
        with open(_prefs_path(), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        console.log(f"[prefs] saved -> {_prefs_path()}")
    except Exception as e:
        console.log(f"[prefs] save error: {e}")


# ------------------------------------------------------
# Резолв значений: prefs → (валидируем) → fallback к манифесту
# Возвращаем то, что стоит применить в пул.
# ------------------------------------------------------
ALLOWED_STEPS_DEFAULT = ["respawn", "buff", "teleport", "macros", "record", "autofarm"]

def _validate_order(order_any: Any, allowed: List[str]) -> List[str]:
    if not isinstance(order_any, list):
        return ALLOWED_STEPS_DEFAULT[:]  # по умолчанию
    order = [str(x).lower().strip() for x in order_any if str(x).lower().strip() in allowed]
    # минимальная страховка: без пустого списка
    return order or ALLOWED_STEPS_DEFAULT[:]
def _norm_macros_rows(rows_any: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in (rows_any or []):
        r = r or {}
        key = str(r.get("key", "1"))[:1]
        if key not in "0123456789":
            key = "1"
        try:
            cast_s = int(float(r.get("cast_s", 0)))
        except Exception:
            cast_s = 0
        try:
            repeat_s = int(float(r.get("repeat_s", 0)))
        except Exception:
            repeat_s = 0
        out.append({
            "key": key,
            "cast_s": max(0, cast_s),
            "repeat_s": max(0, repeat_s),
        })
    return out

def _norm_autofarm_cfg(cfg_any: Any) -> Dict[str, Any]:
    cfg = dict(cfg_any or {})
    prof = str(cfg.get("profession", ""))

    def _norm_key(key_any: Any) -> str:
        k = str(key_any or "1")[:1]
        return k if k in "0123456789" else "1"

    skills: List[Dict[str, Any]] = []
    for s_any in (cfg.get("skills") or []):
        s = dict(s_any or {})
        key = _norm_key(s.get("key"))
        slug = str(s.get("slug", ""))

        # cast_ms
        try:
            cast_ms = int(float(s.get("cast_ms", 850)))
        except Exception:
            cast_ms = 850
        cast_ms = max(0, cast_ms)

        # cooldown_ms: принимаем разные ключи, фолбэк — cast_ms
        raw_cd = s.get("cooldown_ms", s.get("cd_ms", s.get("cooldown", s.get("cd", cast_ms))))
        try:
            cd_ms = int(float(raw_cd))
        except Exception:
            cd_ms = cast_ms

        skills.append({
            "key": key,
            "slug": slug,
            "cast_ms": max(0, cast_ms),
            "cooldown_ms": max(0, cd_ms),
        })

    zone = str(cfg.get("zone", ""))
    mons = [str(x) for x in (cfg.get("monsters") or [])]
    return {"profession": prof, "skills": skills, "zone": zone, "monsters": mons}

def resolve_initial_with_prefs(prefs: Dict[str, Any]) -> Dict[str, Any]:
    resolved: Dict[str, Any] = {}

    # --- server ---
    servers = list_servers()
    if not servers:
        raise RuntimeError("No servers in manifest")
    pref_server = str(prefs.get("config.server") or "")
    server = pref_server if pref_server in servers else servers[0]
    resolved["config.server"] = server

    if pref_server and pref_server not in servers:
        console.log(f"[prefs] server '{pref_server}' not in manifest; fallback -> '{servers[0]}'")

    # --- language ---
    langs = get_languages(server)
    if not langs:
        raise RuntimeError(f"No languages for server '{server}'")
    pref_lang = str(prefs.get("config.language") or "")
    l2_lang = pref_lang if pref_lang in langs else langs[0]
    resolved["config.language"] = l2_lang
    # язык приложения — можно приравнять к UI-языку (если хочешь — сохрани отдельно)
    app_lang = str(prefs.get("config.app_language") or l2_lang)
    resolved["config.app_language"] = app_lang

    if pref_lang and pref_lang not in langs:
        console.log(f"[prefs] language '{pref_lang}' not in {langs}; fallback -> '{langs[0]}'")

    # --- UI sections (зависит от сервера) ---
    resolved["ui.sections"] = get_section_flags(server)

    # --- pipeline ---
    allowed_steps = ALLOWED_STEPS_DEFAULT[:]  # при желании можно сузить по section-флагам
    pref_order = prefs.get("pipeline.order")
    order = _validate_order(pref_order, allowed_steps)
    resolved["pipeline.allowed"] = allowed_steps
    resolved["pipeline.order"] = order

    if isinstance(prefs.get("pipeline.order"), list):
        lost = [x for x in prefs["pipeline.order"] if str(x).lower() not in allowed_steps]
        if lost:
            console.log(f"[prefs] pipeline.order filtered out: {lost}")

    # --- buff ---
    buff_methods = get_buff_methods(server)
    buff_modes = get_buff_modes(server)

    pref_buff_method = str(prefs.get("features.buff.method") or "")
    pref_buff_mode   = str(prefs.get("features.buff.mode") or "")
    resolved["features.buff.methods"] = buff_methods
    resolved["features.buff.modes"] = buff_modes
    resolved["features.buff.method"] = pref_buff_method if pref_buff_method in buff_methods else (buff_methods[0] if buff_methods else "")
    resolved["features.buff.mode"]   = pref_buff_mode   if pref_buff_mode   in buff_modes   else (buff_modes[0]   if buff_modes   else "")

    if pref_buff_method and pref_buff_method not in buff_methods:
        console.log(f"[prefs] buff.method '{pref_buff_method}' not in {buff_methods} -> fallback")
    if pref_buff_mode and pref_buff_mode not in buff_modes:
        console.log(f"[prefs] buff.mode '{pref_buff_mode}' not in {buff_modes} -> fallback")

    # --- teleport ---
    tp_methods = get_teleport_methods(server)
    tp_cats    = get_teleport_categories(server)

    pref_tp_method   = str(prefs.get("features.teleport.method") or "")
    pref_tp_category = str(prefs.get("features.teleport.category") or "")
    category = pref_tp_category if pref_tp_category in tp_cats else (tp_cats[0] if tp_cats else "")
    resolved["features.teleport.methods"]  = tp_methods
    resolved["features.teleport.method"]   = pref_tp_method if pref_tp_method in tp_methods else (tp_methods[0] if tp_methods else "")
    resolved["features.teleport.category"] = category

    if pref_tp_method and pref_tp_method not in tp_methods:
        console.log(f"[prefs] teleport.method '{pref_tp_method}' not in {tp_methods} -> fallback")
    if pref_tp_category and pref_tp_category not in tp_cats:
        console.log(f"[prefs] teleport.category '{pref_tp_category}' not in {tp_cats} -> fallback")

    # location валидируем в контексте выбранной категории
    locs = get_teleport_locations(server, category) if category else []
    pref_tp_loc = str(prefs.get("features.teleport.location") or "")
    resolved["features.teleport.location"] = pref_tp_loc if pref_tp_loc in locs else (locs[0] if locs else "")
    if pref_tp_loc and pref_tp_loc not in locs:
        console.log(f"[prefs] teleport.location '{pref_tp_loc}' not in {locs} -> fallback")

    # --- autofarm (modes + выбранный mode) ---
    af_modes = get_autofarm_modes(server)
    resolved["features.autofarm.modes"] = af_modes

    pref_af_mode = str(prefs.get("features.autofarm.mode") or "")
    af_mode = pref_af_mode if pref_af_mode in af_modes else (af_modes[0] if af_modes else "")
    resolved["features.autofarm.mode"] = af_mode
    if pref_af_mode and pref_af_mode not in af_modes:
        console.log(f"[prefs] autofarm.mode '{pref_af_mode}' not in {af_modes} -> fallback")

    # --- enabled-флаги, которые хотим помнить ---
    # (если их не было — не пишем, чтобы оставить дефолты ensure_pool)
    for path in [
        "features.respawn.enabled",
        "features.respawn.wait_enabled",
        "features.respawn.wait_seconds",
        "features.macros.enabled",
        "features.macros.repeat_enabled",
        "features.macros.rows",
        "features.buff.enabled",
        "features.buff.checker",
        "features.teleport.enabled",
        "features.autofarm.enabled",
        "features.autofarm.config",
        "features.record.enabled",
        "features.record.current_record",
    ]:
        if path in prefs:
            resolved[path] = prefs[path]

    # Нормализация макросов и автофарма из prefs
    if "features.macros.rows" in prefs:
        resolved["features.macros.rows"] = _norm_macros_rows(prefs["features.macros.rows"])

    if "features.autofarm.config" in prefs:
        resolved["features.autofarm.config"] = _norm_autofarm_cfg(prefs["features.autofarm.config"])

    # (опционально для наглядности — короткий лог)
    try:
        console.log(
            "[prefs] resolved snapshot: "
            f"server={resolved.get('config.server')}, "
            f"lang={resolved.get('config.language')}, "
            f"tp={resolved.get('features.teleport.category', '')}/{resolved.get('features.teleport.location', '')}, "
            f"buff={resolved.get('features.buff.method', '')}/{resolved.get('features.buff.mode', '')}, "
            f"autofarm_mode={resolved.get('features.autofarm.mode', '')}, "
            f"macros_rows={len(resolved.get('features.macros.rows', []))}, "
            f"autofarm={'on' if resolved.get('features.autofarm.enabled') else 'off'}"
        )
    except Exception:
        pass

    return resolved
