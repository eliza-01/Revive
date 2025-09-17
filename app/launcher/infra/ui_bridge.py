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

        # Параметры ретраев HUD
        self._hud_retry_ms = 300
        self._hud_max_retries = 10

        # Привязка HUD к логгеру и установка языка (никаких фолбэков)
        console.bind(hud_push=self.hud_push)
        lang = str(pool_get(self.state, "config.app_language", "")).strip().lower()
        if not lang:
            raise RuntimeError("UIBridge: app_language is not set in state['config']['app_language']")
        console.set_language(lang)
        # global _UI_SINGLETON
        # _UI_SINGLETON = self

    # #глобал версия на будущее
    # _UI_SINGLETON = None
    #
    # class _UIProxy:
    #     def __getattr__(self, name):
    #         if _UI_SINGLETON is None:
    #             raise RuntimeError("UIBridge не инициализирован. Создаётся в wiring и присваивает синглтон.")
    #         return getattr(_UI_SINGLETON, name)
    #
    # # Прокси-объект, через который можно вызывать ui.schedule(...)
    # ui = _UIProxy()
    # def schedule(fn, ms: int):
    #     """Альтернатива: from ...ui_bridge import schedule; schedule(fn, ms)"""
    #     if _UI_SINGLETON is None:
    #         raise RuntimeError("UIBridge не инициализирован.")
    #     return _UI_SINGLETON.schedule(fn, ms)


    # простой планировщик
    # пример использования:

    # показать и через 3 секунды «погасить» внимание HUD
    # console.hud("att", "Окно без фокуса")
    # ui.schedule(lambda: console.hud("ok", ""), 3000)

    # сдвинуть действие, чтобы дать UI стабилизироваться
    # ui.schedule(lambda: some_quick_refresh(), 150)

    # timer = ui.schedule(do_something, 2000)
    # ... передумали:
    # timer.cancel()

    def schedule(self, fn, ms: int):
        def _wrap():
            try:
                fn()
            except Exception as e:
                # безопасный лог, чтобы таймер не «падал» молча
                from core.logging import console
                console.log(f"[UIBridge.schedule] task error: {e}")

        t = threading.Timer(max(0.0, ms) / 1000.0, _wrap)
        t.daemon = True
        t.start()
        return t  # ← можно сохранить и вызвать t.cancel() при желании

    def _eval_js_safe(self, js: str) -> bool:
        try:
            self.hud_window.evaluate_js(js)
            return True
        except Exception:
            return False

    # HUD: принимает статус отдельно, в JS передаём объект {status, text},
    # но сам HUD окрашивает по status, отображает ТОЛЬКО text.
    def hud_push(self, status: str, text: str, _attempt: int = 0):
        if not self.hud_window:
            return

        # определяем нужный метод и проверку его наличия
        if status == "clear":
            exists_js = "typeof window.ReviveHUD==='object' && typeof window.ReviveHUD.stop_attention==='function'"
            call_js = "window.ReviveHUD.stop_attention()"
        else:
            exists_js = "typeof window.ReviveHUD==='object' && typeof window.ReviveHUD.push==='function'"
            payload = {"status": str(status), "text": str(text)}
            call_js = f"window.ReviveHUD.push({json.dumps(payload, ensure_ascii=False)})"

        # 1) есть ли API?
        try:
            exists = bool(self.hud_window.evaluate_js(exists_js))
        except Exception:
            exists = False

        if not exists:
            # окно ещё не готово — ретраим несколько раз
            if _attempt < self._hud_max_retries:
                self.schedule(lambda: self.hud_push(status, text, _attempt + 1), self._hud_retry_ms)
            else:
                print(f"[HUD-deferred][{status}] {text}")
            return

        # 2) вызвать метод HUD
        try:
            self.hud_window.evaluate_js(call_js)
        except Exception:
            # не молчим — дублируем в stdout
            print(f"[HUD][{status}] {text}")
