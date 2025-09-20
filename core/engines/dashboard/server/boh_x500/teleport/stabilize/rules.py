# core/engines/dashboard/server/boh_x500/teleport/stabilize/rules.py
from __future__ import annotations
from typing import Any, Dict

from core.state.pool import pool_get
from core.logging import console

from .engine import StabilizeEngine


def run_step(
    state: Dict[str, Any],
    ps_adapter,
    controller,
    snap,
    helpers: Dict[str, Any],
) -> tuple[bool, bool]:
    """
    Выполняет required + (опц.) optional стабилизацию после клика по локации.
    Завершается True,True если:
      - обязательная стабилизация прошла
      - и либо optional выключена, либо optional тоже прошла
    """
    server = (pool_get(state, "config.server", "") or "").lower()
    location = (pool_get(state, "features.teleport.location", "") or "").strip()

    # флаг: features.stabilize.enabled
    do_optional = bool(pool_get(state, "features.stabilize.enabled", False))

    if not location:
        # ничего стабилизировать — считаем успехом
        return True, True

    eng = StabilizeEngine(
        state=state,
        server=server,
        controller=controller,
        get_window=helpers.get("get_window", lambda: None),
        get_language=helpers.get("get_language", lambda: "rus"),
    )

    ok = eng.run(location, do_optional=do_optional)
    return (ok, ok)
