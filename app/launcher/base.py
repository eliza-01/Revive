# app/launcher/base.py
from __future__ import annotations
from typing import Any, Dict, Optional
import json

class BaseSection:
    def __init__(self, window, state: Dict[str, Any]):
        self.window = window
        self.s = state

    def emit(self, scope: str, text: str, ok: Optional[bool]):
        payload = {
            "scope": scope,
            "text": text,
            "ok": (True if ok is True else False if ok is False else None)
        }
        # → UI (без записи в пул)
        try:
            self.window.evaluate_js(
                f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})"
            )
        except Exception:
            pass
