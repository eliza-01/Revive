# core/engines/autofarm/runner.py
from __future__ import annotations
import importlib, os, json, traceback
from typing import Any, Dict, Callable, Optional

# type: on_status(str, ok: Optional[bool]) -> None
def _emit(status_cb: Optional[Callable[[str, Optional[bool]], None]], msg: str, ok: Optional[bool] = None):
    try:
        if callable(status_cb):
            status_cb(msg, ok)
        else:
            print(f"[autofarm] {msg}")
    except Exception:
        print(f"[autofarm] {msg}")

def _zones_paths(server: str):
    AF_ROOT = os.path.join("core", "engines", "autofarm")
    # важно: сначала конкретный сервер, потом общий fallback
    return [
        os.path.join(AF_ROOT, "server", server, "zones.json"),
        os.path.join(AF_ROOT, "server", "common", "zones.json"),
    ]

def _check_files(server: str, on_status):
    # минимальная диагностика перед стартом
    found = False
    for p in _zones_paths(server):
        if os.path.isfile(p):
            found = True
            break
    if not found:
        _emit(on_status, f"[autofarm] zones.json не найден ни в server/{server}, ни в server/common", False)

    # подсказка по темплейтам (не фатально)
    probe_dir = os.path.join("core", "engines", "autofarm", "server", server, "templates")
    if not os.path.isdir(probe_dir):
        _emit(on_status, f"[autofarm] нет каталога templates для сервера: {probe_dir}", None)

def run_autofarm(
    *,
    server: str,
    controller,
    get_window,
    get_language: Callable[[], str],
    on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> bool:
    """
    Универсальный запуск АФ: грузит движок по server и вызывает engine.start(ctx_base, cfg).
    Контекст унифицированный: движок не должен дергать глобалы.
    """
    server = (server or "").lower().strip()
    if not server:
        _emit(on_status, "[autofarm] server не задан", False); return False

    # 1) Импорт сервера
    mod_name = f"core.engines.autofarm.server.{server}.engine"
    try:
        engine = importlib.import_module(mod_name)
    except Exception as e:
        _emit(on_status, f"[autofarm] не найден движок сервера '{server}': {mod_name}: {e}", False)
        _emit(on_status, traceback.format_exc(), False)
        return False

    # 2) Проверка ресурсов
    _check_files(server, on_status)

    # 3) Сбор контекста
    win = None
    try:
        win = get_window() if callable(get_window) else None
    except Exception:
        pass
    if not win:
        _emit(on_status, "[autofarm] окно не найдено", False)
        return False

    language = "eng"
    try:
        language = (get_language() or "eng").lower()
    except Exception:
        pass

    def _status(msg: str, ok: Optional[bool] = None):
        _emit(on_status, msg, ok)

    ctx_base: Dict[str, Any] = {
        "server": server,
        "controller": controller,
        "get_window": lambda: win,           # фиксируем окно на запуск
        "get_language": lambda: language,
        "on_status": _status,
        "should_abort": (should_abort or (lambda: False)),
        # shared flags для движков (если используют)
        "af_current_target_name": None,
        "af_unvisible": False,
    }

    # 4) Старт
    try:
        if not hasattr(engine, "start"):
            _emit(on_status, f"[autofarm] у движка '{server}' нет функции start()", False)
            return False
        cfg = cfg or {}
        _emit(on_status, f"[autofarm] запуск движка '{server}'…", None)
        ok = bool(engine.start(ctx_base, cfg))
        _emit(on_status, f"[autofarm] завершено: {'OK' if ok else 'FAIL'}", True if ok else False)
        return ok
    except Exception as e:
        _emit(on_status, f"[autofarm] ошибка выполнения движка: {e}", False)
        _emit(on_status, traceback.format_exc(), False)
        return False
