# core/engines/dashboard/server/boh/teleport/rules.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import time

from core.logging import console
from core.state.pool import pool_get, pool_write
from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher_2 import match_key_in_zone_single

from ..dashboard_data import ZONES, TEMPLATES
from .engine import TeleportEngine
from .stabilize import rules as stabilize_rules


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


def _zone_ltrb(win: Dict, name: str) -> tuple[int, int, int, int]:
    decl = ZONES.get(name, ZONES.get("fullscreen", {"fullscreen": True}))
    l, t, r, b = compute_zone_ltrb(win, decl)
    return (int(l), int(t), int(r), int(b))


def _ensure_alt_b(controller, *, want_open: bool, win: Dict, server: str, lang: str, timeout_s: float = 2.0) -> bool:
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

    cur = _is_open()
    if (want_open and cur) or ((not want_open) and (not cur)):
        return True

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


def _player_is_dead(state: Dict[str, Any]) -> bool:
    try:
        alive = pool_get(state, "player.alive", None)
        return (alive is False)
    except Exception:
        return False


def _get_attempts(state: Dict[str, Any]) -> int:
    try:
        return int(pool_get(state, "features.teleport.attempts", 0) or 0)
    except Exception:
        return 0


def _set_attempts(state: Dict[str, Any], n: int) -> None:
    try:
        pool_write(state, "features.teleport", {"attempts": int(max(0, n))})
    except Exception:
        pass


def _bump_attempts(state: Dict[str, Any]) -> int:
    n = _get_attempts(state) + 1
    _set_attempts(state, n)
    return n


def _reset_attempts(state: Dict[str, Any]) -> None:
    _set_attempts(state, 0)


def run_step(
    state: Dict[str, Any],
    ps_adapter,
    controller,
    snap,  # core.orchestrators.snapshot.Snapshot
    helpers: Dict[str, Any],
) -> tuple[bool, bool]:

    win = helpers.get("get_window", lambda: None)()  # type: ignore
    if not _win_ok(win):
        return False, False

    if _focused_now(state) is False:
        console.hud("ok", "[dashboard] пауза: окно без фокуса — жду")
        return False, False

    if _player_is_dead(state):
        _hud_err("[teleport] игрок мёртв — телепорт пропущен")
        return False, True

    attempts = _get_attempts(state)
    if attempts >= 10:
        _hud_err("[teleport] попытки исчерпаны (>=10)")
        return False, True
    _bump_attempts(state)

    lang = (helpers.get("get_language", lambda: "rus")() or "rus").lower()  # type: ignore
    server = (pool_get(state, "config.server", "") or "").lower()

    method = (pool_get(state, "features.teleport.method", "") or "").strip().lower()
    category = (pool_get(state, "features.teleport.category", "") or "").strip()
    location = (pool_get(state, "features.teleport.location", "") or "").strip()

    if method and method != "dashboard":
        _hud_err(f"[teleport] неподдерживаемый метод: {method}")
        return False, True

    if not category or not location:
        _hud_err("[teleport] выберите категорию и локацию")
        return True, True

    te = TeleportEngine(
        state=state,
        server=server,
        controller=controller,
        get_window=helpers.get("get_window", lambda: None),
        get_language=helpers.get("get_language", lambda: "rus"),
    )

    # 1) Сброс
    _ensure_alt_b(controller, want_open=False, win=win, server=server, lang=lang, timeout_s=1.5)

    # 2) Открыть Alt+B
    if not _ensure_alt_b(controller, want_open=True, win=win, server=server, lang=lang, timeout_s=2.5):
        _hud_err("[dashboard] Alt+B: не удалось открыть")
        return False, False
    _hud_ok("[dashboard] Alt+B открыт")

    # 3) Вкладка Teleport
    if not te.open_tab(thr_btn=0.85, thr_init=0.85, timeout_s=2.0):
        # НЕ закрываем: пусть останется как есть
        return False, False

    # 4) Категория
    if not te.open_category(category):
        return False, False

    # 5) Локация (click → ждать пропажи dashboard_init)
    if not te.click_location(location, category):
        return False, False

    # === СТАБИЛИЗАЦИЯ ===
    ok_stab, _ = stabilize_rules.run_step(
        state=state,
        ps_adapter=ps_adapter,
        controller=controller,
        snap=snap,
        helpers={"get_window": helpers.get("get_window"), "get_language": helpers.get("get_language")},
    )
    if not ok_stab:
        return False, False

    _reset_attempts(state)
    _hud_succ("[teleport] шаг завершён")
    return True, True
