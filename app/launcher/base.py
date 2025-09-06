# app/launcher/base.py
from __future__ import annotations
import json

class BaseSection:
    """
    Базовый класс секции.
    s — общий словарь состояния лаунчера (shared context).
    window — webview.Window (нужен для evaluate_js).
    """
    def __init__(self, window, sys_state: dict):
        self.window = window
        self.s = sys_state

    def emit(self, scope: str, text: str, ok: bool | None):
        """Проброс статуса в UI и кэш последнего статуса."""
        payload = {
            "scope": scope,
            "text": text,
            "ok": True if ok is True else False if ok is False else None
        }
        self.s.setdefault("_last_status", {})[scope] = payload
        js = f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})"
        try:
            self.window.evaluate_js(js)
        except Exception:
            pass

    def expose(self) -> dict:
        """Вернуть API-методы секции для window.expose(...)."""
        return {}
