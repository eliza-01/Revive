# core/engines/respawn/server/boh/engine.py
# engines/respawn/server/<server>/engine.py
from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Callable, List

from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher import match_in_zone

from .respawn_data import ZONES, TEMPLATES

Point = Tuple[int, int]
Zone = Tuple[int, int, int, int]

DEFAULT_CLICK_THRESHOLD = 0.87
DEFAULT_CONFIRM_TIMEOUT_S = 6.0

# какие шаблоны пробовать для stand_up и в каком порядке
PREFERRED_TEMPLATE_KEYS: List[str] = ["reborn_banner", "death_banner"]


class RespawnEngine:
    """
    Изолированный движок подъёма после смерти (respawn).
    Работает через общий template_matcher.match_in_zone и серверный resolver.
    """

    def __init__(
        self,
        server: str,
        controller,
        is_alive_cb: Optional[Callable[[], bool]] = None,
        click_threshold: float = DEFAULT_CLICK_THRESHOLD,
        confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
        debug: bool = False,
    ):
        self.server = server
        self.controller = controller
        self._is_alive_cb = is_alive_cb or (lambda: True)
        self.click_threshold = float(click_threshold)
        self.confirm_timeout_s = float(confirm_timeout_s)
        self.debug = bool(debug)

    # --- API ---
    def set_server(self, server: str) -> None:
        self.server = server

    def run_stand_up_once(self, window: Dict, lang: str, timeout_ms: int = 14_000) -> bool:
        """
        Сценарий:
          A) Активно кликаем по баннеру/кнопке, пока он виден.
          B) Если баннер пропал — ждём загрузку до 10 сек.
          C) Если не ожили — False.
        """
        # гарантируем фокус окна (если контроллер умеет)
        try:
            if hasattr(self.controller, "focus") and window:
                self.controller.focus(window)
        except Exception:
            pass

        total_deadline = time.time() + max(1, int(timeout_ms)) / 1000.0

        ok = self._click_until_alive_or_banner_gone(window, lang, total_deadline)
        if ok is not None:
            return ok

        load_deadline = time.time() + 10.0
        while time.time() < load_deadline:
            if self._is_alive():
                self._log("[respawn] alive during loading wait")
                return True
            if self._banner_pt(window, lang) is not None:
                ok2 = self._click_until_alive_or_banner_gone(window, lang, load_deadline)
                if ok2 is not None:
                    return ok2
            time.sleep(0.1)

        self._log("[respawn] fallback: still not alive and no banner")
        return False

    # Совместимость со старым именем
    def run_to_village_once(self, window: Dict, lang: str, timeout_ms: int = 14_000) -> bool:
        return self.run_stand_up_once(window, lang, timeout_ms)

    # --- internals ---
    def _banner_pt(self, win: Dict, lang: str) -> Optional[Point]:
        zone_decl = ZONES.get("stand_up")
        if not zone_decl:
            return None
        ltrb = compute_zone_ltrb(win, zone_decl)

        # перебираем шаблоны по приоритету
        for key in PREFERRED_TEMPLATE_KEYS:
            parts = TEMPLATES.get(key)
            if not parts:
                continue
            pt = match_in_zone(
                window=win,
                zone_ltrb=ltrb,
                server=self.server,
                lang=(lang or "rus").lower(),
                template_parts=parts,
                threshold=self.click_threshold,
                engine="respawn",
            )
            if pt is not None:
                return pt
        return None

    def _click(self, x: int, y: int, delay_s: float = 0.40) -> None:
        """
        ЕДИНСТВЕННЫЙ способ клика: через Arduino.
        Движение курсора → пауза → клик (_click_left_arduino).
        Координаты x,y ожидаются в абсолютных экранных координатах.
        """
        try:
            if hasattr(self.controller, "move"):
                self.controller.move(int(x), int(y))
            time.sleep(max(0.0, float(delay_s)))
            if hasattr(self.controller, "_click_left_arduino"):
                self.controller._click_left_arduino()
            else:
                # заплатка на случай альтернативного контроллера
                self.controller.send("l")
        except Exception:
            pass

    def _is_alive(self) -> bool:
        try:
            return bool(self._is_alive_cb())
        except Exception:
            return True  # не блокируемся на ошибке обратного вызова

    def _click_until_alive_or_banner_gone(self, win: Dict, lang: str, phase_deadline: float) -> Optional[bool]:
        """
        Возвращает:
          True  — ожили;
          False — явный фейл (таймаут подтверждения с видимым баннером и исчерпан общий дедлайн);
          None  — баннер исчез (переход к ожиданию загрузки).
        """
        last_click_ts = 0.0
        while time.time() < phase_deadline:
            if self._is_alive():
                self._log("[respawn] alive detected")
                return True

            pt = self._banner_pt(win, lang)
            if pt is None:
                return None  # баннера нет — ждём загрузку

            now = time.time()
            if now - last_click_ts >= 0.6:  # антидребезг
                self._log(f"[respawn] click @ {pt[0]},{pt[1]}")
                self._click(pt[0], pt[1])  # движение + delay + Arduino click
                last_click_ts = now

                confirm_deadline = now + self.confirm_timeout_s
                while time.time() < confirm_deadline:
                    if self._is_alive():
                        self._log("[respawn] alive after click")
                        return True
                    if self._banner_pt(win, lang) is None:
                        return None  # баннер пропал — пошла загрузка
                    time.sleep(0.05)

            time.sleep(0.05)

        self._log("[respawn] phase deadline reached with banner visible")
        return False

    def _log(self, msg: str):
        if self.debug:
            try:
                print(msg)
            except Exception:
                pass


def create_engine(
    server: str,
    controller,
    is_alive_cb: Optional[Callable[[], bool]] = None,
    click_threshold: float = DEFAULT_CLICK_THRESHOLD,
    confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
    debug: bool = False,
) -> RespawnEngine:
    return RespawnEngine(
        server=server,
        controller=controller,
        is_alive_cb=is_alive_cb,
        click_threshold=click_threshold,
        confirm_timeout_s=confirm_timeout_s,
        debug=debug,
    )
