# core/engines/respawn/server/boh/rules.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import time

from core.state.pool import pool_get
from core.orchestrators.snapshot import Snapshot


def run_step(
    *,
    state: Dict[str, Any],
    ps_adapter,
    controller,
    report,
    snap: Snapshot,
    helpers: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, bool]:
    """
    Правило шага RESPawn для текущего сервера.
    Контракт: вернуть (ok, advance).
    """
    helpers = helpers or {}

    # не начинать без окна
    if not snap.has_window:
        _dbg(state, "respawn: no window")
        return False, False

    # если уже жив — шаг успешен и идём дальше
    if snap.alive is True:
        _dbg(state, "respawn: already alive")
        _reset_macros_after_respawn(state)
        return True, True

    # опциональное ожидание «ждать возрождения»
    wait_enabled = bool(pool_get(state, "features.respawn.wait_enabled", False))
    wait_seconds = int(pool_get(state, "features.respawn.wait_seconds", 0))
    if wait_enabled and wait_seconds > 0:
        start = time.time()
        deadline = start + wait_seconds
        tick = -1
        while time.time() < deadline:
            st = ps_adapter.last() or {}
            if st.get("alive"):
                report("[RESPAWN] Поднялись (ожидание)")
                _dbg(state, "respawn/wait: alive -> success")
                _reset_macros_after_respawn(state)
                return True, True
            sec = int(time.time() - start)
            if sec != tick:
                tick = sec
                report(f"[RESPAWN] ожидание возрождения… {sec}/{wait_seconds}")
            time.sleep(1.0)

    # активная попытка восстановления
    report("[RESPAWN] Активная попытка восстановления…")
    runner = helpers.get("respawn_runner")
    if runner is not None:
        try:
            server = pool_get(state, "config.server", None)
            if server:
                runner.set_server(server)
        except Exception:
            pass
        ok = bool(runner.run(timeout_ms=14_000))
        _dbg(state, f"respawn: result ok={ok}")
        if ok:
            _reset_macros_after_respawn(state)
        return (ok, ok)

    report("[RESPAWN] internal: runner missing")
    return False, True


def _reset_macros_after_respawn(state: Dict[str, Any]) -> None:
    """После респавна: сброс таймеров повторов, чтобы не было «двойного макроса»."""
    try:
        svc = (state.get("_services") or {}).get("macros_repeat")
        if hasattr(svc, "bump_all"):
            svc.bump_all()
    except Exception:
        pass


def _dbg(state: Dict[str, Any], msg: str):
    if pool_get(state, "runtime.debug.respawn_debug", False) or pool_get(state, "runtime.debug.pipeline_debug", False):
        try:
            print(f"[RESPAWN/RULE] {msg}")
        except Exception:
            pass
