# core/engines/autofarm/server/boh/engine.py
from __future__ import annotations
import time
import importlib
import os, re
from typing import Dict, Any, List, Tuple, Optional

import ctypes
import json
from pathlib import Path
import cv2
import numpy as np

from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.vision.utils.colors import mask_for_colors_bgr, biggest_horizontal_band
from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

# локальный счётчик перезапусков именно АФ-цикла (НЕ общий рестарт менеджера)
_RESTART_STREAK = 0
_RESTART_STREAK_LIMIT = 10

# В глобальной области добавляем список исключенных целей
excluded_targets = set()

# --- helpers ---

def _af_server_root(server: str) -> str:
    return os.path.join("core", "engines", "autofarm", "server", server)

def _slugify_name_py(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[’`]", "'", s)
    s = re.sub(r"[^a-z0-9а-яё_' -]", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[\s\-']+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def _abort(ctx_base) -> bool:
    f = ctx_base.get("should_abort")
    return bool(f and f())

def _capture_window_region(win: Dict, l: int, t: int, r: int, b: int):
    """
    Захват изображения с экрана в указанной области.
    """
    # Вместо чтения из файла, используем захват с экрана
    screen = capture_window_region_bgr(win, (l, t, r, b))
    if screen is None or screen.size == 0:
        print("[AF boh] Ошибка захвата экрана, пустой или некорректный кадр.")
        return None
    return screen


def _target_zone_ltrb(win: Dict) -> Tuple[int, int, int, int]:
    """Зона 500x120, верх-центр клиентской области."""
    w, h = int(win["width"]), int(win["height"])
    zw, zh = 500, 120
    l = max(0, (w - zw) // 2)
    t = max(0, 1)
    return (l, t, l + zw, t + zh)

def _target_sys_message_zone_ltrb(win: Dict) -> Tuple[int, int, int, int]:
    """Зона для поиска sys_message: отступ слева 24px, отступ снизу 240px, размер зоны 100x17."""
    w, h = int(win["width"]), int(win["height"])
    zw, zh = 93, 40
    l = 22
    t = max(0, h - 220 - zh)
    return (l, t, l + zw, t + zh)

def _hp_palettes(server: str) -> Tuple[List[Tuple[int,int,int]], List[Tuple[int,int,int]], int]:
    """
    Возвращает (alive_palette_RGB, dead_palette_RGB, tolerance).
    Палитры заданы в RGB.
    """
    monster_alive_rgb = [(139, 98, 96), (128, 70, 68), (111, 23, 19), (136, 28, 24), (171, 48, 34)]
    monster_dead_rgb  = [(70, 61, 62), (61, 49, 50), (48, 28, 27), (57, 32, 31), (67, 38, 36)]
    tol = 2
    return monster_alive_rgb, monster_dead_rgb, tol


_debug_dump_done = False

def _detect_target_bands(win: Dict, server: str):
    """Возвращает (rect_alive, rect_any) в локальных коорд. зоны."""
    global _debug_dump_done
    l, t, r, b = _target_zone_ltrb(win)
    img = capture_window_region_bgr(win, (l, t, r, b))
    if img is None or img.size == 0:
        print("[AF boh][hp] frame: empty → UNKNOWN")
        return None, None

    alive_rgb, dead_rgb, tol = _hp_palettes(server)
    mask_alive = mask_for_colors_bgr(img, colors_rgb=alive_rgb, tol=tol)

    if dead_rgb:
        mask_dead  = mask_for_colors_bgr(img, colors_rgb=dead_rgb,  tol=tol)
        mask_any = np.bitwise_or(mask_alive, mask_dead)
    else:
        mask_any = mask_alive.copy()

    rect_alive = biggest_horizontal_band(mask_alive)
    rect_any   = biggest_horizontal_band(mask_any)

    if not _debug_dump_done:
        try:
            dbg_dir = os.path.abspath("debug_af_boh")
            os.makedirs(dbg_dir, exist_ok=True)
            cv2.imwrite(os.path.join(dbg_dir, "target_zone_bgr.png"), img)
            cv2.imwrite(os.path.join(dbg_dir, "mask_alive.png"), mask_alive)
            cv2.imwrite(os.path.join(dbg_dir, "mask_any.png"), mask_any)
            print(f"[AF boh][debug] saved target_zone_bgr.png / mask_alive.png / mask_any.png to {dbg_dir}")
        except Exception as e:
            print(f"[AF boh][debug] save failed: {e}")
        _debug_dump_done = True

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
            print(f"[AF boh][target] any-colors → {'YES' if ok else 'NO'} (w={w},h={h}) try={i+1}/{tries}")
            if ok:
                return True
        time.sleep(delay_ms / 1000.0)
    return False

def _target_alive_by_hp(win: Dict, server: str) -> Optional[bool]:
    """
    Живой, если найдено >= 10 пикселей из палитры 'alive'.
    False — если меньше; None — если кадр пустой/ошибка.
    """
    # захватываем ту же целевую зону
    l, t, r, b = _target_zone_ltrb(win)
    img = capture_window_region_bgr(win, (l, t, r, b))
    if img is None or img.size == 0:
        print("[AF boh][hp] frame: empty → UNKNOWN")
        return None

    alive_rgb, _, tol = _hp_palettes(server)
    mask_alive = mask_for_colors_bgr(img, colors_rgb=alive_rgb, tol=tol)

    # считаем количество «живых» пикселей (robust к 1/3 каналам)
    if mask_alive.ndim == 3:
        alive_px = int(np.count_nonzero(np.any(mask_alive > 0, axis=2)))
    else:
        alive_px = int(np.count_nonzero(mask_alive > 0))

    # print(f"[AF boh][hp/alive_px] count={alive_px} (tol={tol})")
    alive = (alive_px >= 5)
    print(f"[AF boh][hp/alive] → {'ALIVE' if alive else 'DEAD'} (>=10px rule)")
    return alive

def _zone_monsters_raw(server: str, zone_id: str):
    try:
        p = os.path.join("core", "engines", "autofarm", "server", server, "zones.json")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        z = data.get(zone_id) or {}
        mons = z.get("monsters")
        return mons if isinstance(mons, dict) else None
    except Exception as e:
        print(f"[AF boh] zones.json read fail: {e}")
        return None

def _pick_lang_list(raw: dict, lang: str, kind: str) -> List[str]:
    """
    kind: 'short' | 'full'
    Берём массив имен в приоритете:
      <lang>_<kind> → rus_<kind> → eng_<kind>
    Для обратной совместимости, если *_short отсутствуют, пробуем просто <lang>/rus/eng.
    """
    lang = (lang or "eng").lower()
    order = [f"{lang}_{kind}", f"rus_{kind}", f"eng_{kind}"]
    for key in order:
        arr = raw.get(key)
        if isinstance(arr, list) and arr:
            return list(arr)
    # fallback: исторические ключи без _short/_full
    if kind == "short":
        arr = raw.get(lang) or raw.get("rus") or raw.get("eng") or []
        return list(arr) if isinstance(arr, list) else []
    if kind == "full":
        arr = raw.get(lang) or raw.get("rus") or raw.get("eng") or []
        return list(arr) if isinstance(arr, list) else []
    return []

def _normalize_allowed_slugs(server: str, zone_id: str, lang: str, allowed_slugs: set) -> set:
    """
    Приводим слуги, пришедшие из UI, к слугам от 'short'.
    Если UI сохранил слуги по 'full', маппим их в соответствующие 'short' по индексу.
    Если длины списков не совпадают, берём по максимуму с безопасными fallbacks.
    """
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
            full_to_short[f_slug] = s_slug or f_slug  # если short пуст, используем full

    normalized = set()
    for sl in (allowed_slugs or set()):
        sl_norm = full_to_short.get(sl, sl)  # если это full-слуг, переведём к short
        normalized.add(sl_norm)
    return normalized

def _zone_monster_display_names(server: str, zone_id: str, lang: str) -> List[str]:
    """
    Имена ДЛЯ ВВОДА В ЧАТ: сначала короткие из zones.json.
    Приоритет: rus_short → eng_short → <lang>_short → rus → eng → <lang>.
    Если raw не доступен, падаем на репозиторий (может быть длинный список).
    """
    # 1) Пробуем взять короткие из zones.json
    raw = _zone_monsters_raw(server, zone_id)
    if raw:
        for key in ("rus_short", "eng_short", f"{lang}_short", "rus", "eng", lang):
            arr = raw.get(key)
            if arr:
                out = []
                for m in arr:
                    if isinstance(m, dict):
                        out.append(m.get("name") or m.get("slug") or "")
                    else:
                        out.append(str(m))
                out = [s for s in out if s]
                print(f"[AF boh] names_for_chat (zones.json {key}): {out}")
                return out

    # 2) Fallback: что вернёт репозиторий (часто длинные)
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
        out = [s for s in out if s]
        print(f"[AF boh] names_for_chat (repo fallback): {out}")
        return out
    except Exception as e:
        print(f"[AF boh] zone names fetch error: {e}")
        return []

# поиск монстров по темплейтам
def _monster_template_candidates(server: str, lang: str, short_slug: str, full_slug: str) -> List[str]:
    base = os.path.join("core", "engines", "autofarm", "server", server, "templates", lang, "monsters")
    names_dir = os.path.join(base, "names")
    cand = []
    fs = (full_slug or "").strip()
    ss = (short_slug or "").strip()
    if fs: cand.append(os.path.join(names_dir, f"{fs}.png"))
    if ss and ss != fs: cand.append(os.path.join(names_dir, f"{ss}.png"))
    # (без legacy-дублей)
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
    """
    name может быть full или short. Возвращает первый существующий путь к шаблону.
    """
    full_slug  = _slugify_name_py(name)
    short_slug = full_slug
    # если пришёл full → переведём к short по карте зоны
    m = _full_to_short_map(server, zone_id, lang)
    if full_slug in m:
        short_slug = m[full_slug] or full_slug

    for p in _monster_template_candidates(server, lang, short_slug, full_slug):
        if os.path.isfile(p):
            return p
    return None

def _zone_monster_full_names(server: str, zone_id: str, lang: str) -> List[str]:
    raw = _zone_monsters_raw(server, zone_id) or {}
    for key in (f"{(lang or 'eng').lower()}_full", "eng_full", "rus_full", (lang or 'eng').lower(), "eng", "rus"):
        arr = raw.get(key)
        if isinstance(arr, list) and arr:
            return [str(x) for x in arr if x]
    return []

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

USER32 = ctypes.windll.user32

def _move_client(win: Dict, x: int, y: int) -> None:
    abs_x = int((win.get("x") or 0) + x)
    abs_y = int((win.get("y") or 0) + y)
    try:
        USER32.SetCursorPos(abs_x, abs_y)
    except Exception as e:
        print(f"[AF boh][move] failed: {e}")

def _movenclick_client(controller, win: Dict, x: int, y: int, delay_s: float = 0.40) -> None:
    """
    Переводим клиентские (x,y) в абсолютные, двигаем курсор и ждём delay_s
    перед кликом. Клик – ТОЛЬКО через Arduino (ReviveController._click_left_arduino).
    """
    abs_x = int((win.get("x") or 0) + x)
    abs_y = int((win.get("y") or 0) + y)

    # при необходимости можно сфокусировать окно (раскомментируй строку ниже)
    # controller.focus(win)

    controller.move(abs_x, abs_y)
    time.sleep(max(0.0, float(delay_s)))
    try:
        controller._click_left_arduino()  # единый допустимый клик
    except AttributeError:
        # на случай, если контроллер иной — запасной путь
        controller.send("l")

# ищем target dots по цветам вокруг ника
# --- DOT by color (friend/enemy) ---
FRIEND_RGB = [
    (16, 69, 131), (21, 74, 136), (25, 77, 138),
    (32, 82, 143), (32, 85, 147), (46, 99, 161),
]
ENEMY_RGB = [
    (169, 30, 0), (183, 58, 23), (196, 69, 32),
    (204, 89, 58), (221, 100, 73), (239, 138, 114),
]

def _mask_for_rgb_pool(img_bgr: np.ndarray, pool_rgb: List[Tuple[int,int,int]], tol: int) -> np.ndarray:
    """Пиксели, попавшие в допуск tol вокруг любого цвета из pool_rgb (RGB!)."""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    R, G, B = img_rgb[:,:,0], img_rgb[:,:,1], img_rgb[:,:,2]
    mask = np.zeros(img_rgb.shape[:2], dtype=np.uint8)
    for (r,g,b) in pool_rgb:
        m = (np.abs(R - r) <= tol) & (np.abs(G - g) <= tol) & (np.abs(B - b) <= tol)
        mask |= m.astype(np.uint8)
    return mask

def _has_dot_colors_near_rect(win: Dict, rect: Tuple[int,int,int,int],
                              pad: int = 20, tol: int = 12, min_px: int = 10) -> Tuple[bool,bool,int,int]:
    """(has_friend, has_enemy, friend_px, enemy_px) в зоне pad вокруг ника."""
    x, y, w, h = rect
    W, H = int(win["width"]), int(win["height"])
    l = max(0, x - pad); t = max(0, y - pad)
    r = min(W, x + w + pad); b = min(H, y + h + pad)
    if r <= l or b <= t:
        print(f"[AF boh][dot-colors] bad roi ltrb=({l},{t},{r},{b})")
        return (False, False, 0, 0)

    roi = capture_window_region_bgr(win, (l,t,r,b))
    if roi is None or roi.size == 0:
        print(f"[AF boh][dot-colors] empty roi ltrb=({l},{t},{r},{b})")
        return (False, False, 0, 0)

    m_friend = _mask_for_rgb_pool(roi, FRIEND_RGB, tol)
    m_enemy  = _mask_for_rgb_pool(roi, ENEMY_RGB,  tol)

    friend_px = int(np.count_nonzero(m_friend))
    enemy_px  = int(np.count_nonzero(m_enemy))

    print(f"[AF boh][dot-colors] roi=({l},{t},{r},{b}) friend_px={friend_px} enemy_px={enemy_px} "
          f"min={min_px} tol={tol}")
    return (friend_px >= min_px, enemy_px >= min_px, friend_px, enemy_px)


def _template_probe_click(ctx_base: Dict[str, Any], server: str, lang: str, win: Dict, cfg: Dict[str, Any]) -> bool:
    """
    Пытается один клик по первому найденному шаблону любого «разрешённого» full-имени.
    НИЧЕГО не проверяет. Возвращает True, если клик выполнен.
    Дальше всё делает уже существующая логика HP/живости.
    """
    zone_id = (cfg or {}).get("zone") or ""
    if not zone_id:
        return False

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
        # ⬇️ не трогаем blacklisted
        if nm in excluded_targets:
            print(f"[AF boh][tpl] skip (blacklisted): {nm}")
            continue

        tpl = _resolve_monster_template(server, lang, zone_id, nm)
        if not tpl:
            continue

        rect = _match_template_on_window(win, tpl, threshold=0.84)
        if not rect:
            continue

        x, y, w, h = rect

        # ⬇️ ЛОГИ и проверка точек по цвету вокруг ника (20px)
        has_friend, has_enemy, fpx, epx = _has_dot_colors_near_rect(
            win, rect, pad=20, tol=12, min_px=10
        )
        print(f"[AF boh][dot-colors] name='{nm}' friend={has_friend}({fpx}) enemy={has_enemy}({epx}) "
              f"rect=({x},{y},{w},{h})")

        if has_friend or has_enemy:
            print(f"[AF boh][tpl] SKIP '{nm}' — dot-color near nickname")
            continue
        # ⬇️ запоминаем кого кликнули по шаблону
        ctx_base["af_current_target_name"] = nm
        cx = min(max(0, int(x + w / 2)), int(win["width"]) - 1)
        cy = min(max(0, int(y + h + 30)), int(win["height"]) - 1)
        _movenclick_client(controller, win, cx, cy)
        return True

    return False

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

# --- основной сценарий ---
def start(ctx_base: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    global _RESTART_STREAK

    server = (ctx_base["server"] or "boh").lower()
    lang = (ctx_base["get_language"]() or "eng").lower()
    win = ctx_base["get_window"]()
    print(f"[AF boh] Window size: {win['width']}x{win['height']}")

    if not win:
        ctx_base["on_status"]("[AF boh] окно не найдено", False)
        return False
    print(f"[AF boh] cycle start; win={win['width']}x{win['height']}")

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
    ex = FlowOpExecutor(ctx, on_status=ctx_base["on_status"])

    last_target_alive = None  # Переменная для хранения состояния цели

    while True:
        if _abort(ctx_base):
            ctx_base["on_status"]("[AF boh] остановлено пользователем", None)
            return False

        zone_id = (cfg or {}).get("zone") or ""
        # всегда сперва /targetnext
        _send_chat(ex, "/targetnext", wait_ms=1000)
        if _abort(ctx_base):
            return False

        # NEW: есть ли вообще цель (полоса любого цвета)
        has_any = _has_target_by_hp(win, server, tries=1, delay_ms=150, should_abort=lambda: _abort(ctx_base))
        current_alive = _target_alive_by_hp(win, server)

        if current_alive is None:
            has_any = _has_target_by_hp(win, server, tries=1, delay_ms=150, should_abort=lambda: _abort(ctx_base))
            if has_any and not current_alive:
                # возможная задержка обновления HP-полосы — короткая перепроверка
                time.sleep(0.2)
                current_alive = _target_alive_by_hp(win, server)

            print(f"[AF boh] /targetnext → has_any={has_any} alive={current_alive}")
            # захват дал пустой кадр → не выходим, а делаем несколько повторов
            for i in range(10):
                time.sleep(0.3)
                # обновим info окна на случай его смещения/ресайза
                try:
                    win = ctx_base["get_window"]() or win
                except Exception:
                    pass
                current_alive = _target_alive_by_hp(win, server)
                if current_alive is not None:
                    print(f"[AF boh][retry] кадр ок на попытке {i + 1}/10")
                    break
            if current_alive is None:
                # пропускаем тик, главный цикл продолжается
                print("[AF boh][warn] кадр пустой → пропускаю тик")
                current_alive = False  # форсим переход в ветку перебора имён

        print(f"[AF boh] /targetnext → has_any={has_any} alive={current_alive}")

        # ⬇️ ФОЛЛБЭК: если /targetnext не дал живую цель — пробуем шаблоны
        if not (has_any and current_alive) and zone_id:
            print("[AF boh][tpl] fallback: probing templates…")
            if _template_probe_click(ctx_base, server, lang, win, cfg):
                time.sleep(0.35)
                has_any = _has_target_by_hp(
                    win, server, tries=1, delay_ms=150, should_abort=lambda: _abort(ctx_base)
                )
                current_alive = _target_alive_by_hp(win, server)
                print(f"[AF boh][tpl] after fallback → has_any={has_any} alive={current_alive}")

        if has_any and current_alive:
            ctx_base["on_status"]("[AF boh] цель получена /targetnext", True)
            if _abort(ctx_base):
                return False
            # цель взяли не по имени
            ctx_base["af_current_target_name"] = None
            ok = _attack_cycle(ex, ctx_base, server, lang, win, cfg)
            if _abort(ctx_base):
                return False
            if ok:
                _RESTART_STREAK = 0
                print("[AF boh] цель добита → новый поиск", flush=True)
                # очистить исключённые цели после убийства
                excluded_targets.clear()
                continue
            else:
                # если в бою словили "цель не видна" — переходим к перебору имён
                if ctx_base.get("af_unvisible"):
                    print("[AF boh] 'цель не видна' после /targetnext → начинаем перебор имён")
                    ctx_base["af_unvisible"] = False
                    zone_id = (cfg or {}).get("zone") or ""
                    names = _zone_monster_display_names(server, zone_id, lang)

                    allowed_slugs = set((cfg or {}).get("monsters") or [])
                    if allowed_slugs:
                        zone_id = (cfg or {}).get("zone") or ""
                        allowed_slugs = _normalize_allowed_slugs(server, zone_id, lang, allowed_slugs)
                        names = [n for n in names if _slugify_name_py(n) in allowed_slugs]

                    if names and all(nm in excluded_targets for nm in names):
                        print("[AF boh] все цели в blacklist → очищаю список")
                        excluded_targets.clear()

                    if not names:
                        ctx_base["on_status"]("[AF boh] нет списка монстров зоны", False)
                        return False

                    found = False
                    for nm in names:
                        if nm in excluded_targets:
                            print(f"[AF boh] skip (blacklisted): {nm}")
                            continue
                        if _abort(ctx_base):
                            return False
                        _send_target_with_ru_name(ex, nm, wait_ms=500)
                        if _abort(ctx_base):
                            return False
                        if _has_target_by_hp(win, server, tries=3, delay_ms=250, should_abort=lambda: _abort(ctx_base)):
                            ctx_base["on_status"](f"[AF boh] цель найдена (fallback): {nm}", True)
                            ctx_base["af_current_target_name"] = nm
                            ok2 = _attack_cycle(ex, ctx_base, server, lang, win, cfg)
                            if _abort(ctx_base):
                                return False

                            # если снова "цель не видна" — чёрный список и дальше
                            if ctx_base.get("af_unvisible"):
                                excluded_targets.add(nm)
                                ctx_base["af_unvisible"] = False
                                print(f"[AF boh] '{nm}' невидима → в чёрный список; ищем дальше")
                                continue

                            if ok2:
                                _RESTART_STREAK = 0
                                excluded_targets.clear()
                                found = True
                                break

                    if found:
                        continue
                    _RESTART_STREAK += 1
                    ctx_base["on_status"](f"[AF boh] цель не найдена (fallback), рестарт цикла #{_RESTART_STREAK}", None)
                else:
                    _RESTART_STREAK += 1
        else:
            # /targetnext не дал живую цель → перебираем имена
            zone_id = (cfg or {}).get("zone") or ""
            names = _zone_monster_display_names(server, zone_id, lang)

            allowed_slugs = set((cfg or {}).get("monsters") or [])
            if allowed_slugs:
                zone_id = (cfg or {}).get("zone") or ""
                allowed_slugs = _normalize_allowed_slugs(server, zone_id, lang, allowed_slugs)
                names = [n for n in names if _slugify_name_py(n) in allowed_slugs]

            if names and all(nm in excluded_targets for nm in names):
                print("[AF boh] все цели в blacklist → очищаю список")
                excluded_targets.clear()

            if not names:
                ctx_base["on_status"]("[AF boh] нет списка монстров зоны", False)
                return False

            found = False
            for nm in names:
                if nm in excluded_targets:
                    print(f"[AF boh] Пропускаем цель (blacklisted): {nm}")
                    continue

                if _abort(ctx_base):
                    return False
                _send_target_with_ru_name(ex, nm, wait_ms=500)
                if _abort(ctx_base):
                    return False
                if _has_target_by_hp(win, server, tries=3, delay_ms=250, should_abort=lambda: _abort(ctx_base)):
                    # NEW: если цель мёртвая (труп) → в чёрный список и к следующему имени
                    alive_state = _target_alive_by_hp(win, server)
                    if alive_state is False:
                        excluded_targets.add(nm)
                        print(f"[AF boh] '{nm}' мёртв → blacklist до следующего убийства")
                        continue

                    found = True
                    ctx_base["on_status"](f"[AF boh] цель найдена: {nm}", True)
                    ctx_base["af_current_target_name"] = nm
                    if _abort(ctx_base):
                        return False
                    ok = _attack_cycle(ex, ctx_base, server, lang, win, cfg)
                    if _abort(ctx_base):
                        return False

                    # если в бою поймали "цель не видна" — заносим имя в чёрный список и пробуем следующего
                    if ctx_base.get("af_unvisible"):
                        excluded_targets.add(nm)
                        ctx_base["af_unvisible"] = False
                        print(f"[AF boh] '{nm}' невидима → в чёрный список; ищем дальше")
                        found = False
                        continue

                    if ok:
                        _RESTART_STREAK = 0
                        excluded_targets.clear()
                        found = False  # сразу уходим на новый круг поиска
                        break

            if found:
                continue  # на всякий

            _RESTART_STREAK += 1
            ctx_base["on_status"](f"[AF boh] цель не найдена, рестарт цикла #{_RESTART_STREAK}", None)

        if _RESTART_STREAK >= _RESTART_STREAK_LIMIT:
            try:
                _send_chat(ex, "/unstuck", wait_ms=2222)
                _press_esc(ex)
                print("[AF boh] streak лимит → отправлен /unstuck")
            except Exception as e:
                print(f"[AF boh] /unstuck failed: {e}")
            ctx_base["on_status"]("[AF boh] 10 безрезультатных циклов → запустить ПОЛНЫЙ ЦИКЛ (как после смерти)", False)
            return False

        time.sleep(0.3)



def _attack_cycle(ex: FlowOpExecutor, ctx_base: Dict[str, Any], server: str, lang: str,
                  win: Dict, cfg: Dict[str, Any]) -> bool:
    """
    Движок атаки: пока цель жива — крутим круги скиллов.
    """
    skills = list((cfg or {}).get("skills") or [])
    if not skills:
        ctx_base["on_status"]("[AF boh] нет настроенных скиллов", False)
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
            ctx_base["on_status"]("[AF boh] остановлено пользователем", None)
            return False

        if (time.time() - start_ts) > hard_timeout:
            ctx_base["on_status"]("[AF boh] таймаут атаки", False)
            print("[AF boh] таймаут атаки")
            return False

        alive = _target_alive_by_hp(win, server)
        if alive is False:
            ctx_base["on_status"]("[AF boh] цель мертва/пропала", True)
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

        # Завершение круга скиллов
        if all(it["used"] for it in plan):
            print("[AF boh] круг скиллов завершён → новый круг", flush=True)

            # Проверка на видимость новой цели
            zone_id = (cfg or {}).get("zone") or ""
            if _check_target_visibility(ex, server, lang, win, zone_id):
                _send_chat(ex, "/", wait_ms=22)
                _send_chat(ex, "/", wait_ms=22)
                _press_esc(ex)
                # сигнал наружу: цель невидима → нужно сменить цель
                ctx_base["af_unvisible"] = True
                print("[AF boh] цель не видна → выходим из attack_cycle для смены цели")
                return False


# Функция для проверки видимости цели после первой атаки
def _check_target_visibility(ex: FlowOpExecutor, server: str, lang: str, win: Dict, zone_id: str) -> bool:
    image_path = os.path.join("core","engines","autofarm","server",server,"templates",lang,"sys_messages","target_unvisible.png")
    """
    Проверяем видимость цели после первой атаки.
    Теперь используем OpenCV для поиска изображения, а не match_in_zone.
    """

    # Загружаем изображение для поиска
    target_img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if target_img is None:
        print(f"[AF boh] Ошибка загрузки изображения {image_path}")
        return False  # Если изображение не найдено, цель видна

    # Получаем зону для поиска sys_message
    l, t, r, b = _target_sys_message_zone_ltrb(win)

    # Используем новую функцию для захвата экрана
    search_zone = _capture_window_region(win, l, t, r, b)

    if search_zone is None or search_zone.size == 0:
        print(f"[AF boh] Ошибка захвата экрана в зоне {l},{t},{r},{b}")
        return False  # Если не удалось захватить экран, цель видна

    # Проверка на корректную размерность массива (оно должно быть 2D или 3D)
    if search_zone.ndim != 3:
        print(f"[AF boh] Ошибка: захваченный экран имеет неправильную размерность (ndim={search_zone.ndim})")
        return False  # Если размерность неправильная, цель видна

    # Сохраняем захваченную область для дебага
    # try:
    #     dbg_dir = os.path.abspath("debug_af_boh")
    #     os.makedirs(dbg_dir, exist_ok=True)
    #     debug_image_path = os.path.join(dbg_dir, "captured_zone.png")
    #     cv2.imwrite(debug_image_path, search_zone)
    #     print(f"[AF boh][debug] saved captured zone to {debug_image_path}")
    # except Exception as e:
    #     print(f"[AF boh][debug] failed to save captured zone: {e}")

    # Преобразуем в оттенки серого для удобства поиска
    search_zone_gray = cv2.cvtColor(search_zone, cv2.COLOR_BGR2GRAY)

    # Используем метод сравнения шаблонов OpenCV (например, `cv2.matchTemplate`)
    result = cv2.matchTemplate(search_zone_gray, target_img, cv2.TM_CCOEFF_NORMED)

    # Пороговое значение для нахождения шаблона
    threshold = 0.40
    if np.any(result >= threshold):
        print(f"[AF boh] Цель не видна, отсылаем /s команду.")
        return True  # Если шаблон найден, цель не видна

    # Если совпадение не найдено, цель видна
    print(f"[AF boh] Цель видна — продолжаем бой.")
    return False
