# core/engines/macros/server/boh_x500/engine.py
from __future__ import annotations
import time
from typing import Any, Dict, Optional, Callable, List
from core.logging import console

def _norm_rows(rows: Any) -> List[Dict[str, int | str]]:
    out: List[Dict[str, int | str]] = []
    for r in rows or []:
        try:
            key = str((r or {}).get("key", "1"))[:1]
            if key not in "0123456789":
                key = "1"
            cast_s = int(float((r or {}).get("cast_s", 0)))
            repeat_s = int(float((r or {}).get("repeat_s", 0)))
        except Exception:
            key, cast_s, repeat_s = "1", 0, 0
        cast_s = max(0, min(99, cast_s))
        repeat_s = max(0, min(9999, repeat_s))
        out.append({"key": key, "cast_s": cast_s, "repeat_s": repeat_s})
    return out or [{"key": "1", "cast_s": 0, "repeat_s": 0}]

def start(ctx: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """
    Одноразовый прогон списка макросов (без расписаний).
    cfg: rows: [{key, cast_s, repeat_s}, ...]
    """
    controller = ctx.get("controller")
    should_abort: Callable[[], bool] = ctx.get("should_abort") or (lambda: False)

    rows = _norm_rows(cfg.get("rows"))
    total = len(rows)

    if total <= 0:
        console.hud("err", "[macros] нет строк для выполнения")
        return False

    all_ok = True

    for i, row in enumerate(rows, start=1):
        if should_abort():
            console.hud("ok", "[macros] прервано пользователем")
            return False

        key = str(row.get("key", "1"))[:1]
        cast_s = int(row.get("cast_s", 0))

        console.hud("ok", f"Макрос используется ({i}/{total})")

        try:
            controller.send(key)
        except Exception:
            all_ok = False

        if cast_s > 0:
            end = time.time() + cast_s
            while time.time() < end:
                if should_abort():
                    console.hud("ok", "[macros] прервано пользователем")
                    return False
                time.sleep(0.05)

    console.hud("succ", "Макросы выполнены")
    return bool(all_ok)
