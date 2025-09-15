# core/engines/dashboard/server/boh/teleport/stabilize/engine.py
from __future__ import annotations
import json
import os
import time
from typing import Any, Dict, Optional, Tuple, List

from core.logging import console
from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher_2 import match_key_in_zone_single
from core.engines.flow.ops import FlowCtx, FlowOpExecutor, run_flow

from .stabilize_data import ZONES, TEMPLATES


_ANCHORS_CACHE: Dict[str, Any] = {}


def _anchors_path() -> str:
    return os.path.join(
        os.path.dirname(__file__),
        "anchors.json",
    )


def _load_anchors() -> Dict[str, Any]:
    global _ANCHORS_CACHE
    if _ANCHORS_CACHE:
        return _ANCHORS_CACHE
    try:
        with open(_anchors_path(), "r", encoding="utf-8") as f:
            _ANCHORS_CACHE = json.load(f) or {}
    except Exception as e:
        console.log(f"[teleport/stabilize] anchors read error: {e}")
        _ANCHORS_CACHE = {}
    return _ANCHORS_CACHE


class StabilizeEngine:
    """
    Обязательная стабилизация:
      1) кликаем в центр зоны 'state' пока в зоне 'target' не появится 'target_init'
      2) жмём Esc

    Дополнительная (optional), если features.stabilize.enabled=True:
      1) /target <anchor> (ru/en вариант)
      2) если target_init не появился — повторить п.1
      3) /attack (ждём travel_time мс) → Esc
    """

    def __init__(self, state: Dict[str, Any], server: str, controller: Any, get_window, get_language):
        self.s = state
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

    def _visible(self, tpl_key: str, zone_name: str, thr: float = 0.70) -> bool:
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
            engine="stabilize",  # тот же матчинг
        ) is not None

    def _click_zone_center(self, zone_name: str, delay_ms: int = 80):
        l, t, r, b = self._zone(zone_name)
        x = (l + r) // 2
        y = (t + b) // 2
        win = self._win() if hasattr(self, "_win") else (self.get_window() if hasattr(self, "get_window") else {}) or {}
        abs_x = int((win.get("x") or 0) + x)
        abs_y = int((win.get("y") or 0) + y)
        try:
            self.controller.send(f"click:{abs_x},{abs_y}")
        except Exception:
            pass
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    def _press_esc(self, delay_ms: int = 200):
        try:
            self.controller.send("esc")
        except Exception:
            pass
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    def _press_enter(self, delay_ms: int = 80):
        try:
            self.controller.send("press_enter")
        except Exception:
            pass
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    def _press_pagedown(self, delay_ms: int = 80):
        try:
            self.controller.send("pagedown")
        except Exception:
            pass
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    def _enter_text(self, text: str):
        # контроллер сам печатает raw-текст; раскладка уже учитывается в /target-логике (см. ниже)
        try:
            self.controller.send(f"enter_text {text}")
        except Exception:
            pass

    def _layout_toggle_altshift(self, count: int = 1, delay_ms: int = 120):
        for i in range(max(1, count)):
            try:
                self.controller.send("layout_toggle_altshift")
            except Exception:
                pass
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

    # --- send_target ---------------------------------------------------------
    def _send_target_ru(self, ex: FlowOpExecutor, npc_name: str, wait_ms: int = 120) -> bool:
        flow = [
            {"op": "press_enter"},
            {"op": "enter_text", "layout": "en", "text": "/target "},
            {"op": "set_layout", "layout": "ru", "delay_ms": 120},
            {"op": "enter_text", "layout": "ru", "text": npc_name, "wait_ms": 60},
            {"op": "press_enter"},
            {"op": "set_layout", "layout": "en", "delay_ms": 120},
            {"op": "sleep", "ms": max(0, int(wait_ms))},
        ]
        return bool(run_flow(flow, ex))

    def _send_target_en(self, ex: FlowOpExecutor, npc_name: str, wait_ms: int = 120) -> bool:
        flow = [
            {"op": "press_enter"},
            {"op": "enter_text", "layout": "en", "text": f"/target {npc_name}"},
            {"op": "press_enter"},
            {"op": "sleep", "ms": max(0, int(wait_ms))},
        ]
        return bool(run_flow(flow, ex))

    # --- required ---------------------------------------------------------

    def stabilize_required(self, timeout_s: float = 8.0) -> bool:
        """
        Кликаем в центр 'state' пока 'target_init' не виден в 'target' → Esc.
        """
        end = time.time() + max(1.0, timeout_s)
        while time.time() < end:
            if self._visible("target_init", "target", 0.70):
                self._press_esc(200)
                return True
            self._click_zone_center("state", 80)
            time.sleep(0.10)
        return False

    # --- Flow executor (для корректной печати) ----------------------------

    def _make_executor(self) -> FlowOpExecutor:
        ctx = FlowCtx(
            server=self.server,
            controller=self.controller,
            get_window=self.get_window,
            get_language=self.get_language,
            zones=ZONES,
            templates=TEMPLATES,
            extras={},  # пока без плейсхолдеров
        )
        return FlowOpExecutor(ctx, logger=lambda m: console.log(f"[stabilize] {m}"))
    # --- optional ---------------------------------------------------------

    def _anchors_for_location(self, location: str) -> Tuple[str, int]:
        data = _load_anchors()
        locs = ((data.get("location") or {}) if isinstance(data, dict) else {})
        node = locs.get(location) or {}
        travel_ms = int(node.get("travel_time", 1500) or 1500)
        anchor = ((node.get("anchor") or {}) if isinstance(node, dict) else {})
        key = "rus" if self._lang().startswith("ru") else "eng"
        name = str(anchor.get(key, "")).strip()
        return name, travel_ms

    def stabilize_optional(self, location: str) -> bool:
        """
        /target <anchor> до появления target_init → /attack (ждать travel_time) → Esc
        """
        anchor, travel_ms = self._anchors_for_location(location)
        if not anchor:
            # нет якоря — нечего делать, считаем успехом
            return True

        # Повторы таргета до появления креста
        ex = self._make_executor()
        for _ in range(4):

            if self._lang().startswith("ru"):
                # /target (англ) + имя русскими (через Alt+Shift)
                self._send_target_ru(ex, anchor, wait_ms=120)
            else:
                self._send_target_en(ex, anchor, wait_ms=120)

            time.sleep(0.20)
            if self._visible("target_init", "target", 0.86):
                break
        else:
            # ни разу не подсветился target
            return False

        # /attack и ожидание перемещения
        self._press_enter(80)
        self._enter_text("/attack")
        self._press_enter(80)
        # подождать (движение к якорю)
        wait_s = max(0.2, travel_ms / 1000.0)
        time.sleep(wait_s)
        self._press_esc(200)
        self._press_pagedown(120)
        self._press_pagedown(120)
        self._press_pagedown(120)
        return True

    # --- entry ------------------------------------------------------------

    def run(self, location: str, *, do_optional: bool) -> bool:
        if not self.stabilize_required(timeout_s=8.0):
            console.hud("err", "[teleport] стабилизация: не удалось зафиксировать таргет")
            return False

        if do_optional:
            if not self.stabilize_optional(location):
                console.hud("err", "[teleport] стабилизация (optional) не удалась")
                return False

        console.hud("succ", "[teleport] стабилизация завершена")
        return True
