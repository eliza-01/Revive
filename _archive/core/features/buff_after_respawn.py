# core/features/buff_after_respawn.py
from __future__ import annotations
from typing import Callable, Optional, Dict
import importlib

from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

BUFF_MODE_PROFILE = "profile"
BUFF_MODE_MAGE = "mage"
BUFF_MODE_FIGHTER = "fighter"


class BuffAfterRespawnWorker:
    """
    Выполняет баф по выбранному методу:
      - method='dashboard' -> core.servers.<server>.flows.buff_dashboard
        (если файла нет — fallback на flows.buff)
      - method='npc'       -> core.servers.<server>.flows.buff_npc

    Зоны/шаблоны берутся из core.servers.<server>.zones.buff

    В flow можно использовать tpl="{mode_key}" — подставится один из:
      buffer_mode_profile | buffer_mode_mage | buffer_mode_fighter
    """
    def __init__(
        self,
        controller,
        server: str,
        get_window: Callable[[], Optional[Dict]],
        get_language: Callable[[], str],
        on_status: Callable[[str, Optional[bool]], None] = lambda *_: None,
        click_threshold: float = 0.87,
        debug: bool = False,
    ):
        self.controller = controller
        self.server = server
        self._get_window = get_window
        self._get_language = get_language
        self._on_status = on_status
        self._click_thr = float(click_threshold)
        self._debug = bool(debug)

        self._mode = BUFF_MODE_PROFILE
        self._method = "dashboard"  # 'dashboard' | 'npc'

    # --- публичные настройки ---
    def set_mode(self, mode: str):
        m = (mode or BUFF_MODE_PROFILE).lower()
        self._mode = m if m in (BUFF_MODE_PROFILE, BUFF_MODE_MAGE, BUFF_MODE_FIGHTER) else BUFF_MODE_PROFILE

    def set_method(self, method: str):
        m = (method or "dashboard").lower()
        self._method = m if m in ("dashboard", "npc") else "dashboard"

    # --- внутренние ---
    def _mode_tpl_key(self) -> str:
        return {
            BUFF_MODE_PROFILE: "buffer_mode_profile",
            BUFF_MODE_MAGE: "buffer_mode_mage",
            BUFF_MODE_FIGHTER: "buffer_mode_fighter",
        }[self._mode]

    def _load_flow(self):
        """
        Возвращает список шагов FLOW для выбранного метода.
        dashboard:  пробуем flows.buff_dashboard, иначе fallback на flows.buff
        npc:        flows.buff_npc (без fallback)
        """
        try:
            if self._method == "dashboard":
                try:
                    mod = importlib.import_module(f"core.servers.{self.server}.flows.buff_dashboard")
                except Exception:
                    # бэк-компат: старое имя файла
                    mod = importlib.import_module(f"core.servers.{self.server}.flows.buff")
            else:  # npc
                mod = importlib.import_module(f"core.servers.{self.server}.flows.buff_npc")
            return getattr(mod, "FLOW", [])
        except Exception as e:
            self._on_status(f"[buff] load flow error: {e}", False)
            return []

    def _load_zones(self):
        try:
            zm = importlib.import_module(f"core.servers.{self.server}.zones.buff")
            zones = getattr(zm, "ZONES", {})
            templates = getattr(zm, "TEMPLATES", {})
            return zones, templates
        except Exception as e:
            self._on_status(f"[buff] zones load error: {e}", False)
            return {}, {}

    # --- запуск ---
    def run_once(self) -> bool:
        flow = self._load_flow()
        if not flow:
            self._on_status("[buff] empty flow (nothing to do)", False)
            return False

        zones, templates = self._load_zones()
        if not zones or not templates:
            return False

        ctx = FlowCtx(
            server=self.server,
            controller=self.controller,
            get_window=self._get_window,
            get_language=self._get_language,
            zones=zones,
            templates=templates,
            extras={
                # для "{mode_key}" в flow
                "mode_key_provider": lambda: self._mode_tpl_key(),
            },
        )
        execu = FlowOpExecutor(ctx, on_status=self._on_status, logger=lambda m: print(m))
        ok = run_flow(flow, execu)
        self._on_status(("Баф выполнен" if ok else "Баф не выполнен"), ok)
        return ok
