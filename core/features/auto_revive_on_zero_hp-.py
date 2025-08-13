# core/features/auto_revive_on_zero_hp-.py
# Триггер: HP == 0% (с допуском). Действие: клик по центру шаблона "to_village".
# Подтверждение: HP > 0% в разумный таймаут.

from __future__ import annotations
import importlib
import threading
import time
from typing import Callable, Optional, Dict, Tuple, Any  # доп. Any

from core.features.player_state import PlayerState, PlayerStateMonitor
from core.vision.matching.template_matcher import match_in_zone
from core.features.player_state import is_alive  # ← добавить

class AutoReviveOnZeroHP:
    def __init__(
            self,
            controller,
            server: str,
            get_window: Callable[[], Optional[Dict]],
            get_language: Callable[[], str],
            poll_interval: float = 0.2,
            zero_hp_threshold: float = 0.01,
            confirm_timeout_s: float = 6.0,
            click_threshold: float = 0.87,
            debug: bool = False,
            on_revive: Optional[Callable[[], None]] = None,
            get_tp: Optional[Callable[[], Any]] = None,   # ← геттер TP
    ):
        self.controller = controller
        self.server = server
        self._get_window = get_window
        self._get_language = get_language
        self.zero_hp_threshold = zero_hp_threshold
        self.confirm_timeout_s = confirm_timeout_s
        self.click_threshold = click_threshold
        self.debug = debug
        self._on_revive = on_revive
        self._get_tp = get_tp

        # загрузка зон и шаблонов для respawn
        self._zones: Dict[str, Tuple[int,int,int,int]] = {}
        self._templates: Dict[str, list] = {}
        self._load_respawn_cfg()

        # монитор состояния
        self._state = PlayerState()
        self._monitor = PlayerStateMonitor(
            server=server,
            get_window=get_window,
            on_update=self._on_state_update,
            poll_interval=poll_interval,
            debug=False,
        )

        # флаги
        self._lock = threading.Lock()
        self._reviving = False
        self._last_attempt_ts = 0.0
        self._attempt_cooldown_s = 3.0

    # ---------- lifecycle ----------
    def set_server(self, server: str):
        self.server = server
        self._monitor.set_server(server)
        self._load_respawn_cfg()

    def start(self):
        self._monitor.start()

    def stop(self):
        self._monitor.stop()

    # ---------- internals ----------
    def _load_respawn_cfg(self):
        try:
            mod = importlib.import_module(f"core.servers.{self.server}.zones.respawn")
            self._zones = getattr(mod, "ZONES", {})
            self._templates = getattr(mod, "TEMPLATES", {})
            if self.debug:
                print(f"[revive] respawn cfg loaded for {self.server}")
        except Exception as e:
            print(f"[revive] cfg load error: {e}")
            self._zones, self._templates = {}, {}

    def _on_state_update(self, st: PlayerState):
        self._state = st
        print(f"[state] HP={int(st.hp_ratio * 100)}%")  # ← лог HP%
        if not is_alive(st, self.zero_hp_threshold):
            now = time.time()
            if (now - self._last_attempt_ts) < self._attempt_cooldown_s:
                return
            if not self._reviving:
                self._last_attempt_ts = now
                threading.Thread(target=self._revive_once_safe, daemon=True).start()

    def set_tp_getter(self, fn: Callable[[], Any]) -> None:    # ← НОВОЕ
        self._get_tp = fn

# ЗАМЕНИ целиком метод _revive_once_safe в core/features/auto_revive_on_zero_hp-.py

    def _revive_once_safe(self):
        with self._lock:
            if self._reviving:
                return
            self._reviving = True
        try:
            # 1) Пытаемся встать
            ok = self._revive_once()

            # 2) Если встал — запускаем пользовательский хук (баф)
            if ok and callable(self._on_revive):
                try:
                    self._on_revive()
                except Exception as e:
                    if self.debug:
                        print(f"[revive] on_revive error: {e}")

            # 3) После бафа — ТП, если включён
            try:
                tp = self._get_tp() if callable(getattr(self, "_get_tp", None)) else None
                if tp and getattr(tp, "is_enabled", lambda: False)():
                    fn = getattr(tp, "teleport_now_selected", None)
                    ok_tp = fn() if callable(fn) else False
                    print("[tp] run:", ok_tp)
                else:
                    print("[tp] skipped")
            except Exception as e:
                print(f"[tp] error: {e}")

            if self.debug:
                print(f"[revive] {'OK' if ok else 'FAIL'}")
        finally:
            self._reviving = False


    def _revive_once(self) -> bool:
        win = self._get_window() or {}
        if not win:
            if self.debug:
                print("[revive] no window")
            return False

        zone = self._zones.get("to_village")
        tpl_parts = self._templates.get("to_village")
        if not zone or not tpl_parts:
            if self.debug:
                print("[revive] zone/template not configured")
            return False

        # Нормализуем зону: поддержка dict и tuple
        z = self._normalize_zone(win, zone)

        # Ищем кнопку «В деревню»
        pt = match_in_zone(
            window=win,
            zone_ltrb=z,
            server=self.server,
            lang=self._safe_lang(),
            template_parts=tpl_parts,
            threshold=self.click_threshold,
        )
        if not pt:
            if self.debug:
                print("[revive] to_village not found")
            return False

        # Кликаем по центру найденного шаблона
        self.controller.send(f"click:{pt[0]},{pt[1]}")

        # Ожидание подтверждения: HP должен стать > 0%
        deadline = time.time() + self.confirm_timeout_s
        while time.time() < deadline:
            if is_alive(self._state, self.zero_hp_threshold):
                return True
            time.sleep(0.05)
        return False

    def _safe_lang(self) -> str:
        try:
            return (self._get_language() or "rus").lower()
        except Exception:
            return "rus"

    @staticmethod
    def _normalize_zone(window: Dict, zone_decl):
        """
        Принимает:
          - tuple (l,t,r,b) в client
          - dict {"left","top","width","height"} или {"centered":True,...} или {"fullscreen":True}
        Возвращает LTRB tuple.
        """
        wx, wy, ww, wh = window.get("x", 0), window.get("y", 0), window.get("width", 0), window.get("height", 0)

        if isinstance(zone_decl, tuple) and len(zone_decl) == 4:
            l, t, r, b = zone_decl
            return int(l), int(t), int(r), int(b)

        if isinstance(zone_decl, dict):
            if zone_decl.get("fullscreen"):
                return 0, 0, ww, wh
            if zone_decl.get("centered"):
                w, h = int(zone_decl["width"]), int(zone_decl["height"])
                l = ww // 2 - w // 2
                t = wh // 2 - h // 2
                return l, t, l + w, t + h
            # left/top/width/height
            l = int(zone_decl.get("left", 0))
            t = int(zone_decl.get("top", 0))
            w = int(zone_decl.get("width", 0))
            h = int(zone_decl.get("height", 0))
            return l, t, l + w, t + h

        # fallback
        return 0, 0, ww, wh
