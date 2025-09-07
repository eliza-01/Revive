 # core/engines/macros/server/boh/engine.py
from __future__ import annotations
import time
from typing import Any, Dict, Optional, Callable, List

def _emit(cb: Optional[Callable[[str, Optional[bool]], None]], text: str, ok: Optional[bool] = None):
    try:
        (cb or (lambda *_: None))(text, ok)
    except Exception:
        pass

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
    cfg:
      rows: [{key:'1'..'0', cast_s:int<=99, repeat_s:int<=9999}, ...]
    Статусы:
      "Макрос используется (i/N)"
      "Макросы выполнены"
    """
    controller = ctx.get("controller")
    on_status: Callable[[str, Optional[bool]], None] = ctx.get("on_status") or (lambda *_: None)
    should_abort: Callable[[], bool] = ctx.get("should_abort") or (lambda: False)

    rows = _norm_rows(cfg.get("rows"))
    total = len(rows)

    if total <= 0:
        _emit(on_status, "[macros] нет строк для выполнения", False)
        return False

    all_ok = True

    for i, row in enumerate(rows, start=1):
        if should_abort():
            _emit(on_status, "[macros] прервано пользователем", None)
            return False

        key = str(row.get("key", "1"))[:1]
        cast_s = int(row.get("cast_s", 0))

        # прогресс
        _emit(on_status, f"Макрос используется ({i}/{total})", None)

        # отправляем цифру в Arduino
        try:
            controller.send(key)
        except Exception:
            all_ok = False

        # “кастуется”
        if cast_s > 0:
            end = time.time() + cast_s
            while time.time() < end:
                if should_abort():
                    _emit(on_status, "[macros] прервано пользователем", None)
                    return False
                time.sleep(0.05)

    _emit(on_status, "Макросы выполнены", all_ok)
    return bool(all_ok)