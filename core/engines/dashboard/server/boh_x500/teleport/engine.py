# core/engines/dashboard/server/boh/teleport/engine.py
from __future__ import annotations
import time
from typing import Any, Dict, Optional, Tuple, List

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
    Низкоуровневые операции вкладки Teleport (немой движок):
      - переход на вкладку
      - открытие категории (towns|villages)
      - открытие контейнера города (если требуется)
      - клик локации (опц. Esc перед кликом)
      - подтверждение удачного старта (dashboard исчез)
    Предполагается, что Dashboard уже открыт.
    """

    def __init__(self, server: str, controller: Any, get_window, get_language):
        self.server = (server or "").lower()
        self.controller = controller
        self.get_window = get_window
        self.get_language = get_language

    # --- utils ------------------------------------------------------------

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

    def _zone(self, name: str) -> Tuple[int, int, int, int]:
        win = self._win()
        if not win:
            return (0, 0, 0, 0)
        decl = ZONES.get(name, ZONES.get("fullscreen", {"fullscreen": True}))
        l, t, r, b = compute_zone_ltrb(win, decl)
        return (int(l), int(t), int(r), int(b))

    def _visible(self, tpl_key: str, zone_name: str = "fullscreen", thr: float = 0.87) -> bool:
        win = self._win()
        if not win:
            return False
        parts = TEMPLATES.get(tpl_key)
        if not parts:
            return False
        return match_key_in_zone_single(
            window=win,
            zone_ltrb=self._zone(zone_name),
            server=self.server,
            lang=self._lang(),
            template_parts=parts,
            threshold=thr,
            engine="dashboard",
        ) is not None

    def _click_at(self, x: int, y: int, *, hover_delay_s: float = 0.20, post_delay_s: float = 0.20) -> None:
        try:
            if hasattr(self.controller, "move"):
                self.controller.move(int(x), int(y))
            time.sleep(max(0.0, float(hover_delay_s)))
            if hasattr(self.controller, "_click_left_arduino"):
                self.controller._click_left_arduino()
            else:
                self.controller.send("l")
            time.sleep(max(0.0, float(post_delay_s)))
        except Exception:
            pass

    def _click_template(
        self,
        parts: List[str],
        zone: str = "fullscreen",
        thr: float = 0.86,
        timeout_s: float = 2.5,
    ) -> bool:
        """Как в respawn: сперва матч, потом явный клик по найденной точке."""
        win = self._win()
        if not win or not parts:
            return False
        end = time.time() + max(0.2, timeout_s)
        while time.time() < end:
            pt = match_key_in_zone_single(
                window=win,
                zone_ltrb=self._zone(zone),
                server=self.server,
                lang=self._lang(),
                template_parts=parts,
                threshold=thr,
                engine="dashboard",
            )
            if pt:
                self._click_at(pt[0], pt[1], hover_delay_s=0.20, post_delay_s=0.20)
                return True
            time.sleep(0.05)
        return False

    def _press_esc(self, delay_s: float = 0.10):
        try:
            self.controller.send("esc")
        except Exception:
            pass
        if delay_s > 0:
            time.sleep(delay_s)

    # --- actions ----------------------------------------------------------

    def open_tab(self, *, thr_btn: float = 0.86, thr_init: float = 0.86, timeout_s: float = 2.5) -> bool:
        """Клик по кнопке Teleport и ожидание инициализации вкладки."""
        btn = TEMPLATES.get("dashboard_teleport_button")
        init = TEMPLATES.get("dashboard_teleport_init")
        if not (btn and init):
            return False
        if not self._click_template(btn, "fullscreen", thr_btn, timeout_s):
            return False

        # дождаться init вкладки
        win = self._win()
        if not win:
            return False
        end = time.time() + timeout_s
        while time.time() < end:
            if match_key_in_zone_single(
                window=win,
                zone_ltrb=self._zone("fullscreen"),
                server=self.server,
                lang=self._lang(),
                template_parts=init,
                threshold=thr_init,
                engine="dashboard",
            ):
                return True
            time.sleep(0.05)
        return False

    def open_category(self, cat: str, *, thr_btn: float = 0.86, timeout_s: float = 2.5) -> bool:
        """towns/villages → клик + ожидание *_init."""
        cat = (cat or "").strip().lower()
        if cat not in TELEPORT_CATEGORIES:
            return False

        # клик по плитке категории
        parts_cat = TELEPORT_CATEGORIES.get(cat)
        parts_cat = [self._lang() if p == "<lang>" else p for p in (parts_cat or [])]
        if not self._click_template(parts_cat, "fullscreen", thr_btn, timeout_s):
            return False

        # ожидание init раздела
        init_key = "towns_init" if cat == "towns" else "villages_init"
        init_map = TELEPORT_TOWNS if cat == "towns" else TELEPORT_VILLAGES
        parts_init = init_map.get(init_key)
        parts_init = [self._lang() if p == "<lang>" else p for p in (parts_init or [])]

        win = self._win()
        end = time.time() + timeout_s
        while time.time() < end:
            if match_key_in_zone_single(
                window=win,
                zone_ltrb=self._zone("fullscreen"),
                server=self.server,
                lang=self._lang(),
                template_parts=parts_init,
                threshold=0.86,
                engine="dashboard",
            ):
                return True
            time.sleep(0.05)
        return False

    def _ensure_container_for_location(self, loc: str, cat: str, *, thr: float = 0.86, timeout_s: float = 2.5) -> bool:
        """
        Для towns: перед кликом по локации нужно войти в город-контейнер.
        Определяем по пути в TELEPORT_LOCATIONS[loc] имя города и кликаем его + ждём *_init.
        Для villages — контейнер не требуется.
        """
        cat = (cat or "").strip().lower()
        if cat != "towns":
            return True  # для деревень не заходим внутрь

        parts = TELEPORT_LOCATIONS.get(loc)
        if not parts:
            return False
        parts = [self._lang() if p == "<lang>" else p for p in parts]

        # ожидаем, что путь имеет вид: "<lang>/teleport/towns/<City>/<file>"
        city_name = None
        try:
            idx = parts.index("towns")
            city_name = parts[idx + 1]
        except Exception:
            pass

        if not city_name:
            return True  # ничего не знаем — попробуем без контейнера

        # клик по городу
        city_btn = TELEPORT_TOWNS.get(city_name)
        city_init = TELEPORT_TOWNS.get(f"{city_name}_init")
        if not (city_btn and city_init):
            return True  # нет шаблонов — пробуем без контейнера

        city_btn = [self._lang() if p == "<lang>" else p for p in city_btn]
        city_init = [self._lang() if p == "<lang>" else p for p in city_init]

        if not self._click_template(city_btn, "fullscreen", thr, timeout_s):
            return False

        # дождаться init города
        win = self._win()
        end = time.time() + timeout_s
        while time.time() < end:
            if match_key_in_zone_single(
                window=win,
                zone_ltrb=self._zone("fullscreen"),
                server=self.server,
                lang=self._lang(),
                template_parts=city_init,
                threshold=thr,
                engine="dashboard",
            ):
                return True
            time.sleep(0.05)
        return False

    def click_location(self, loc: str, cat: str, *, thr: float = 0.86, timeout_s: float = 3.0) -> bool:
        """
        Нажать Esc → клик по локации → успех, если dashboard_init исчез.
        """
        loc = (loc or "").strip()
        if not loc:
            return False

        # контейнер (для towns)
        if not self._ensure_container_for_location(loc, cat, thr=thr, timeout_s=timeout_s):
            return False

        # клик по локации
        parts = TELEPORT_LOCATIONS.get(loc)
        if not parts:
            return False
        parts = [self._lang() if p == "<lang>" else p for p in parts]
        if not self._click_template(parts, "fullscreen", thr, timeout_s):
            return False

        # подтверждение: dashboard_init должен пропасть сам
        end = time.time() + max(1.0, timeout_s)
        while time.time() < end:
            if not self._visible("dashboard_init", "fullscreen", 0.86):
                return True
            time.sleep(0.05)

        return False
