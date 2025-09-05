# core/engines/window_focus/runner.py
from __future__ import annotations
import importlib
import traceback
from typing import Optional, Callable, Dict, Any

# type: on_status(str, ok: Optional[bool]) -> None
def _emit(status_cb: Optional[Callable[[str, Optional[bool]], None]], msg: str, ok: Optional[bool] = None):
    try:
        if callable(status_cb):
            status_cb(msg, ok)
        else:
            print(f"[window_focus] {msg}")
    except Exception:
        print(f"[window_focus] {msg}")

def run_window_focus(
    *,
    server: str = "common",
    get_window: Callable[[], Optional[Dict]],
    on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
    on_update: Optional[Callable[[Dict[str, Any]], None]] = None,  # {"has_focus": bool, "ts": float}
    cfg: Optional[Dict[str, Any]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> bool:
    """
    Универсальный запуск движка window_focus:
      - импортирует core.engines.window_focus.server.{server}.engine
      - пробрасывает get_window как есть (НЕ фиксируем), чтобы каждый тик видеть актуальный hwnd
      - вызывает engine.start(ctx_base, cfg)
    """
    server = (server or "common").lower().strip()

    # 1) Проверка наличия функции get_window
    if not callable(get_window):
        _emit(on_status, "[window_focus] get_window не задан", False)
        return False

    # 2) Импорт серверного движка (общий для всех — common)
    mod_name = f"core.engines.window_focus.server.{server}.engine"
    try:
        engine = importlib.import_module(mod_name)
    except Exception as e:
        _emit(on_status, f"[window_focus] не найден движок сервера '{server}': {mod_name}: {e}", False)
        _emit(on_status, traceback.format_exc(), False)
        return False

    # 3) Контекст
    def _status(msg: str, ok: Optional[bool] = None):
        _emit(on_status, msg, ok)

    ctx_base = {
        "server": server,
        "get_window": get_window,              # важно: динамически читаем окно на каждом тике в движке
        "on_status": _status,
        "on_update": on_update,                # публикация has_focus наружу
        "should_abort": (should_abort or (lambda: False)),
    }

    # 4) Старт
    try:
        if not hasattr(engine, "start"):
            _emit(on_status, f"[window_focus] у движка '{server}' нет функции start()", False)
            return False
        cfg = cfg or {}
        _emit(on_status, f"[window_focus] запуск движка '{server}'…", None)
        ok = bool(engine.start(ctx_base, cfg))
        _emit(on_status, f"[window_focus] завершено: {'OK' if ok else 'FAIL'}", True if ok else False)
        return ok
    except Exception as e:
        _emit(on_status, f"[window_focus] ошибка выполнения движка: {e}", False)
        _emit(on_status, traceback.format_exc(), False)
        return False
