# app/launcher/sections/teleport.py
from __future__ import annotations
from typing import Any, Dict, List
from ..base import BaseSection
from core.state.pool import pool_get, pool_write
from core.config.servers import get_teleport_categories, get_teleport_locations

class TeleportSection(BaseSection):
    """
    Телепорт: только UI/конфиг (пул и ручные команды из WebUI).
    Исполнение шага делает движок/правило пайплайна.
    """

    def __init__(self, window, controller, ps_adapter, state: Dict[str, Any], schedule):
        super().__init__(window, state)
        self.controller = controller
        self.ps = ps_adapter
        self.schedule = schedule

        # Инициализация минимальных полей (без списков категорий/локаций)
        teleport = dict(pool_get(self.s, "features.teleport", {}) or {})
        teleport.setdefault("enabled", False)
        teleport.setdefault("method", teleport.get("method", "dashboard"))
        teleport.setdefault("category", teleport.get("category", ""))
        teleport.setdefault("location", teleport.get("location", ""))
        teleport.setdefault("status", teleport.get("status", "idle"))
        teleport.setdefault("busy", teleport.get("busy", False))
        teleport.setdefault("waiting", teleport.get("waiting", False))
        pool_write(self.s, "features.teleport", teleport)

        # stabilize — отдельная фича (не в teleport)
        stab = dict(pool_get(self.s, "features.stabilize", {}) or {})
        stab.setdefault("enabled", False)
        stab.setdefault("busy", False)
        stab.setdefault("status", "idle")
        pool_write(self.s, "features.stabilize", stab)

    # ---------- setters ----------
    def teleport_set_enabled(self, enabled: bool):
        pool_write(self.s, "features.teleport", {"enabled": bool(enabled)})
        self.emit("teleport", f"ТП: {'вкл' if enabled else 'выкл'}", True if enabled else None)

    def teleport_set_method(self, method: str):
        pool_write(self.s, "features.teleport", {"method": str(method or "")})

    def teleport_set_category(self, cat: str):
        pool_write(self.s, "features.teleport", {"category": str(cat or "")})

    def teleport_set_location(self, loc: str):
        pool_write(self.s, "features.teleport", {"location": str(loc or "")})

    def teleport_set_stabilize(self, flag: bool):
        pool_write(self.s, "features.stabilize", {"enabled": bool(flag)})
        self.emit("teleport", f"Стабилизация прибытия: {'вкл' if flag else 'выкл'}", True if flag else None)

    # ---------- getters ----------
    def teleport_get_config(self) -> Dict[str, Any]:
        teleport = dict(pool_get(self.s, "features.teleport", {}) or {})
        return {
            "enabled": bool(teleport.get("enabled", False)),
            "method": str(teleport.get("method", "")),
            "category": str(teleport.get("category", "")),
            "location": str(teleport.get("location", "")),
            "stabilize": bool(pool_get(self.s, "features.stabilize.enabled", False)),
        }

    # ---------- lists for UI (из манифеста) ----------
    def teleport_list_categories(self) -> List[str]:
        server = str(pool_get(self.s, "config.server", ""))
        return get_teleport_categories(server)

    def teleport_list_locations(self, category: str) -> List[str]:
        server = str(pool_get(self.s, "config.server", ""))
        return get_teleport_locations(server, category)

    # ---------- manual run ----------
    def teleport_run_now(self) -> Dict[str, Any]:
        en = bool(pool_get(self.s, "features.teleport.enabled", False))
        if not en:
            self.emit("teleport", "Телепорт отключён", None)
            return {"ok": False, "reason": "disabled"}

        cat = pool_get(self.s, "features.teleport.category", "")
        loc = pool_get(self.s, "features.teleport.location", "")
        if not cat or not loc:
            self.emit("teleport", "Выберите категорию и локацию", None)
            return {"ok": False, "reason": "no_target"}

        pool_write(self.s, "features.teleport", {"status": "pending"})
        self.emit("teleport", f"ТП → {cat} / {loc}", None)
        return {"ok": True}

    # ---------- expose ----------
    def expose(self) -> dict:
        return {
            "teleport_set_enabled": self.teleport_set_enabled,
            "teleport_set_method": self.teleport_set_method,
            "teleport_set_category": self.teleport_set_category,
            "teleport_set_location": self.teleport_set_location,
            "teleport_set_stabilize": self.teleport_set_stabilize,
            "teleport_get_config": self.teleport_get_config,
            "teleport_list_categories": self.teleport_list_categories,
            "teleport_list_locations": self.teleport_list_locations,
            "teleport_run_now": self.teleport_run_now,
        }
