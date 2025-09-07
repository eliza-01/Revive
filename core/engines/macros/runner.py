# core/engines/macros/runner.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, List
import time

# используем ваш архивный движок шагов, как в примере _press_key
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
    ex = FlowOpExecutor(ctx, on_status=lambda *_: None)
    flow = [{"op": "send_arduino", "cmd": str(key_digit)[:2], "delay_ms": 0}]
    return bool(run_flow(flow, ex))


def run_macros(
    server: str,
    controller: Any,
    get_window: Callable[[], Optional[Dict]],
    get_language: Callable[[], str],
    on_status: Callable[[str, Optional[bool]], None],
    cfg: Dict[str, Any],
    should_abort: Callable[[], bool],
) -> bool:
    """
    Одноразовый прогон макросов «сверху вниз».

    ОЖИДАЕТ cfg = {"rows": [{"key": "1","cast_s": 2,"repeat_s": 0}, ...]}
    - key: цифра '0'..'9' (нажимаем через Arduino)
    - cast_s: длительность «кастуется», секунды
    - repeat_s: «повторять через, сек». В ЭТОМ одноразовом раннере ПОВТОРА НЕТ.
                 Явное правило: repeat_s == 0  → НЕ повторять.
                 (Повторы реализуются уже во фоновом сервисе, если/когда он появится.)
    """
    rows: List[Dict[str, Any]] = list(cfg.get("rows") or [])
    if not rows:
        on_status("Нет макросов для выполнения", False)
        return False

    total = len(rows)
    for i, row in enumerate(rows, 1):
        if should_abort():
            return False

        key = (str(row.get("key", "1"))[:1] or "1")
        cast_s = max(0, int(float(row.get("cast_s", 0))))
        repeat_s = max(0, int(float(row.get("repeat_s", 0))))  # ← 0 означает «НЕ повторять»

        # статус для HUD/оркестратора
        on_status(f"Макрос используется ({i}/{total})", None)

        # нажимаем кнопку
        if not _press_key(controller, server, get_window, get_language, key):
            on_status(f"Не удалось нажать {key}", False)
            return False

        # ждём «кастуется»
        end = time.time() + cast_s
        while time.time() < end:
            if should_abort():
                return False
            time.sleep(0.05)

        # В ЭТОМ одноразовом прогоне НЕ делаем повтор даже если repeat_s > 0.
        # Повторять здесь — ответственность фонового сервиса (будет учитывать: repeat_s > 0 ⇒ планировать; == 0 ⇒ нет).

    on_status("Макросы выполнены", True)
    return True
