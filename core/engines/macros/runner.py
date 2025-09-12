# core/engines/macros/runner.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, List
import time
from core.logging import console

# используем архивный движок шагов, как в примере _press_key
from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow


def _press_key(controller, server, get_window, get_language, key_digit: str) -> bool:
    """
    Нажимает цифру через Arduino. Строго одна команда, без задержек.
    """
    ctx = FlowCtx(
        server=server,
        controller=controller,
        get_window=get_window,
        get_language=get_language,
        zones={}, templates={}, extras={}
    )
    ex = FlowOpExecutor(ctx)  # без on_status
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
    ОЖИДАЕТ cfg = {"rows": [{"key": "1","cast_s": 2,"repeat_s": 0}, ...]}
    """
    rows: List[Dict[str, Any]] = list(cfg.get("rows") or [])
    if not rows:
        console.hud("err", "Нет макросов для выполнения")
        return False

    total = len(rows)
    for i, row in enumerate(rows, 1):
        if should_abort():
            return False

        key = (str(row.get("key", "1"))[:1] or "1")
        cast_s = max(0, int(float(row.get("cast_s", 0))))
        repeat_s = max(0, int(float(row.get("repeat_s", 0))))

        # статус
        console.hud("ok", f"Макрос используется ({i}/{total})")

        # нажимаем кнопку
        if not _press_key(controller, server, get_window, get_language, key):
            console.hud("err", f"Не удалось нажать {key}")
            return False

        # ждём «кастуется»
        end = time.time() + cast_s
        while time.time() < end:
            if should_abort():
                return False
            time.sleep(0.05)

    console.hud("succ", "Макросы выполнены")
    return True
