from __future__ import annotations
from typing import Any, Callable, Dict, Optional, List
import time

from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow
from core.logging import console


def _press_key(controller, server, get_window, get_language, key_digit: str) -> bool:
    ctx = FlowCtx(
        server=server,
        controller=controller,
        get_window=get_window,
        get_language=get_language,
        zones={}, templates={}, extras={}
    )
    ex = FlowOpExecutor(ctx)  # лог в console.log
    flow = [{"op": "send_arduino", "cmd": str(key_digit)[:2], "delay_ms": 0}]
    return bool(run_flow(flow, ex))


def run_macros(
    server: str,
    controller: Any,
    get_window: Callable[[], Optional[Dict]],
    get_language: Callable[[], str],
    cfg: Dict[str, Any],
    should_abort: Callable[[], bool],
) -> bool:
    """
    Одноразовый прогон макросов «сверху вниз».
    cfg = {"rows": [{"key": "1","cast_s": 2,"repeat_s": 0}, ...]}
    """
    rows: List[Dict[str, Any]] = list(cfg.get("rows") or [])
    if not rows:
        console.log("[macros] нет макросов для выполнения")
        return False

    total = len(rows)
    for i, row in enumerate(rows, 1):
        if should_abort():
            return False

        key = (str(row.get("key", "1"))[:1] or "1")
        cast_s = max(0, int(float(row.get("cast_s", 0))))
        repeat_s = max(0, int(float(row.get("repeat_s", 0))))  # 0 → без повтора

        console.log(f"[macros] используется ({i}/{total}) key={key}, cast={cast_s}s, repeat={repeat_s}s")

        if not _press_key(controller, server, get_window, get_language, key):
            console.log(f"[macros] не удалось нажать {key}")
            return False

        end = time.time() + cast_s
        while time.time() < end:
            if should_abort():
                return False
            time.sleep(0.05)

    console.log("[macros] макросы выполнены")
    return True
