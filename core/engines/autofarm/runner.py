# core/engines/autofarm/runner.py
from __future__ import annotations
import importlib
from typing import Callable, Dict, Any

def run_autofarm(
    server: str,
    controller,
    get_window: Callable[[], Dict[str, Any]],
    get_language: Callable[[], str],
    on_status: Callable[[str, bool | None], None] = lambda *_: None,
    should_abort=None,
    cfg: Dict[str, Any] | None = None,
) -> bool:
    server = (server or "common").lower()
    mod_path = f"core.engines.autofarm.server.{server}.engine"
    try:
        mod = importlib.import_module(mod_path)
    except Exception as e:
        on_status(f"[af] engine import error ({mod_path}): {e}", False)
        return False

    ctx = {
        "server": server,
        "controller": controller,
        "get_window": get_window,
        "get_language": get_language,
        "on_status": on_status,
    }
    if callable(should_abort):
        ctx["should_abort"] = should_abort

    try:
        return bool(mod.start(ctx, cfg or {}))
    except Exception as e:
        on_status(f"[af] start error: {e}", False)
        return False
