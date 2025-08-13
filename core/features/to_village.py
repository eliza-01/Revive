# core/features/to_village.py
from __future__ import annotations
import importlib
import time
from typing import Callable, Optional, Dict, Tuple

from core.vision.matching.template_matcher import match_in_zone

class ToVillage:
    """
    Нажимает «В деревню» после смерти.

    Поведение:
      1) Если кнопка видна — кликаем и продолжаем кликать, пока она видна,
         параллельно проверяем is_alive(). Как только alive → True, успех.
      2) Если кнопка исчезла — считаем, что идёт загрузка. Ждём до 10 секунд.
         В ожидании если кнопка снова появилась — снова кликаем.
      3) Если по таймаутам не стали живыми и кнопки нет — возвращаем False (заглушка).
    """

    def __init__(
            self,
            controller,
            server: str,
            get_window: Callable[[], Optional[Dict]],
            get_language: Callable[[], str],
            click_threshold: float = 0.87,
            debug: bool = False,
            is_alive: Optional[Callable[[], bool]] = None,
            confirm_timeout_s: float = 6.0,  # локальный таймаут подтверждения после клика
    ):
        self.controller = controller
        self.server = server
        self._get_window = get_window
        self._get_language = get_language
        self.click_threshold = float(click_threshold)
        self.debug = bool(debug)
        self._is_alive_cb = is_alive or (lambda: True)
        self.confirm_timeout_s = float(confirm_timeout_s)

        self._zones: Dict[str, object] = {}
        self._templates: Dict[str, list] = {}
        self._load_cfg()

    # ---------- public ----------
    def set_server(self, server: str):
        self.server = server
        self._load_cfg()

    def run_once(self, timeout_ms: int = 4000) -> bool:
        win = self._get_window() or {}
        if not win:
            self._log("[to_village] no window")
            return False

        total_deadline = time.time() + max(0.001, timeout_ms) / 1000.0

        # Фаза A: активно кликаем, пока кнопка видна
        ok = self._click_until_alive_or_button_gone(win, total_deadline)
        if ok is not None:
            return ok  # True/False

        # Фаза B: кнопки нет — считаем, что загрузка/переход. Ждём до 10 сек.
        load_deadline = time.time() + 10.0
        while time.time() < load_deadline:
            # если ожили — успех
            if self._is_alive():
                self._log("[to_village] alive during loading wait")
                return True

            # если кнопка снова появилась — возвращаемся к активным кликам
            if self._button_pt(win) is not None:
                ok2 = self._click_until_alive_or_button_gone(win, load_deadline)
                if ok2 is not None:
                    return ok2
                # если вернулись None — кнопка опять исчезла, продолжаем ждать
            time.sleep(0.1)

        # Фаза C: заглушка. Кнопки нет и не ожили по таймауту ожидания загрузки.
        self._log("[to_village] fallback: still not alive and no button")
        return False

    # ---------- internals ----------
    def _load_cfg(self):
        try:
            mod = importlib.import_module(f"core.servers.{self.server}.zones.respawn")
            self._zones = getattr(mod, "ZONES", {})
            self._templates = getattr(mod, "TEMPLATES", {})
            if self.debug:
                print(f"[to_village] cfg loaded for {self.server}")
        except Exception as e:
            print(f"[to_village] cfg load error: {e}")
            self._zones, self._templates = {}, {}

    def _lang(self) -> str:
        try:
            return (self._get_language() or "rus").lower()
        except Exception:
            return "rus"

    def _zone_ltrb(self, win: Dict, zone_decl) -> Tuple[int, int, int, int]:
        if isinstance(zone_decl, tuple) and len(zone_decl) == 4:
            return tuple(map(int, zone_decl))
        if isinstance(zone_decl, dict):
            ww, wh = int(win.get("width", 0)), int(win.get("height", 0))
            if zone_decl.get("fullscreen"):
                return (0, 0, ww, wh)
            if zone_decl.get("centered"):
                w, h = int(zone_decl["width"]), int(zone_decl["height"])
                l = ww // 2 - w // 2
                t = wh // 2 - h // 2
                return (l, t, l + w, t + h)
            l = int(zone_decl.get("left", 0))
            t = int(zone_decl.get("top", 0))
            w = int(zone_decl.get("width", 0))
            h = int(zone_decl.get("height", 0))
            return (l, t, l + w, t + h)
        return (0, 0, int(win.get("width", 0)), int(win.get("height", 0)))

    def _button_pt(self, win: Dict):
        zone = self._zones.get("to_village")
        parts = self._templates.get("to_village")
        if not zone or not parts:
            return None
        ltrb = self._zone_ltrb(win, zone)
        return match_in_zone(win, ltrb, self.server, self._lang(), parts, self.click_threshold)

    def _click(self, x: int, y: int):
        try:
            self.controller.send(f"click:{x},{y}")
        except Exception:
            pass

    def _is_alive(self) -> bool:
        try:
            return bool(self._is_alive_cb())
        except Exception:
            return True  # не блокируемся на ошибке обратного вызова

    def _click_until_alive_or_button_gone(self, win: Dict, phase_deadline: float) -> Optional[bool]:
        """
        Возвращает:
          True  — ожили;
          False — явный фейл (таймаут подтверждения с видимой кнопкой и исчерпан общий дедлайн);
          None  — кнопка исчезла (переход к ожиданию загрузки).
        """
        last_click_ts = 0.0
        while time.time() < phase_deadline:
            # если ожили — успех
            if self._is_alive():
                self._log("[to_village] alive detected")
                return True

            pt = self._button_pt(win)
            if pt is None:
                # кнопки нет — выходим в ожидание загрузки
                return None

            # если видна — кликаем, но не чаще антидребезга
            now = time.time()
            if now - last_click_ts >= 0.6:
                self._log(f"[to_village] click @ {pt[0]},{pt[1]}")
                self._click(pt[0], pt[1])
                last_click_ts = now

                # короткое подтверждение: ждём alive, но не дольше confirm_timeout_s
                confirm_deadline = now + self.confirm_timeout_s
                while time.time() < confirm_deadline:
                    if self._is_alive():
                        self._log("[to_village] alive after click")
                        return True
                    # если кнопка пропала — отдаём None, перейдём к ожиданию загрузки
                    if self._button_pt(win) is None:
                        return None
                    time.sleep(0.05)

            time.sleep(0.05)

        # общий дедлайн исчерпан, кнопка была видна, но не ожили
        self._log("[to_village] phase deadline reached with button visible")
        return False

    def _log(self, msg: str):
        if self.debug:
            try:
                print(msg)
            except Exception:
                pass
