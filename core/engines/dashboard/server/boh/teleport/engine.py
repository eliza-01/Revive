# core/engines/dashboard/server/boh/teleport/engine.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, List

from core.logging import console
from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher_2 import match_key_in_zone_single

from ..dashboard_data import (
    ZONES,
    TEMPLATES,
    TELEPORT_CATEGORIES,
    TELEPORT_TOWNS,
    TELEPORT_VILLAGES,
    TELEPORT_LOCATIONS,
)


class TeleportEngine:
    """
    Низкоуровневые операции вкладки Teleport:
      - открыть кнопку Teleport в Dashboard и дождаться init
      - открыть категорию (towns/villages) и дождаться *_init
      - открыть «контейнер» (город/деревню) и дождаться <Container>_init
      - клик по локации (по карте TELEPORT_LOCATIONS)
    """

    def __init__(self, state: Dict[str, Any], server: str, controller: Any, get_window, get_language):
        self.s = state
        self.server = (server or "").lower()
        self.controller = controller
        self.get_window = get_window
        self.get_language = get_language

    # --- utils ------------------------------------------------------------

    def _hud(self, status: str, text: str):
        try:
            console.hud(status, text)
        except Exception:
            console.log(f"[HUD/{status}] {text}")

    def _lang(self) -> str:
        try:
            return (self.get_language() or "rus").lower()
        except Exception:
            return "rus"

    def _win(self) -> Optional[Dict[str, Any]]:
        try:
            return self.get_window() or None
        except Exception:
            return None

    def _zone_ltrb(self, win: Dict, name: str) -> Tuple[int, int, int, int]:
        decl = ZONES.get(name, ZONES.get("fullscreen", {"fullscreen": True}))
        l, t, r, b = compute_zone_ltrb(win, decl)
        return (int(l), int(t), int(r), int(b))

    def _click(self, x: int, y: int, *, hover_delay_s: float = 0.20, post_delay_s: float = 0.20) -> None:
        try:
            if hasattr(self.controller, "move"):
                self.controller.move(int(x), int(y))
            import time as _t
            _t.sleep(max(0.0, float(hover_delay_s)))
            if hasattr(self.controller, "_click_left_arduino"):
                self.controller._click_left_arduino()
            else:
                self.controller.send("l")
            _t.sleep(max(0.0, float(post_delay_s)))
        except Exception:
            pass

    def _match_key_center(self, win: Dict, parts: List[str], thr: float = 0.87) -> Optional[Tuple[int, int]]:
        pt = match_key_in_zone_single(
            window=win,
            zone_ltrb=self._zone_ltrb(win, "fullscreen"),
            server=self.server,
            lang=self._lang(),
            template_parts=parts or [],
            threshold=thr,
            engine="dashboard",
        )
        return pt

    # --- state ------------------------------------------------------------

    def is_open(self, thr: float = 0.87) -> bool:
        """Teleport-вкладка открыта, если виден ключ 'dashboard_teleport_init'."""
        win = self._win()
        if not win:
            return False
        parts = TEMPLATES.get("dashboard_teleport_init")
        if not parts:
            return False
        return self._match_key_center(win, parts, thr) is not None

    def open_tab(self, thr_btn: float = 0.85, thr_init: float = 0.85, timeout_s: float = 2.5) -> bool:
        """Клик по кнопке Teleport и ожидание 'dashboard_teleport_init'."""
        win = self._win()
        if not win:
            self._hud("err", "[dashboard/teleport] окно игры не найдено")
            return False

        if self.is_open(thr=thr_init):
            return True

        btn = TEMPLATES.get("dashboard_teleport_button")
        init = TEMPLATES.get("dashboard_teleport_init")
        if not btn or not init:
            self._hud("err", "[dashboard/teleport] нет шаблонов кнопки/инициализации")
            return False

        pt = self._match_key_center(win, btn, thr_btn)
        if not pt:
            self._hud("err", "[dashboard/teleport] кнопка Teleport не найдена")
            return False

        self._click(pt[0], pt[1])

        import time as _t
        end = _t.time() + max(0.5, float(timeout_s))
        while _t.time() < end:
            if self._match_key_center(win, init, thr_init):
                self._hud("ok", "[dashboard] раздел Teleport открыт")
                return True
            _t.sleep(0.05)

        self._hud("err", "[dashboard/teleport] раздел не открылся")
        return False

    # --- categories / containers -----------------------------------------

    def open_category(self, category: str, thr_btn: float = 0.85, thr_init: float = 0.85, timeout_s: float = 2.5) -> bool:
        win = self._win()
        if not win:
            return False
        category = (category or "").strip()

        # карта категорий → кнопка
        parts_btn = TELEPORT_CATEGORIES.get(category)
        if not parts_btn:
            self._hud("err", f"[teleport] неизвестная категория: {category}")
            return False

        # init-ключ для выбранной категории
        if category == "towns":
            parts_init = TELEPORT_TOWNS.get("towns_init")
        elif category == "villages":
            parts_init = TELEPORT_VILLAGES.get("villages_init")
        else:
            parts_init = None

        if not parts_init:
            self._hud("err", f"[teleport] нет шаблона init для категории '{category}'")
            return False

        # если уже в разделе категории — готово
        if self._match_key_center(win, parts_init, thr_init):
            return True

        pt = self._match_key_center(win, parts_btn, thr_btn)
        if not pt:
            self._hud("err", f"[teleport] кнопка категории '{category}' не найдена")
            return False

        self._click(pt[0], pt[1])

        import time as _t
        end = _t.time() + max(0.5, float(timeout_s))
        while _t.time() < end:
            if self._match_key_center(win, parts_init, thr_init):
                self._hud("ok", f"[teleport] открыт раздел '{category}'")
                return True
            _t.sleep(0.05)

        self._hud("err", f"[teleport] раздел '{category}' не открылся")
        return False

    def _ensure_container_open(self, category: str, container: str,
                               thr_btn: float = 0.85, thr_init: float = 0.85, timeout_s: float = 2.5) -> bool:
        """
        Убедиться, что открыт подраздел (например, towns → Goddard).
        Для towns: TELEPORT_TOWNS['Goddard'] → ожидать TELEPORT_TOWNS['Goddard_init'].
        Для villages: аналогично TELEPORT_VILLAGES.
        """
        win = self._win()
        if not win:
            return False
        category = (category or "").strip()
        container = (container or "").strip()

        if category == "towns":
            btn_parts = TELEPORT_TOWNS.get(container)
            init_parts = TELEPORT_TOWNS.get(f"{container}_init")
        elif category == "villages":
            btn_parts = TELEPORT_VILLAGES.get(container)
            init_parts = TELEPORT_VILLAGES.get(f"{container}_init")
        else:
            btn_parts = None
            init_parts = None

        if not init_parts:
            # иногда контейнера как отдельной страницы нет — считаем, что уже «открыт»
            return True

        # уже открыт?
        if self._match_key_center(win, init_parts, thr_init):
            return True

        if not btn_parts:
            self._hud("err", f"[teleport] нет кнопки контейнера '{container}' для категории '{category}'")
            return False

        pt = self._match_key_center(win, btn_parts, thr_btn)
        if not pt:
            self._hud("err", f"[teleport] кнопка контейнера '{container}' не найдена")
            return False

        self._click(pt[0], pt[1])

        import time as _t
        end = _t.time() + max(0.5, float(timeout_s))
        while _t.time() < end:
            if self._match_key_center(win, init_parts, thr_init):
                return True
            _t.sleep(0.05)

        self._hud("err", f"[teleport] контейнер '{container}' не открылся")
        return False

    # --- locations --------------------------------------------------------

    @staticmethod
    def _infer_cat_and_container_for_location(location: str) -> Tuple[Optional[str], Optional[str]]:
        """
        По TELEPORT_LOCATIONS выясняем категорию (towns/villages) и «контейнер» (город/деревня),
        на странице которого лежит нужная локация.
        parts = ["<lang>", "teleport", <cat>, <container>, ...]
        """
        parts = TELEPORT_LOCATIONS.get(location)
        if not parts or len(parts) < 4:
            return None, None
        cat = parts[2]
        container = parts[3]
        return (cat, container)

    def click_location(self, location: str, thr_btn: float = 0.85) -> bool:
        """
        Кликает по локации. При необходимости:
          - переключает категорию,
          - открывает нужный контейнер (город/деревню).
        """
        win = self._win()
        if not win:
            return False
        location = (location or "").strip()

        parts = TELEPORT_LOCATIONS.get(location)
        if not parts:
            self._hud("err", f"[teleport] неизвестная локация: {location}")
            return False

        cat, container = self._infer_cat_and_container_for_location(location)
        if not cat:
            self._hud("err", f"[teleport] не удалось вывести категорию/контейнер для '{location}'")
            return False

        # открыть категорию
        if not self.open_category(cat):
            return False

        # открыть контейнер (страницу города/деревни), если требуется
        if container and not self._ensure_container_open(cat, container):
            return False

        # клик по самой локации
        pt = self._match_key_center(win, parts, thr_btn)
        if not pt:
            self._hud("err", f"[teleport] кнопка локации '{location}' не найдена")
            return False

        self._click(pt[0], pt[1])
        self._hud("succ", f"[teleport] клик по '{location}'")
        return True
