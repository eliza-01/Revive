# core/engines/autofarm/runner.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, List
import importlib

from core.logging import console


def run_autofarm(
    server: str,
    controller: Any,
    get_window: Callable[[], Optional[Dict]],
    get_language: Callable[[], str],
    cfg: Dict[str, Any],
    should_abort: Callable[[], bool],
) -> bool:
    """
    Одноразовый прогон автофарма.
    Здесь только подготовка и вызов server-движка:
      core.engines.autofarm.server.<server>.engine.start(ctx, cfg)
    """
    try:
        console.hud("succ", "[AUTOFARM] запуск")
        console.log("[autofarm] run_autofarm: start")
    except Exception:
        pass

    # --- нормализация конфига ---
    raw = dict(cfg or {})

    def _norm_int(x, d=0):
        try:
            return int(float(x))
        except Exception:
            return d

    mode = (raw.get("mode") or "auto").strip().lower()
    zone = (raw.get("zone") or "").strip()

    skills: List[Dict[str, Any]] = []
    for s in (raw.get("skills") or []):
        skills.append({
            "key":     (str((s or {}).get("key", "1"))[:1] or "1"),
            "slug":    ((s or {}).get("slug", "") or ""),
            "cast_ms": max(0, _norm_int((s or {}).get("cast_ms", 0))),
        })

    cfg_norm = {
        "mode":       mode,
        "profession": (raw.get("profession") or "").strip(),
        "zone":       zone,
        "skills":     skills,
        "monsters":   list(raw.get("monsters") or []),
    }

    # обязательные проверки (без фолбэков)
    if not server:
        console.hud("err", "[AUTOFARM] server не задан")
        console.log("[autofarm] error: server is empty")
        return False

    if not zone or not skills:
        console.hud("err", "[AUTOFARM] нет зоны или атакующих скиллов")
        console.log("[autofarm] error: missing zone or skills")
        return False

    # --- загрузка серверного движка и старт ---
    mod_name = f"core.engines.autofarm.server.{server.lower()}.engine"
    try:
        mod = importlib.import_module(mod_name)
    except Exception as e:
        console.hud("err", f"[AUTOFARM] импорт движка не удался: {e}")
        console.log(f"[autofarm] import fail {mod_name}: {e}")
        return False

    start = getattr(mod, "start", None)
    if not callable(start):
        console.hud("err", f"[AUTOFARM] в модуле нет start(): {mod_name}")
        console.log(f"[autofarm] start() missing in {mod_name}")
        return False

    ctx = {
        "server":       server.lower(),
        "controller":   controller,
        "get_window":   get_window,
        "get_language": get_language,
        "should_abort": should_abort,
    }

    ok = bool(start(ctx, cfg_norm))
    return ok
