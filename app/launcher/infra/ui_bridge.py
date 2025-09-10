# app/launcher/infra/ui_bridge.py
from __future__ import annotations
from typing import Any, Dict, Optional
import json, threading
from core.state.pool import pool_write, pool_get

class UIBridge:
    """
    Единая обвязка для HUD, статусов в UI и таймеров.
    """
    def __init__(self, window, state: Dict[str, Any], hud_window=None):
        self.window = window
        self.state = state
        self.hud_window = hud_window

    # простой планировщик (как раньше schedule)
    def schedule(self, fn, ms: int):
        t = threading.Timer(max(0.0, ms) / 1000.0, fn)
        t.daemon = True
        t.start()

    # HUD: вывести строку
    def hud_push(self, text: str):
        if not self.hud_window:
            return
        try:
            js = f"window.ReviveHUD && window.ReviveHUD.push({json.dumps(str(text))})"
            self.hud_window.evaluate_js(js)
        except Exception as e:
            print(f"[HUD] eval error: {e}")

    # лог + HUD
    def log(self, msg: str):
        try:
            print(msg)
        finally:
            self.hud_push(msg)

    # лог для повторов макросов (в точности как было)
    def log_ok(self, msg: str, ok: Optional[bool] = None):
        try:
            print(f"[MACROS] {msg}")
        finally:
            self.hud_push(f"Повтор макроса: {msg}")

    # статусы для UI + запись в пул
    def ui_emit(self, scope: str, text: str, ok: Optional[bool]):
        payload = {"scope": scope, "text": text, "ok": (True if ok is True else False if ok is False else None)}
        pool_write(self.state, f"ui_status.{scope}", {"text": text, "ok": payload["ok"]})
        try:
            self.window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})")
        except Exception:
            pass
