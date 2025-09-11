# core/engines/autofarm/runner.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, List
import importlib

def run_autofarm(
    server: str,
    controller: Any,
    get_window: Callable[[], Optional[Dict]],
    get_language: Callable[[], str],
    on_status: Callable[[str, Optional[bool]], None],
    cfg: Dict[str, Any],
    should_abort: Callable[[], bool],
) -> bool:
    """
    Одноразовый прогон автофарма. Здесь только подготовка и вызов
    server-движка core.engines.autofarm.server.<server>.engine.start(ctx, cfg).
    """
    on_status("Автофарм: запуск", None)

    # --- нормализация конфига (ровно как в сервисе) --------------------------
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
            "key":      (str((s or {}).get("key", "1"))[:1] or "1"),
            "slug":     ((s or {}).get("slug", "") or ""),
            "cast_ms":  max(0, _norm_int((s or {}).get("cast_ms", 0))),
        })

    cfg = {
        "mode":        mode,
        "profession":  (raw.get("profession") or "").strip(),
        "zone":        zone,
        "skills":      skills,
        "monsters":    list(raw.get("monsters") or []),
    }

    if not zone or not skills:
        on_status("Нет зоны или атакующих скиллов", False)
        return False

    # --- загрузка серверного движка и запуск ---------------------------------
    mod_name = f"core.engines.autofarm.server.{(server or 'boh').lower()}.engine"
    try:
        mod = importlib.import_module(mod_name)
        start = getattr(mod, "start", None)
        if not callable(start):
            on_status(f"Движок '{mod_name}' без start()", False)
            return False
    except Exception as e:
        on_status(f"Импорт движка не удался: {e}", False)
        return False

    ctx = {
        "server":        (server or "boh").lower(),
        "controller":    controller,
        "get_window":    get_window,
        "get_language":  get_language,
        "on_status":     on_status,
        "should_abort":  should_abort,
    }

    # теперь реально работаем — внутри start() вся логика поиска/атаки
    ok = bool(start(ctx, cfg))
    return ok
