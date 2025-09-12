from __future__ import annotations
import time
import os, re, json, ctypes
from typing import Dict, Any, List, Tuple, Optional

import cv2
import numpy as np
from pathlib import Path

from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.vision.utils.colors import mask_for_colors_bgr, biggest_horizontal_band
from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow
from core.logging import console

# локальный счётчик перезапусков именно АФ-цикла (НЕ общий рестарт менеджера)
_RESTART_STREAK = 0
_RESTART_STREAK_LIMIT = 10

# список исключенных целей в рамках одного цикла
excluded_targets: set[str] = set()

USER32 = ctypes.windll.user32


# -------- helpers (чисто низкоуровневые) --------

def _slugify_name_py(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[’`]", "'", s)
    s = re.sub(r"[^a-z0-9а-яё_' -]", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[\s\-']+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def _target_zone_ltrb(win: Dict) -> Tuple[int, int, int, int]:
    """Зона 500x120, верх-центр клиентской области."""
    w, h = int(win["width"]), int(win["height"])
    zw, zh = 500, 120
    l = max(0, (w - zw) // 2)
    t = max(0, 1)
    return (l, t, l + zw, t + zh)

def _target_sys_message_zone_ltrb(win: Dict) -> Tuple[int, int, int, int]:
    """Зона для поиска sys_message."""
    w, h = int(win["width"]), int(win["height"])
    zw, zh = 93, 40
    l = 22
    t = max(0, h - 220 - zh)
    return (l, t, l + zw, t + zh)

def _hp_palettes(server: str) -> Tuple[List[Tuple[int,int,int]], List[Tuple[int,int,int]], int]:
    monster_alive_rgb = [(139, 98, 96), (128, 70, 68), (111, 23, 19), (136, 28, 24), (171, 48, 34)]
    monster_dead_rgb  = [(70, 61, 62), (61, 49, 50), (48, 28, 27), (57, 32, 31), (67, 38, 36)]
    tol = 2
    return monster_alive_rgb, monster_dead_rgb, tol

def _detect_target_bands(win: Dict, server: str):
    """Возвращает (rect_alive, rect_any) в локальных коорд. зоны."""
    l, t, r, b = _target_zone_ltrb(win)
    img = capture_window_region_bgr(win, (l, t, r, b))
    if img is None or img.size == 0:
        return None, None

    alive_rgb, dead_rgb, tol = _hp_palettes(server)
    mask_alive = mask_for_colors_bgr(img, colors_rgb=alive_rgb, tol=tol)
    if dead_rgb:
        mask_dead  = mask_for_colors_bgr(img, colors_rgb=dead_rgb, tol=tol)
        mask_any = np.bitwise_or(mask_alive, mask_dead)
    else:
        mask_any = mask_alive.copy()

    rect_alive = biggest_horizontal_band(mask_alive)
    rect_any   = biggest_horizontal_band(mask_any)
    return rect_alive, rect_any

def _has_target_by_hp(win: Dict, server: str, tries: int = 3, delay_ms: int = 200, should_abort=None) -> bool:
    """Есть ли вообще цель (любой «полосатый» цвет: alive+dead)? С досрочной отменой."""
    for i in range(max(1, tries)):
        if should_abort and should_abort():
            return False
        _, rect_any = _detect_target_bands(win, server)
        if rect_any:
            x, y, w, h = rect_any
            ok = (w >= 40 and h >= 3)
            if ok:
                return True
        time.sleep(delay_ms / 1000.0)
    return False

def _target_alive_by_hp(win: Dict, server: str) -> Optional[bool]:
    """
    Живой, если найдено >= N пикселей из палитры 'alive'.
    False — если меньше; None — если кадр пустой/ошибка.
    """
    l, t, r, b = _target_zone_ltrb(win)
    img = capture_window_region_bgr(win, (l, t, r, b))
    if img is None or img.size == 0:
        return None

    alive_rgb, _, tol = _hp_palettes(server)
    mask_alive = mask_for_colors_bgr(img, colors_rgb=alive_rgb, tol=tol)
    if mask_alive.ndim == 3:
        alive_px = int(np.count_nonzero(np.any(mask_alive > 0, axis=2)))
    else:
        alive_px = int(np.count_nonzero(mask_alive > 0))

    alive = (alive_px >= 5)
    return alive

def _zone_monsters_raw(server: str, zone_id: str):
    try:
        p = os.path.join("core", "engines", "autofarm", "server", server, "zones.json")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        z = data.get(zone_id) or {}
        mons = z.get("monsters")
        return mons if isinstance(mons, dict) else None
    except Exception:
        return None

def _pick_lang_list(raw: dict, lang: str, kind: str) -> List[str]:
    lang = (lang or "eng").lower()
    order = [f"{lang}_{kind}", f"rus_{kind}", f"eng_{kind}"]
    for key in order:
        arr = raw.get(key)
        if isinstance(arr, list) and arr:
            return list(arr)
    arr = raw.get(lang) or raw.get("rus") or raw.get("eng") or []
    return list(arr) if isinstance(arr, list) else []

def _normalize_allowed_slugs(server: str, zone_id: str, lang: str, allowed_slugs: set) -> set:
    raw = _zone_monsters_raw(server, zone_id) or {}
    short_list = _pick_lang_list(raw, lang, "short")
    full_list  = _pick_lang_list(raw, lang, "full")
    L = max(len(short_list), len(full_list))
    full_to_short = {}
    for i in range(L):
        s_name = short_list[i] if i < len(short_list) else (full_list[i] if i < len(full_list) else "")
        f_name = full_list[i]  if i < len(full_list)  else ""
        s_slug = _slugify_name_py(s_name) if s_name else ""
        f_slug = _slugify_name_py(f_name) if f_name else ""
        if f_slug:
            full_to_short[f_slug] = s_slug or f_slug
    normalized = set()
    for sl in (allowed_slugs or set()):
        sl_norm = full_to_short.get(sl, sl)
        normalized.add(sl_norm)
    return normalized

def _zone_monster_display_names(server: str, zone_id: str, lang: str) -> List[str]:
    raw = _zone_monsters_raw(server, zone_id)
    if raw:
        for key in ("rus_short", "eng_short", f"{lang}_short", "rus", "eng", lang):
            arr = raw.get(key)
            if arr:
                out: List[str] = []
                for m in arr:
                    if isinstance(m, dict):
                        out.append(m.get("name") or m.get("slug") or "")
                    else:
                        out.append(str(m))
                return [s for s in out if s]
    try:
        from core.engines.autofarm.zone_repo import get_zone_info
        info = get_zone_info(server, zone_id, lang or "eng")
        mon = (info or {}).get("monsters") or []
        out: List[str] = []
        for m in mon:
            if isinstance(m, dict):
                out.append(m.get("name") or m.get("slug") or "")
            else:
                out.append(str(m))
        return [s for s in out if s]
    except Exception:
        return []

def _monster_template_candidates(server: str, lang: str, short_slug: str, full_slug: str) -> List[str]:
    base = os.path.join("core", "engines", "autofarm", "server", server, "templates", lang, "monsters")
    names_dir = os.path.join(base, "names")
    cand = []
    fs = (full_slug or "").strip()
    ss = (short_slug or "").strip()
    if fs: cand.append(os.path.join(names_dir, f"{fs}.png"))
    if ss and ss != fs: cand.append(os.path.join(names_dir, f"{ss}.png"))
    return cand

def _full_to_short_map(server: str, zone_id: str, lang: str) -> Dict[str, str]:
    raw = _zone_monsters_raw(server, zone_id) or {}
    short_list = _pick_lang_list(raw, lang, "short")
    full_list  = _pick_lang_list(raw, lang, "full")
    L = max(len(short_list), len(full_list))
    m: Dict[str, str] = {}
    for i in range(L):
        s_name = short_list[i] if i < len(short_list) else ""
        f_name = full_list[i]  if i < len(full_list)  else ""
        s_slug = _slugify_name_py(s_name) if s_name else ""
        f_slug = _slugify_name_py(f_name) if f_name else ""
        if f_slug:
            m[f_slug] = s_slug or f_slug
    return m

def _resolve_monster_template(server: str, lang: str, zone_id: str, name: str) -> Optional[str]:
    full_slug  = _slugify_name_py(name)
    short_slug = full_slug
    m = _full_to_short_map(server, zone_id, lang)
    if full_slug in m:
        short_slug = m[full_slug] or full_slug
    for p in _monster_template_candidates(server, lang, short_slug, full_slug):
        if os.path.isfile(p):
            return p
    return None

def _match_template_on_window(win: Dict, tpl_path: str, threshold: float = 0.84) -> Optional[Tuple[int,int,int,int]]:
    if not (tpl_path and os.path.isfile(tpl_path)):
        return None
    tpl = cv2.imread(tpl_path, cv2.IMREAD_GRAYSCALE)
    if tpl is None or tpl.size == 0:
        return None
    th, tw = tpl.shape[:2]
    frame = capture_window_region_bgr(win, (0, 0, int(win["width"]), int(win["height"])))
    if frame is None or frame.size == 0:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, maxVal, _, maxLoc = cv2.minMaxLoc(cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED))
    if float(maxVal) < float(threshold):
        return None
    x, y = int(maxLoc[0]), int(maxLoc[1])
    return (x, y, tw, th)

def _movenclick_client(controller, win: Dict, x: int, y: int, delay_s: float = 0.40) -> None:
    abs_x = int((win.get("x") or 0) + x)
    abs_y = int((win.get("y") or 0) + y)
    controller.move(abs_x, abs_y)
    time.sleep(max(0.0, float(delay_s)))
    try:
        controller._click_left_arduino()
    except AttributeError:
        controller.send("l")


# -------- основной движок цикла --------

def _abort(ctx_base) -> bool:
    f = ctx_base.get("should_abort")
    return bool(f and f())

def _send_chat(ex: FlowOpExecutor, text: str, wait_ms: int = 500) -> bool:
    flow = [
        {"op": "send_message", "layout": "en", "text": text, "wait_ms": 60},
        {"op": "sleep", "ms": max(0, int(wait_ms))}
    ]
    return bool(run_flow(flow, ex))

def _send_target_with_ru_name(ex: FlowOpExecutor, mob_name: str, wait_ms: int = 500) -> bool:
    flow = [
        {"op": "press_enter"},
        {"op": "enter_text", "layout": "en", "text": "/target "},
        {"op": "set_layout", "layout": "ru", "delay_ms": 120},
        {"op": "enter_text", "layout": "ru", "text": mob_name, "wait_ms": 60},
        {"op": "press_enter"},
        {"op": "set_layout", "layout": "en", "delay_ms": 120},
        {"op": "sleep", "ms": max(0, int(wait_ms))}
    ]
    return bool(run_flow(flow, ex))

def _press_key(ex: FlowOpExecutor, key_digit: str) -> bool:
    key_digit = str(key_digit)[:2]
    flow = [{"op": "send_arduino", "cmd": key_digit, "delay_ms": 0}]
    return bool(run_flow(flow, ex))

def _press_esc(ex: FlowOpExecutor) -> bool:
    return bool(run_flow([{"op": "send_arduino", "cmd": "esc", "delay_ms": 0}], ex))

def _has_dot_colors_near_rect(win: Dict, rect: Tuple[int,int,int,int],
                              pad: int = 20, tol: int = 12, min_px: int = 10) -> Tuple[bool,bool,int,int]:
    x, y, w, h = rect
    W, H = int(win["width"]), int(win["height"])
    l = max(0, x - pad); t = max(0, y - pad)
    r = min(W, x + w + pad); b = min(H, y + h + pad)
    if r <= l or b <= t:
        return (False, False, 0, 0)
    roi = capture_window_region_bgr(win, (l,t,r,b))
    if roi is None or roi.size == 0:
        return (False, False, 0, 0)

    def _mask_for_rgb_pool(img_bgr: np.ndarray, pool_rgb: List[Tuple[int,int,int]], tol: int) -> np.ndarray:
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        R, G, B = img_rgb[:,:,0], img_rgb[:,:,1], img_rgb[:,:,2]
        mask = np.zeros(img_rgb.shape[:2], dtype=np.uint8)
        for (r,g,b) in pool_rgb:
            m = (np.abs(R - r) <= tol) & (np.abs(G - g) <= tol) & (np.abs(B - b) <= tol)
            mask |= m.astype(np.uint8)
        return mask

    FRIEND_RGB = [(16,69,131),(21,74,136),(25,77,138),(32,82,143),(32,85,147),(46,99,161)]
    ENEMY_RGB  = [(169,30,0),(183,58,23),(196,69,32),(204,89,58),(221,100,73),(239,138,114)]
    m_friend = _mask_for_rgb_pool(roi, FRIEND_RGB, tol)
    m_enemy  = _mask_for_rgb_pool(roi, ENEMY_RGB,  tol)

    friend_px = int(np.count_nonzero(m_friend))
    enemy_px  = int(np.count_nonzero(m_enemy))
    return (friend_px >= min_px, enemy_px >= min_px, friend_px, enemy_px)

def _template_probe_click(ctx_base: Dict[str, Any], server: str, lang: str, win: Dict, cfg: Dict[str, Any]) -> bool:
    zone_id = (cfg or {}).get("zone") or ""
    if not zone_id:
        return False

    # имена для чата
    def _zone_monster_full_names(server: str, zone_id: str, lang: str) -> List[str]:
        raw = _zone_monsters_raw(server, zone_id) or {}
        for key in (f"{(lang or 'eng').lower()}_full", "eng_full", "rus_full", (lang or 'eng').lower(), "eng", "rus"):
            arr = raw.get(key)
            if isinstance(arr, list) and arr:
                return [str(x) for x in arr if x]
        return []

    full_names = _zone_monster_full_names(server, zone_id, lang)
    if not full_names:
        return False

    allowed_ui = set((cfg or {}).get("monsters") or [])
    if allowed_ui:
        allowed_short = _normalize_allowed_slugs(server, zone_id, lang, allowed_ui)
        full2short = _full_to_short_map(server, zone_id, lang)
        full_names = [nm for nm in full_names if full2short.get(_slugify_name_py(nm), "") in allowed_short]
        if not full_names:
            return False

    controller = ctx_base["controller"]

    for nm in full_names:
        if _abort(ctx_base):
            return False
        if nm in excluded_targets:
            continue
        tpl = _resolve_monster_template(server, lang, zone_id, nm)
        if not tpl:
            continue
        rect = _match_template_on_window(win, tpl, threshold=0.84)
        if not rect:
            continue

        has_friend, has_enemy, fpx, epx = _has_dot_colors_near_rect(win, rect, pad=20, tol=12, min_px=10)
        if has_friend or has_enemy:
            continue

        ctx_base["af_current_target_name"] = nm
        x, y, w, h = rect
        cx = min(max(0, int(x + w / 2)), int(win["width"]) - 1)
        cy = min(max(0, int(y + h + 30)), int(win["height"]) - 1)
        _movenclick_client(controller, win, cx, cy)
        return True

    return False

def _press_silent_cancel(ex: FlowOpExecutor):
    try:
        _send_chat(ex, "/", wait_ms=22)
        _send_chat(ex, "/", wait_ms=22)
        _press_esc(ex)
    except Exception:
        pass

def _check_target_visibility(ex: FlowOpExecutor, server: str, lang: str, win: Dict, zone_id: str) -> bool:
    img_path = os.path.join("core","engines","autofarm","server",server,"templates",lang,"sys_messages","target_unvisible.png")
    target_img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    if target_img is None:
        return False
    l, t, r, b = _target_sys_message_zone_ltrb(win)
    search_zone = capture_window_region_bgr(win, (l, t, r, b))
    if search_zone is None or search_zone.size == 0 or search_zone.ndim != 3:
        return False
    search_zone_gray = cv2.cvtColor(search_zone, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(search_zone_gray, target_img, cv2.TM_CCOEFF_NORMED)
    threshold = 0.40
    return bool(np.any(result >= threshold))


# -------- public entry --------

def start(ctx_base: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """
    Низкоуровневый цикл автофарма для сервера 'boh'.
    ctx_base: {
      server, controller, get_window, get_language, should_abort, ...
    }
    Внешние проверки (enabled/focus/alive/очередь) — на стороне rules.py.
    """
    global _RESTART_STREAK, excluded_targets
    _RESTART_STREAK = 0
    excluded_targets.clear()

    server = (ctx_base["server"] or "boh").lower()
    lang = (ctx_base["get_language"]() or "eng").lower()
    win = ctx_base["get_window"]()
    if not win:
        console.log("[autofarm] окно не найдено")
        return False

    zones = {
        "fullscreen": {"fullscreen": True},
        "target_zone": {
            "left": _target_zone_ltrb(win)[0],
            "top": _target_zone_ltrb(win)[1],
            "width": 400,
            "height": 80,
        }
    }
    ctx = FlowCtx(
        server=server,
        controller=ctx_base["controller"],
        get_window=lambda: win,
        get_language=lambda: lang,
        zones=zones,
        templates={},
        extras={},
    )
    ex = FlowOpExecutor(ctx)  # логгер по умолчанию — console.log

    start_ts = time.time()

    while True:
        if _abort(ctx_base):
            console.log("[autofarm] остановлено пользователем")
            return False

        zone_id = (cfg or {}).get("zone") or ""
        # сперва /targetnext
        _send_chat(ex, "/targetnext", wait_ms=1000)
        if _abort(ctx_base):
            return False

        # проверка HP-полос
        has_any = _has_target_by_hp(win, server, tries=1, delay_ms=150, should_abort=lambda: _abort(ctx_base))
        current_alive = _target_alive_by_hp(win, server)

        if current_alive is None:
            for _ in range(10):
                if _abort(ctx_base):
                    return False
                time.sleep(0.3)
                try:
                    win = ctx_base["get_window"]() or win
                except Exception:
                    pass
                current_alive = _target_alive_by_hp(win, server)
                if current_alive is not None:
                    break
            if current_alive is None:
                current_alive = False  # форсим переход в fallback

        # fallback: пробуем шаблоны, если /targetnext не дал живую цель
        if not (has_any and current_alive) and zone_id:
            if _template_probe_click(ctx_base, server, lang, win, cfg):
                time.sleep(0.35)
                has_any = _has_target_by_hp(win, server, tries=1, delay_ms=150, should_abort=lambda: _abort(ctx_base))
                current_alive = _target_alive_by_hp(win, server)

        if has_any and current_alive:
            console.log("[autofarm] цель получена /targetnext")
            ctx_base["af_current_target_name"] = None

            if _abort(ctx_base):
                return False
            if _attack_cycle(ex, ctx_base, server, lang, win, cfg):
                _RESTART_STREAK = 0
                excluded_targets.clear()
                continue
            else:
                if ctx_base.get("af_unvisible"):
                    ctx_base["af_unvisible"] = False
                    # перебор имён после «цель не видна»
                    if _search_by_names(ex, ctx_base, server, lang, win, cfg):
                        _RESTART_STREAK = 0
                        excluded_targets.clear()
                        continue
                    _RESTART_STREAK += 1
                else:
                    _RESTART_STREAK += 1
        else:
            # перебор имён «в лоб»
            if _search_by_names(ex, ctx_base, server, lang, win, cfg):
                _RESTART_STREAK = 0
                excluded_targets.clear()
                continue
            _RESTART_STREAK += 1

        if _RESTART_STREAK >= _RESTART_STREAK_LIMIT:
            try:
                _send_chat(ex, "/unstuck", wait_ms=1999)
                _press_esc(ex)
            except Exception:
                pass
            console.log(f"[autofarm] {_RESTART_STREAK_LIMIT} неудачных попыток")
            console.log("[autofarm] Перезапускаю весь цикл полностью")
            return False

        time.sleep(0.3)


def _search_by_names(ex: FlowOpExecutor, ctx_base: Dict[str, Any], server: str, lang: str,
                       win: Dict, cfg: Dict[str, Any]) -> bool:
    """Перебор имён зоны (с учётом чёрного списка и UI-фильтра). True если нашли и добили цель."""
    zone_id = (cfg or {}).get("zone") or ""
    names = _zone_monster_display_names(server, zone_id, lang)

    allowed_slugs = set((cfg or {}).get("monsters") or [])
    if allowed_slugs:
        allowed_slugs = _normalize_allowed_slugs(server, zone_id, lang, allowed_slugs)
        names = [n for n in names if _slugify_name_py(n) in allowed_slugs]

    if names and all(nm in excluded_targets for nm in names):
        excluded_targets.clear()

    if not names:
        console.log("[autofarm] нет списка монстров зоны")
        return False

    for nm in names:
        if nm in excluded_targets:
            continue
        if _abort(ctx_base):
            return False
        _send_chat(ex, f"/target {nm}", wait_ms=500) if False else _send_target_with_ru_name(ex, nm, wait_ms=500)
        if _abort(ctx_base):
            return False

        if _has_target_by_hp(win, server, tries=3, delay_ms=250, should_abort=lambda: _abort(ctx_base)):
            alive_state = _target_alive_by_hp(win, server)
            if alive_state is False:
                excluded_targets.add(nm)
                continue

            console.log(f"[autofarm] цель найдена: {nm}")
            ctx_base["af_current_target_name"] = nm
            if _abort(ctx_base):
                return False

            ok = _attack_cycle(ex, ctx_base, server, lang, win, cfg)
            if _abort(ctx_base):
                return False

            if ctx_base.get("af_unvisible"):
                excluded_targets.add(nm)
                ctx_base["af_unvisible"] = False
                continue

            if ok:
                return True
    return False


def _attack_cycle(ex: FlowOpExecutor, ctx_base: Dict[str, Any], server: str, lang: str,
                  win: Dict, cfg: Dict[str, Any]) -> bool:
    """
    Движок атаки: пока цель жива — крутим круги скиллов.
    """
    skills = list((cfg or {}).get("skills") or [])
    if not skills:
        console.log("[autofarm] нет настроенных скиллов")
        return False

    plan: List[Dict[str, Any]] = []
    for s in skills:
        k = str(s.get("key") or "1")
        cd = max(1, int(s.get("cast_ms") or 2000)) / 1000.0
        plan.append({"key": k, "cd": cd, "last": 0.0, "used": False})

    probe_sleep = max((it["cd"] for it in plan), default=0.5)
    start_ts = time.time()
    hard_timeout = 30.0

    def ready(item) -> bool:
        return (time.time() - (item["last"] or 0.0)) >= item["cd"]

    while True:
        if _abort(ctx_base):
            console.log("[autofarm] остановлено пользователем")
            return False

        if (time.time() - start_ts) > hard_timeout:
            console.log("[autofarm] таймаут атаки")
            return False

        alive = _target_alive_by_hp(win, server)
        if alive is False:
            console.log("[autofarm] цель мертва/пропала")
            time.sleep(0.2)
            return True
        if alive is None:
            time.sleep(probe_sleep)
            continue

        candidate = next((it for it in plan if (not it["used"]) and ready(it)), None)
        if not candidate:
            ready_any = [it for it in plan if ready(it)]
            candidate = ready_any[0] if ready_any else None

        if candidate:
            if _press_key(ex, candidate["key"]):
                if _abort(ctx_base):
                    return False
                candidate["last"] = time.time()
                candidate["used"] = True
            time.sleep(probe_sleep)
        else:
            time.sleep(probe_sleep)

        # Завершение круга
        if all(it["used"] for it in plan):
            # Проверка «цель не видна»
            zone_id = (cfg or {}).get("zone") or ""
            if _check_target_visibility(ex, server, lang, win, zone_id):
                _press_silent_cancel(ex)
                ctx_base["af_unvisible"] = True
                return False
