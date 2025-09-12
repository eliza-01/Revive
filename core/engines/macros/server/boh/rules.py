# core/engines/macros/server/boh/rules.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, List

from core.state.pool import pool_get
from core.orchestrators.snapshot import Snapshot
from core.engines.macros.runner import run_macros
from core.logging import console


def run_step(
    *,
    state: Dict[str, Any],
    ps_adapter,
    controller,
    snap: Snapshot,
    helpers: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, bool]:
    """
    Правило шага MACROS для текущего сервера. Контракт: (ok, advance).
    """
    rows = _get_rows_from_pool(state)
    if not rows:
        console.hud("err", "[MACROS] Нет макросов для выполнения")
        return False, True

    srv = pool_get(state, "config.server", None) or ""
    ok = run_macros(
        server=srv,
        controller=controller,
        get_window=lambda: pool_get(state, "window.info", None),
        get_language=lambda: pool_get(state, "config.language", "rus"),
        cfg={"rows": rows},
        should_abort=lambda: False,
    )

    # после успешного «ручного» прогона — сдвигаем таймер повтора
    try:
        if ok:
            svc = (state.get("_services") or {}).get("macros_repeat")
            if hasattr(svc, "bump_all"):
                svc.bump_all()
    except Exception:
        pass

    return (bool(ok), bool(ok))


def _get_rows_from_pool(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = list(pool_get(state, "features.macros.rows", []) or [])
    if rows:
        out = []
        for r in rows:
            key = str((r or {}).get("key", "1"))[:1]
            cast_s = int(float((r or {}).get("cast_s", 0)))
            repeat_s = int(float((r or {}).get("repeat_s", 0)))
            out.append({"key": key, "cast_s": max(0, cast_s), "repeat_s": max(0, repeat_s)})
        return out
    return []
