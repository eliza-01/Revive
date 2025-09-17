from __future__ import annotations
import importlib
from typing import Optional, Callable, Dict, Any

from core.logging import console


def run_window_focus(
    *,
    server: str = "common",  # сохранён для совместимости, не используется
    get_window: Callable[[], Optional[Dict]],
    on_update: Optional[Callable[[Dict[str, Any]], None]] = None,  # {"is_focused": bool, "ts": float}
    cfg: Optional[Dict[str, Any]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> bool:
    """
    Универсальный запуск движка window_focus:
      - импортирует core.engines.window_focus.engine (без привязки к server)
      - пробрасывает get_window как есть, чтобы каждый тик видеть актуальный hwnd
      - вызывает engine.start(ctx_base, cfg)
    """
    # 1) Проверка наличия функции get_window
    if not callable(get_window):
        console.log("[window_focus] get_window не задан")
        console.hud("err", "[window_focus] get_window не задан")
        return False

    # 2) Импорт движка по фиксированному пути
    mod_name = "core.engines.window_focus.engine"
    try:
        engine = importlib.import_module(mod_name)
    except Exception as e:
        console.log(f"[window_focus] не найден движок: {e}")
        console.hud("err", f"[window_focus] не найден движок: {e}")
        return False

    # 3) Контекст
    ctx_base = {
        "server": (server or "common"),
        "get_window": get_window,
        "on_update": on_update,
        "should_abort": (should_abort or (lambda: False)),
    }

    # 4) Старт
    try:
        if not hasattr(engine, "start"):
            console.log("[window_focus] у движка нет функции start()")
            console.hud("err", "[window_focus] у движка нет функции start()")
            return False
        cfg = cfg or {}
        return bool(engine.start(ctx_base, cfg))
    except Exception as e:
        console.log(f"[window_focus] ошибка выполнения движка: {e}")
        console.hud("err", f"[window_focus] ошибка выполнения движка: {e}")
        return False
