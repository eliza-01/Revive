# core/engines/dashboard/server/boh/buffer/rules.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import time
import os

import cv2
import numpy as np

from core.logging import console
from core.state.pool import pool_get
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

# Общие данные по зонам/шаблонам
from core.engines.dashboard.server.boh.dashboard_data import TEMPLATES

# Серверный резолвер путей до png (ВАЖНО: должен уметь резолвить вложенные подпапки)
from core.engines.dashboard.server.boh.templates.resolver import resolve as tpl_resolve


# ---------------------- low-level helpers ----------------------

def _focused_now(state: Dict[str, Any]) -> Optional[bool]:
    try:
        v = pool_get(state, "focus.is_focused", None)
        return bool(v) if isinstance(v, bool) else None
    except Exception:
        return None


def _win_ok(win: Optional[Dict]) -> bool:
    return bool(win and all(k in win for k in ("x", "y", "width", "height")))


def _hud_ok(msg: str):   console.hud("ok",   msg)
def _hud_err(msg: str):  console.hud("err",  msg)
def _hud_succ(msg: str): console.hud("succ", msg)


def _resolve_template(lang: str, key: str) -> Optional[str]:
    """
    Берём parts из TEMPLATES[key] и резолвим через server resolver.
    TEMPLATES[key] ожидается в формате: ["<lang>", "dir1", "dir2", "file.png"].
    """
    parts = TEMPLATES.get(key)
    if not parts:
        return None
    p = tpl_resolve(lang, *parts)
    return p if (p and os.path.isfile(p)) else None


def _frame_full(win: Dict) -> Optional[np.ndarray]:
    """Снимок всей клиентской области окна (BGR)."""
    l, t, r, b = 0, 0, int(win["width"]), int(win["height"])
    return capture_window_region_bgr(win, (l, t, r, b))


def _match_template(win: Dict, img_path: str, thr: float = 0.87) -> Optional[Tuple[int, int, int, int]]:
    """
    OpenCV matchTemplate по всему окну.
    Возвращает (x, y, w, h) найденного шаблона в координатах окна либо None.
    """
    try:
        if not (win and img_path and os.path.isfile(img_path)):
            return None
        tpl = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if tpl is None or tpl.size == 0:
            return None
        th, tw = tpl.shape[:2]
        frame = _frame_full(win)
        if frame is None or frame.size == 0:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, maxVal, _, maxLoc = cv2.minMaxLoc(res)
        if float(maxVal) < float(thr):
            return None
        x, y = int(maxLoc[0]), int(maxLoc[1])
        return (x, y, tw, th)
    except Exception:
        return None


def _visible(win: Dict, img_path: Optional[str], thr: float = 0.87) -> bool:
    return bool(img_path and _match_template(win, img_path, thr) is not None)


def _click_center(controller, win: Dict, rect: Tuple[int, int, int, int], delay_s: float = 0.08):
    x, y, w, h = rect
    cx = int(x + w / 2)
    cy = int(y + h / 2)
    # переводим из координат клиента окна в абсолютные координаты экрана
    abs_x = int((win.get("x") or 0) + cx)
    abs_y = int((win.get("y") or 0) + cy)
    try:
        controller.send(f"click:{abs_x},{abs_y}")
    except Exception:
        pass
    if delay_s > 0:
        time.sleep(delay_s)


def _click_by_template(controller, win: Dict, img_path: str, thr: float = 0.87, delay_s: float = 0.08) -> bool:
    rect = _match_template(win, img_path, thr)
    if not rect:
        return False
    _click_center(controller, win, rect, delay_s=delay_s)
    return True


def _ensure_alt_b(controller, open_state: bool, win: Dict, lang: str, timeout_s: float = 2.0) -> bool:
    """
    Привести дашборд к нужному состоянию (open_state=True → открыт, False → закрыт),
    используя Alt+B и проверяя по шаблону 'dashboard_init'.
    """
    init_png = _resolve_template(lang, "dashboard_init")
    if not init_png:
        _hud_err("[dashboard] нет шаблона dashboard_init")
        return False

    # уже в нужном состоянии?
    vis = _visible(win, init_png, thr=0.87)
    if (open_state and vis) or ((not open_state) and (not vis)):
        return True

    # один тоггл Alt+B и ждём подтверждения
    try:
        controller.send("altB")
    except Exception:
        pass

    end = time.time() + max(0.2, float(timeout_s))
    while time.time() < end:
        if _visible(win, init_png, thr=0.87) == open_state:
            return True
        time.sleep(0.05)
    return False


def _unlock_if_locked(controller, win: Dict, lang: str, timeout_s: float = 12.0, probe_interval_s: float = 1.0) -> bool:
    """
    Если на экране виден один из 'dashboard_is_locked_*' — периодически жмём 'l'
    пока баннер не исчезнет, либо по таймауту.
    """
    lock1 = _resolve_template(lang, "dashboard_is_locked_1")
    lock2 = _resolve_template(lang, "dashboard_is_locked_2")
    if not (lock1 or lock2):
        return True  # нечего проверять

    start = time.time()
    next_probe = 0.0
    while (time.time() - start) < timeout_s:
        vis1 = _visible(win, lock1, thr=0.82) if lock1 else False
        vis2 = _visible(win, lock2, thr=0.82) if lock2 else False
        if not (vis1 or vis2):
            return True
        now = time.time()
        if now >= next_probe:
            try:
                controller.send("l")
            except Exception:
                pass
            next_probe = now + max(0.2, probe_interval_s)
        time.sleep(0.05)
    console.log("[dashboard] lock banner still visible")
    return False


# ---------------------- public entry (pipeline step) ----------------------

def run_step(
    state: Dict[str, Any],
    ps_adapter,
    controller,
    snap,  # core.orchestrators.snapshot.Snapshot
    helpers: Dict[str, Any],
) -> tuple[bool, bool]:
    """
    Выполняет шаг 'buff' через dashboard/buffer:
      1) Сброс: если дэш уже открыт — закрываем Alt+B.
      2) Открываем дэш Alt+B и убеждаемся, что открыт (dashboard_init).
      3) Анлок, если висит баннер блокировки.
      4) Открываем вкладку баффера.
      5) Жмём выбранный профиль (profile|mage|fighter|archer*).
    Возвращает (ok, advance).
    """

    # окно и фокус
    win = helpers.get("get_window", lambda: None)()  # type: ignore
    if not _win_ok(win):
        return False, False

    f = _focused_now(state)
    if f is False:
        console.hud("ok", "[dashboard] пауза: окно без фокуса — жду")
        return False, False

    # язык интерфейса L2
    lang = (helpers.get("get_language", lambda: "rus")() or "rus").lower()  # type: ignore

    # ---- 1) Сброс: если открыт — закрываем Alt+B
    if not _ensure_alt_b(controller, open_state=False, win=win, lang=lang, timeout_s=1.5):
        # даже если был закрыт — это не крит, продолжаем
        pass

    # ---- 2) Открываем и проверяем
    if not _ensure_alt_b(controller, open_state=True, win=win, lang=lang, timeout_s=2.5):
        _hud_err("[dashboard] Alt+B: не удалось открыть")
        return False, False
    _hud_ok("[dashboard] Alt+B открыт")

    # ---- 3) Анлок при необходимости
    if not _unlock_if_locked(controller, win, lang, timeout_s=12.0, probe_interval_s=1.0):
        _hud_err("[dashboard] заблокирован (unlock timeout)")
        # Закрыть дэш перед выходом
        _ensure_alt_b(controller, open_state=False, win=win, lang=lang, timeout_s=1.0)
        return False, False

    # ---- 4) Открыть вкладку баффера
    btn_path = _resolve_template(lang, "dashboard_buffer_button")
    if not btn_path:
        _hud_err("[dashboard] нет шаблона кнопки баффера")
        _ensure_alt_b(controller, open_state=False, win=win, lang=lang, timeout_s=1.0)
        return False, False

    if not _click_by_template(controller, win, btn_path, thr=0.85, delay_s=0.12):
        _hud_err("[dashboard] не удалось нажать кнопку баффера")
        _ensure_alt_b(controller, open_state=False, win=win, lang=lang, timeout_s=1.0)
        return False, False

    # ожидаем экран баффера
    buf_init = _resolve_template(lang, "dashboard_buffer_init")
    if not buf_init:
        _hud_err("[dashboard] нет шаблона dashboard_buffer_init")
        _ensure_alt_b(controller, open_state=False, win=win, lang=lang, timeout_s=1.0)
        return False, False

    end = time.time() + 2.0
    opened = False
    while time.time() < end:
        if _visible(win, buf_init, thr=0.85):
            opened = True
            break
        time.sleep(0.05)

    if not opened:
        _hud_err("[dashboard] баффер не открылся")
        _ensure_alt_b(controller, open_state=False, win=win, lang=lang, timeout_s=1.0)
        return False, False

    _hud_ok("[dashboard] баффер открыт")

    # ---- 5) Нажать профиль в соответствии с режимом
    mode = (pool_get(state, "features.buff.mode", "") or "").strip().lower() or "profile"
    key_by_mode = {
        "profile": "dashboard_buffer_profile",
        "fighter": "dashboard_buffer_fighter",
        "mage":    "dashboard_buffer_mage",
        # "archer": шаблон может отсутствовать — обработаем ниже
        "archer":  "dashboard_buffer_archer",
    }
    tpl_key = key_by_mode.get(mode, "dashboard_buffer_profile")
    tpl_path = _resolve_template(lang, tpl_key)

    # Если конкретного режима нет (например, archer), откатимся на profile
    if not tpl_path:
        console.log(f"[dashboard/buffer] template for mode '{mode}' missing → fallback to 'profile'")
        tpl_path = _resolve_template(lang, "dashboard_buffer_profile")

    if not tpl_path:
        _hud_err("[dashboard] нет шаблона профиля баффа")
        _ensure_alt_b(controller, open_state=False, win=win, lang=lang, timeout_s=1.0)
        return False, False

    if not _click_by_template(controller, win, tpl_path, thr=0.85, delay_s=0.12):
        _hud_err(f"[dashboard] не удалось нажать профиль '{mode}'")
        _ensure_alt_b(controller, open_state=False, win=win, lang=lang, timeout_s=1.0)
        return False, False

    _hud_succ("[dashboard] Бафаемся…")

    # При желании можно подождать 1–2 секунды “каста” — пока без ожиданий
    time.sleep(0.2)

    # Закрыть дэш, чтобы не мешался (по желанию — можно оставить открыт)
    _ensure_alt_b(controller, open_state=False, win=win, lang=lang, timeout_s=1.0)

    return True, True
