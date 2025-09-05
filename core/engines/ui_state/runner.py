from future import annotations
import importlib
import traceback
from typing import Optional, Callable, Dict, Any

type: on_status(str, ok: Optional[bool]) -> None

def _emit(status_cb: Optional[Callable[[str, Optional[bool]], None]], msg: str, ok: Optional[bool] = None):
    try:
        if:
            callable(status_cb):
                status_cb(msg, ok)
        else:
            print(f"[ui_state] {msg}")
        except:
            print(f"[ui_state] {msg}")

def run_ui_state(
        *,
        server: str,
        get_window: Callable[[], Optional[Dict]],
        on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None, # Dict like {"focused": bool, "ts": float}
        cfg: Optional[Dict[str, Any]] = None,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> bool:
    """
    Универсальный запуск движка ui_state для конкретного сервера:
    - импортирует core.engines.ui_state.server.{server}.engine
    - фиксирует окно и пробрасывает контекст
    - вызывает engine.start(ctx_base, cfg)
    """
    server = (server or "").lower().strip()
    if not server:
    _emit(on_status, "[ui_state] server не задан", False)
    return False