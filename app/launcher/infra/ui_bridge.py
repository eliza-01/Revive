# app/launcher/infra/ui_bridge.py
from __future__ import annotations
from typing import Any, Dict
import json, threading
from core.state.pool import pool_get
from core.logging import console

class UIBridge:
    """
    Мост: HUD и таймеры. UI-статусы пушим через BaseSection.emit().
    """
    def __init__(self, window, state: Dict[str, Any], hud_window=None):
        self.window = window
        self.state = state
        self.hud_window = hud_window

        if self.hud_window is None:
            raise RuntimeError("UIBridge: HUD window is not attached")

        # Привязка HUD к логгеру и установка языка (никаких фолбэков)
        console.bind(hud_push=self.hud_push)
        lang = str(pool_get(self.state, "config.app_language", "")).strip().lower()
        if not lang:
            raise RuntimeError("UIBridge: app_language is not set in state['config']['app_language']")
        console.set_language(lang)

    # простой планировщик
    def schedule(self, fn, ms: int):
        t = threading.Timer(max(0.0, ms) / 1000.0, fn)
        t.daemon = True
        t.start()

    # HUD: принимает статус отдельно, в JS передаём объект {status, text},
    # но сам HUD окрашивает по status, отображает ТОЛЬКО text.
    def hud_push(self, status: str, text: str):
        if not self.hud_window:
            raise RuntimeError("UIBridge.hud_push: HUD window is not attached")
        payload = {"status": str(status), "text": str(text)}
        js = f"window.ReviveHUD && window.ReviveHUD.push({json.dumps(payload, ensure_ascii=False)})"
        self.hud_window.evaluate_js(js)
