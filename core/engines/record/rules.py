# core/engines/record/rules.py
from __future__ import annotations
from typing import Any, Dict, Tuple, Optional, List
import time

from core.logging import console
from core.state.pool import pool_get, pool_write

from .engine import RecordEngine

def _focused_now(state: Dict[str, Any]) -> Optional[bool]:
    try:
        v = pool_get(state, "focus.is_focused", None)
        return bool(v) if isinstance(v, bool) else None
    except Exception:
        return None

def _win_has_focus_or_wait(helpers: Dict[str, Any], timeout_s: float = 3.0) -> bool:
    get_focus = helpers.get("get_focus")  # опц. колбэк, если есть
    if callable(get_focus):
        return bool(get_focus(timeout_s=timeout_s))
    # иначе — фолбэк на пул
    end = time.time() + max(0.0, timeout_s)
    state = helpers.get("state") or {}
    while time.time() < end:
        if _focused_now(state) is not False:
            return True
        time.sleep(0.05)
    return _focused_now(state) is not False

def _set_busy(state: Dict[str, Any], v: bool):
    try:
        pool_write(state, "features.record", {"busy": bool(v), "ts": time.time()})
    except Exception:
        pass

def _set_status(state: Dict[str, Any], status: str):
    try:
        pool_write(state, "features.record", {"status": status, "ts": time.time()})
    except Exception:
        pass

def run_step(
    *,
    state: Dict[str, Any],
    ps_adapter,
    controller,
    snap,  # Snapshot
    helpers: Dict[str, Any],
) -> Tuple[bool, bool]:

    console.log("[record.rules] enter run_step")

    if not snap.has_window:
        console.log("[record.rules] no window -> skip")
        return False, False

    enabled = bool(pool_get(state, "features.record.enabled", False))
    status  = str(pool_get(state, "features.record.status", "") or "")
    current = str(pool_get(state, "features.record.current_record", "") or "")
    console.log(f"[record.rules] enter enabled={enabled} status={status} current='{current}' focus={snap.is_focused}")

    if not enabled:
        console.log("[record.rules] skip: not enabled")
        return False, False
    if status == "recording":
        console.log("[record.rules] skip: already recording")
        return False, False

    if bool(pool_get(state, "features.record.status", "") == "recording"):
        console.log("[record.rules] currently recording -> skip playback")
        return False, False

    engine: RecordEngine = helpers.get("record_engine")
    if not isinstance(engine, RecordEngine):
        console.hud("err", "[record] internal: engine missing")
        console.log("[record.rules] engine missing")
        return False, True

    focused = _win_has_focus_or_wait(helpers, timeout_s=3.0)
    console.log(f"[record.rules] focused={focused}")
    if not focused:
        console.hud("err", "[record] нет фокуса окна")
        return False, False

    # воспроизведение записи через countdown_s (!нет это не тут)
    ok = bool(engine.play(wait_focus_cb=lambda timeout_s=0: True, countdown_s=3.0))
    console.log(f"[record.rules] play -> ok={ok}")
    pool_write(state, "features.record", {"enabled": False})
    return ok, True