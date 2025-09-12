from __future__ import annotations
import importlib
from typing import Optional, Callable, Dict, Any
from core.logging import console


def run_player_state(
    *,
    server: str,
    get_window: Callable[[], Optional[Dict]],
    on_update: Optional[Callable[[Dict[str, Any]], None]] = None,  # {"hp_ratio": float, "ts": float}
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
        console.log("[player_state] server не задан")
        return False

    # 1) Проверка окна (фиксируем на запуск)
    try:
        win = get_window() if callable(get_window) else None
    except Exception:
        win = None
    if not win:
        console.log("[player_state] окно не найдено")
        return False

    # 2) Импорт серверного движка
    mod_name = f"core.engines.player_state.server.{server}.engine"
    try:
        engine = importlib.import_module(mod_name)
    except Exception as e:
        console.log(f"[player_state] не найден движок сервера '{server}': {mod_name}: {e}")
        return False

    # 3) Контекст (минимально необходимый)
    ctx_base = {
        "server": server,
        "get_window": lambda: win,   # фиксируем окно на момент запуска
        "on_update": on_update,      # опционально: публикация hp_ratio наружу
        "should_abort": (should_abort or (lambda: False)),
    }

    # 4) Старт
    try:
        if not hasattr(engine, "start"):
            console.log(f"[player_state] у движка '{server}' нет функции start()")
            return False
        cfg = cfg or {}
        console.log(f"[player_state] запуск движка '{server}'…")
        ok = bool(engine.start(ctx_base, cfg))
        console.log(f"[player_state] завершено: {'OK' if ok else 'FAIL'}")
        return ok
    except Exception as e:
        console.log(f"[player_state] ошибка выполнения движка: {e}")
        return False
