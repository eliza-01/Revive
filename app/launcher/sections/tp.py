# app/launcher/sections/tp.py
from __future__ import annotations
from typing import Any, Dict, List
from ..base import BaseSection
from core.state.pool import pool_write, pool_get

TP_METHOD_DASHBOARD = "dashboard"
TP_METHOD_GATEKEEPER = "gatekeeper"

class TPSection(BaseSection):
    """
    Управление телепортом через пул.
    Категории/локации тянем из server profile, если он предоставляет такие методы.
    """

    def __init__(self, window, controller, ps_adapter, state: Dict[str, Any], schedule):
        super().__init__(window, state)
        self.controller = controller
        self.ps = ps_adapter
        self.schedule = schedule

    # --- helpers to profile ---
    def _profile(self):
        return pool_get(self.s, "config.profile", None)

    def tp_get_methods(self) -> List[str]:
        return [TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER]

    def tp_list_categories(self) -> List[str]:
        prof = self._profile()
        try:
            fn = getattr(prof, "tp_categories", None) or getattr(prof, "get_tp_categories", None)
            if fn:
                cats = list(fn()) or []
                return [str(c) for c in cats]
        except Exception:
            pass
        return []

    def tp_list_locations(self, category: str) -> List[Dict[str, Any]]:
        prof = self._profile()
        cat = category or ""
        try:
            fn = getattr(prof, "tp_locations", None) or getattr(prof, "get_tp_locations", None)
            if fn:
                rows = list(fn(cat)) or []
                # нормализуем: [{"id": "...", "title": "..."}]
                norm: List[Dict[str, Any]] = []
                for r in rows:
                    if isinstance(r, dict):
                        rid = r.get("id") or r.get("rid") or r.get("row_id") or r.get("value") or ""
                        title = r.get("title") or r.get("name") or r.get("text") or str(rid)
                        norm.append({"id": str(rid), "title": str(title)})
                    else:
                        # строка
                        norm.append({"id": str(r), "title": str(r)})
                return norm
        except Exception:
            pass
        return []

    # --- setters ---
    def tp_set_enabled(self, enabled: bool):
        pool_write(self.s, "features.tp", {"enabled": bool(enabled)})
        self.emit("tp", "Телепорт: вкл" if enabled else "Телепорт: выкл", True if enabled else None)

    def tp_set_method(self, method: str):
        m = (method or "").strip().lower()
        if m not in (TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER):
            self.emit("tp", f"Неизвестный метод телепорта: {method}", None)
        pool_write(self.s, "features.tp", {"method": m})

    def tp_set_category(self, category: str):
        pool_write(self.s, "features.tp", {"category": category or ""})

    def tp_set_location(self, location: str, row_id: str = ""):
        # можно сохранить оба варианта: логическое имя и конкретный row_id из профиля
        upd = {"location": location or ""}
        if row_id:
            upd["row_id"] = str(row_id)
        pool_write(self.s, "features.tp", upd)

    # --- getters ---
    def tp_get_state(self) -> Dict[str, Any]:
        return {
            "enabled": bool(pool_get(self.s, "features.tp.enabled", False)),
            "method": pool_get(self.s, "features.tp.method", TP_METHOD_DASHBOARD),
            "category": pool_get(self.s, "features.tp.category", ""),
            "location": pool_get(self.s, "features.tp.location", ""),
            "row_id": pool_get(self.s, "features.tp.row_id", ""),
        }

    # --- action ---
    def tp_run_once(self) -> bool:
        if not pool_get(self.s, "features.tp.enabled", False):
            self.emit("tp", "Телепорт отключён", None)
            return False

        method = pool_get(self.s, "features.tp.method", TP_METHOD_DASHBOARD)
        cat = pool_get(self.s, "features.tp.category", "")
        loc = pool_get(self.s, "features.tp.location", "")
        rid = pool_get(self.s, "features.tp.row_id", "")

        # здесь должен быть вызов конкретного движка телепорта.
        # пока просто прокинем статус, чтобы пайплайн мог сообщить пользователю.
        self.emit("tp", f"Телепорт ({method}): {cat} → {loc or rid or '—'}", None)
        return True

    def expose(self) -> dict:
        return {
            "tp_get_methods": self.tp_get_methods,
            "tp_list_categories": self.tp_list_categories,
            "tp_list_locations": self.tp_list_locations,
            "tp_get_state": self.tp_get_state,
            "tp_set_enabled": self.tp_set_enabled,
            "tp_set_method": self.tp_set_method,
            "tp_set_category": self.tp_set_category,
            "tp_set_location": self.tp_set_location,
            "tp_run_once": self.tp_run_once,
        }
