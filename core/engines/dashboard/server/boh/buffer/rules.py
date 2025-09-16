# core/engines/dashboard/server/boh/buffer/rules.py
# core/engines/dashboard/server/<server>/buffer/rules.py
from __future__ import annotations
from typing import Any, Dict, Optional, List, Tuple
import time
import tempfile
import importlib
import os

import cv2
import numpy as np

from core.logging import console
from core.state.pool import pool_get, pool_write
from core.vision.zones import compute_zone_ltrb
from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.vision.matching.template_matcher_2 import (
    match_key_in_zone_single,
)

from ..dashboard_data import TEMPLATES, ZONES, BUFFS, DANCES, SONGS
from .engine import BufferEngine
from ..templates.resolver import resolve as tpl_resolve


# ---------------------- helpers ----------------------
def _run_unstuck(state: Dict[str, Any], controller) -> None:
    try:
        srv = (pool_get(state, "config.server", "boh") or "boh").lower()
        mod = importlib.import_module(f"core.engines.ui_guard.server.{srv}.engine")
        Eng = getattr(mod, "UIGuardEngine", None)
        if Eng is None:
            console.log("[UNSTUCK] UIGuardEngine not found")
            return
        eng = Eng(server=srv, controller=controller, state=state)
        eng.run_unstuck()
    except Exception as e:
        console.log(f"[UNSTUCK] invoke error: {e}")


def _debug_open_zone_with_icons(
    state: Dict[str, Any],
    win: Dict[str, Any],
    lang: str,
    tokens: List[str],
    zone_name: str = "current_buffs",
    filename_hint: str = "verify"
) -> None:
    """
    Если включен флаг runtime.debug.buff_zone=True —
    сохраняет PNG зоны + снизу полосу с иконками, которые ищем.
    Автоматически открывает изображение системной вьюхой.
    """
    dbg = bool(pool_get(state, "runtime.debug.buff_zone", False))
    if not dbg:
        return
    try:
        # зона
        decl = ZONES.get(zone_name)
        if decl is None:
            console.log(f"[dashboard/buffer][dbg] zone '{zone_name}' not found")
            return
        ltrb = compute_zone_ltrb(win, decl)
        roi = capture_window_region_bgr(win, ltrb)
        if roi is None or roi.size == 0:
            console.log(f"[dashboard/buffer][dbg] zone '{zone_name}' empty")
            return

        # собрать иконки (25x25 + зелёная рамка + подпись)
        icons = []
        for tok in (tokens or []):
            parts = (BUFFS.get(tok) or DANCES.get(tok) or SONGS.get(tok))
            if not parts:
                continue
            p = tpl_resolve(lang, *parts)
            if not (p and os.path.isfile(p)):
                continue
            img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            if img is None or img.size == 0:
                continue
            # в BGR
            if img.ndim == 2:
                icon = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif img.ndim == 3 and img.shape[2] == 4:
                icon = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            else:
                icon = img
            icon = cv2.resize(icon, (25, 25), interpolation=cv2.INTER_AREA)
            # рамка
            icon = cv2.copyMakeBorder(icon, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=(0, 255, 0))
            # подпись
            label_h = 14
            tile_w, tile_h = icon.shape[1], icon.shape[0] + label_h
            tile = np.zeros((tile_h, tile_w, 3), dtype=np.uint8)
            tile[0:icon.shape[0], 0:icon.shape[1]] = icon
            cv2.putText(tile, str(tok)[:10], (2, tile_h - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
            icons.append(tile)

        # собрать полосу иконок
        strip = None
        if icons:
            cols = min(12, len(icons))
            rows = int(np.ceil(len(icons) / cols))
            row_imgs = []
            for r in range(rows):
                row_tiles = icons[r * cols:(r + 1) * cols]
                row_imgs.append(np.hstack(row_tiles))
            strip = np.vstack(row_imgs)
            # заголовок
            header = np.zeros((20, strip.shape[1], 3), dtype=np.uint8)
            cv2.putText(header, "SEARCHING:", (5, 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
            strip = np.vstack([header, strip])

        # финальная картинка
        roi_bgr = roi if roi.ndim == 3 else cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
        if strip is not None:
            W = max(roi_bgr.shape[1], strip.shape[1])

            def _pad_w(img):
                if img.shape[1] == W:
                    return img
                pad = np.zeros((img.shape[0], W - img.shape[1], 3), dtype=np.uint8)
                return np.hstack([img, pad])

            out = np.vstack([_pad_w(roi_bgr), _pad_w(strip)])
        else:
            out = roi_bgr

        # сохранить и открыть
        ts = int(time.time())
        base = f"revive_dbg_{zone_name}_{filename_hint}_{ts}.png"
        path = os.path.join(tempfile.gettempdir(), base)
        cv2.imwrite(path, out)
        console.log(f"[dashboard/buffer][dbg] saved zone '{zone_name}' -> {path}")
        try:
            os.startfile(path)  # Windows
        except Exception:
            try:
                import subprocess, platform
                if platform.system() == "Darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
            except Exception:
                pass
    except Exception as e:
        console.log(f"[dashboard/buffer][dbg] error: {e}")


def _paused_now(state: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        p = bool(pool_get(state, "features.buff.paused", False))
        reason = str(pool_get(state, "features.buff.pause_reason", "") or "")
        return p, reason
    except Exception:
        return False, ""


def _win_ok(win: Optional[Dict[str, Any]]) -> bool:
    return bool(win and all(k in win for k in ("x", "y", "width", "height")))


def _hud_ok(msg: str):   console.hud("ok",   msg)
def _hud_err(msg: str):  console.hud("err",  msg)
def _hud_succ(msg: str): console.hud("succ", msg)


def _zone_ltrb(win: Dict[str, Any], name: str) -> Tuple[int, int, int, int]:
    decl = ZONES.get(name, ZONES.get("fullscreen", {"fullscreen": True}))
    l, t, r, b = compute_zone_ltrb(win, decl)
    return (int(l), int(t), int(r), int(b))


def _click(controller, x: int, y: int, *, hover_delay_s: float = 0.20, post_delay_s: float = 0.20) -> None:
    try:
        if hasattr(controller, "move"):
            controller.move(int(x), int(y))
        time.sleep(max(0.0, float(hover_delay_s)))
        if hasattr(controller, "_click_left_arduino"):
            controller._click_left_arduino()
        else:
            controller.send("l")
        time.sleep(max(0.0, float(post_delay_s)))
    except Exception:
        pass


def _ensure_alt_b(controller, *, want_open: bool, win: Dict[str, Any], server: str, lang: str, timeout_s: float = 2.0) -> bool:
    """
    Привести дэш к нужному состоянию (want_open=True → открыт) по ключу 'dashboard_init'.
    Проверка состояния — как в respawn: сначала матч, без клика.
    """
    parts = TEMPLATES.get("dashboard_init")
    if not parts:
        _hud_err("[dashboard] нет шаблона dashboard_init")
        return False

    def _is_open() -> bool:
        pt = match_key_in_zone_single(
            window=win,
            zone_ltrb=_zone_ltrb(win, "fullscreen"),
            server=server,
            lang=lang,
            template_parts=parts,
            threshold=0.87,
            engine="dashboard",
        )
        return pt is not None

    # уже в нужном состоянии?
    cur = _is_open()
    if (want_open and cur) or ((not want_open) and (not cur)):
        return True

    # тоггл Alt+B
    try:
        controller.send("altB")
    except Exception:
        pass

    end = time.time() + max(0.2, float(timeout_s))
    while time.time() < end:
        if _is_open() == want_open:
            return True
        time.sleep(0.05)
    return False


def _dashboard_is_locked(win: Dict[str, Any], server: str, lang: str) -> bool:
    """
    Новый вариант: не нажимаем ничего — просто проверяем наличие хотя бы одного
    из 'dashboard_is_locked_*' (по аналогии с respawn-метчами).
    """
    for key in ("dashboard_is_locked_1", "dashboard_is_locked_2"):
        parts = TEMPLATES.get(key)
        if not parts:
            continue
        pt = match_key_in_zone_single(
            window=win,
            zone_ltrb=_zone_ltrb(win, "fullscreen"),
            server=server,
            lang=lang,
            template_parts=parts,
            threshold=0.82,
            engine="dashboard",
        )
        if pt:
            return True
    return False


# ---- attempts & alive ----------------------------------------------------

def _player_is_dead(state: Dict[str, Any]) -> bool:
    try:
        alive = pool_get(state, "player.alive", None)
        return (alive is False)
    except Exception:
        return False


def _get_attempts(state: Dict[str, Any]) -> int:
    try:
        return int(pool_get(state, "features.buff.attempts", 0) or 0)
    except Exception:
        return 0


def _set_attempts(state: Dict[str, Any], n: int) -> None:
    try:
        pool_write(state, "features.buff", {"attempts": int(max(0, n))})
    except Exception:
        pass


def _bump_attempts(state: Dict[str, Any]) -> int:
    n = _get_attempts(state) + 1
    _set_attempts(state, n)
    return n


def _reset_attempts(state: Dict[str, Any]) -> None:
    _set_attempts(state, 0)


# ---------------------- public entry (pipeline step) ----------------------

def run_step(
    state: Dict[str, Any],
    ps_adapter,
    controller,
    snap,  # core.orchestrators.snapshot.Snapshot
    helpers: Dict[str, Any],
) -> Tuple[bool, bool]:
    """
    Шаг 'buff' через dashboard/buffer:
      1) Закрыть дэш, если открыт (Alt+B).
      2) Открыть дэш (Alt+B) и убедиться, что открыт.
      3) Перейти на вкладку баффера.
      4) Ждать появления экрана баффера; если не появился — проверить доступность (locked).
      5) Нажать профиль (profile|mage|fighter|archer*).
      6) Проверить баф по иконкам (features.buff.checker).
      7) По успеху прожать Restore HP и закрыть дэш.

      Дополнительно:
      - Если player.alive == False — прекращаем попытку шага сразу.
      - Если attempts >= 5 — вызов /unstuck и выходим.
      - Если features.buff.paused == True — не тратим время, просто ждём (return False, False).
    """

    # окно
    win = helpers.get("get_window", lambda: None)()  # type: ignore
    if not _win_ok(win):
        return False, False

    # пауза — уважение orchestration-паузы (вместо is_focused)
    paused, reason = _paused_now(state)
    if paused:
        console.hud("ok", f"[dashboard] пауза: {reason or 'остановлено'} — жду")
        return False, False

    # если мёртв — прекратить попытки (не тратим время на бафф)
    if _player_is_dead(state):
        _hud_err("[dashboard] игрок мёртв — бафф пропущен")
        return False, True  # прекращаем попытку, даём пайплайну идти дальше

    # лимит попыток
    attempts = _get_attempts(state)
    if attempts >= 5:
        _hud_err(f"[dashboard] попытки исчерпаны (>={attempts}) — запускаю /unstuck")
        _run_unstuck(state, controller)
        _reset_attempts(state)
        return False, True

    # инкремент перед процедурой шага
    _bump_attempts(state)

    # параметры окружения
    lang = (helpers.get("get_language", lambda: "rus")() or "rus").lower()  # type: ignore
    server = (pool_get(state, "config.server", "") or "").lower()

    # локальная проверка «стоит ли прерывать ожидания»
    def _should_abort() -> bool:
        p, _ = _paused_now(state)
        if p:
            return True
        if _player_is_dead(state):
            return True
        return False

    # 1) Сброс
    _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.5)

    # 2) Открыть и проверить
    if _should_abort():
        return False, False
    if not _ensure_alt_b(controller, want_open=True, win=win, server=server, lang=lang, timeout_s=2.5):
        _hud_err("[dashboard] Alt+B: не удалось открыть")
        return False, False
    _hud_ok("[dashboard] Alt+B открыт")

    # 3) Перейти на вкладку баффера — сначала матч, затем явный клик
    btn = TEMPLATES.get("dashboard_buffer_button")
    if not btn:
        _hud_err("[dashboard] не вижу кнопку раздела баффера")
        _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.0)
        return False, False

    pt = match_key_in_zone_single(
        window=win,
        zone_ltrb=_zone_ltrb(win, "fullscreen"),
        server=server,
        lang=lang,
        template_parts=btn,
        threshold=0.85,
        engine="dashboard",
    )
    if not pt:
        _hud_err("[dashboard] не удалось найти кнопку баффера")
        _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.0)
        return False, False

    _click(controller, pt[0], pt[1], hover_delay_s=0.20, post_delay_s=0.20)

    # 4) Ждать появления экрана баффера; если не появился — проверить доступность
    buf_init = TEMPLATES.get("dashboard_buffer_init")
    end = time.time() + 2.0
    opened = False
    while time.time() < end:
        # прерывание ожидания при паузе/смерти
        if _should_abort():
            _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.0)
            # смерть → завершаем попытку; пауза → просто ждём в пайплайне
            return (False, True) if _player_is_dead(state) else (False, False)

        pt2 = match_key_in_zone_single(
            window=win,
            zone_ltrb=_zone_ltrb(win, "fullscreen"),
            server=server,
            lang=lang,
            template_parts=buf_init or [],
            threshold=0.85,
            engine="dashboard",
        ) if buf_init else None
        if pt2:
            opened = True
            break
        time.sleep(0.05)

    if not opened:
        # Только теперь проверяем «доступность»
        if _dashboard_is_locked(win, server, lang):
            _hud_err("[dashboard] заблокирован (ждем..)")
            _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.0)
            return False, False

        _hud_err("[dashboard] баффер не открылся")
        _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.0)
        return False, False

    _hud_ok("[dashboard] баффер открыт")

    # 5) Нажать профиль (mode из пула передаём в engine явно)
    mode = (pool_get(state, "features.buff.mode", "") or "").strip().lower() or "profile"
    be = BufferEngine(
        server=server,
        controller=controller,
        get_window=helpers.get("get_window", lambda: None),
        get_language=helpers.get("get_language", lambda: "rus"),
    )
    if not be.click_mode(mode=mode, thr=0.85):
        _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.0)
        return False, False

    time.sleep(0.5)  # дать анимации времени

    # 6) Верификация бафа (сбор токенов — здесь, матч — в engine)
    tokens: List[str] = list(pool_get(state, "features.buff.checker", []) or [])
    if tokens:
        _debug_open_zone_with_icons(state, win, lang, tokens, filename_hint="verify")
    if not be.verify_selected_buffs(tokens, thr=0.86):
        _hud_err("[dashboard] баф не обнаружен")
        _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.0)
        return False, False

    # 7) Restore HP и закрыть
    if be.click_restore_hp(thr=0.85):
        _hud_ok("[dashboard] восстановление HP")
    time.sleep(0.2)
    _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.0)

    # успешно — сбрасываем счётчик попыток
    _reset_attempts(state)
    _hud_succ("[dashboard] баф подтверждён")
    return True, True
