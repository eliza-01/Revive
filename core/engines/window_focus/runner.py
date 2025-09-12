# core/engines/window_focus/runner.py
from __future__ import annotations
import importlib
from typing import Optional, Callable, Dict, Any

from core.logging import console


def run_window_focus(
    *,
    server: str = "common",
    get_window: Callable[[], Optional[Dict]],
    on_update: Optional[Callable[[Dict[str, Any]], None]] = None,  # {"is_focused": bool, "ts": float}
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
        console.log("[window_focus] get_window не задан")
        console.hud("err", "[window_focus] get_window не задан")
        return False

    # 2) Импорт серверного движка
    mod_name = f"core.engines.window_focus.server.{server}.engine"
    try:
        engine = importlib.import_module(mod_name)
    except Exception as e:
        console.log(f"[window_focus] не найден движок '{server}': {e}")
        console.hud("err", f"[window_focus] не найден движок '{server}': {e}")
        return False

    # 3) Контекст
    ctx_base = {
        "server": server,
        "get_window": get_window,              # динамически читаем окно на каждом тике в движке
        "on_update": on_update,                # публикация is_focused наружу
        "should_abort": (should_abort or (lambda: False)),
    }

    # 4) Старт
    try:
        if not hasattr(engine, "start"):
            console.log(f"[window_focus] у движка '{server}' нет функции start()")
            console.hud("err", f"[window_focus] у движка '{server}' нет функции start()")
            return False
        cfg = cfg or {}
        return bool(engine.start(ctx_base, cfg))
    except Exception as e:
        console.log(f"[window_focus] ошибка выполнения движка: {e}")
        console.hud("err", f"[window_focus] ошибка выполнения движка: {e}")
        return False
