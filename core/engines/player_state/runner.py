# core/engines/player_state/runner.py
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
            print(f"[player_state] {msg}")
    except Exception:
        print(f"[player_state] {msg}")

def run_player_state(
    *,
    server: str,
    get_window: Callable[[], Optional[Dict]],
    on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
    on_update: Optional[Callable[[Dict[str, Any]], None]] = None,  # Dict with {"hp_ratio": float, "ts": float}
    cfg: Optional[Dict[str, Any]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> bool:
    """
    Универсальный запуск движка player_state для конкретного сервера:
      - импортирует core.engines.player_state.server.{server}.engine
      - фиксирует окно и пробрасывает контекст
      - вызывает engine.start(ctx_base, cfg)
    """
    server = (server or "").lower().strip()
    if not server:
        _emit(on_status, "[player_state] server не задан", False)
        return False

    # 1) Проверка окна (фиксируем на запуск)
    win = None
    try:
        win = get_window() if callable(get_window) else None
    except Exception:
        win = None
    if not win:
        _emit(on_status, "[player_state] окно не найдено", False)
        return False

    # 2) Импорт серверного движка
    mod_name = f"core.engines.player_state.server.{server}.engine"
    try:
        engine = importlib.import_module(mod_name)
    except Exception as e:
        _emit(on_status, f"[player_state] не найден движок сервера '{server}': {mod_name}: {e}", False)
        _emit(on_status, traceback.format_exc(), False)
        return False

    # 3) Контекст (минимально необходимый)
    def _status(msg: str, ok: Optional[bool] = None):
        _emit(on_status, msg, ok)

    ctx_base = {
        "server": server,
        "get_window": lambda: win,   # фиксируем окно на момент запуска
        "on_status": _status,
        "on_update": on_update,      # опционально: публикация hp_ratio наружу
        "should_abort": (should_abort or (lambda: False)),
    }

    # 4) Старт
    try:
        if not hasattr(engine, "start"):
            _emit(on_status, f"[player_state] у движка '{server}' нет функции start()", False)
            return False
        cfg = cfg or {}
        _emit(on_status, f"[player_state] запуск движка '{server}'…", None)
        ok = bool(engine.start(ctx_base, cfg))
        _emit(on_status, f"[player_state] завершено: {'OK' if ok else 'FAIL'}", True if ok else False)
        return ok
    except Exception as e:
        _emit(on_status, f"[player_state] ошибка выполнения движка: {e}", False)
        _emit(on_status, traceback.format_exc(), False)
        return False
