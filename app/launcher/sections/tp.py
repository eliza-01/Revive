# app/launcher/sections/tp.py
from __future__ import annotations
from .base import BaseSection
from core.features.tp_after_respawn import TPAfterDeathWorker, TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER
from core.servers.l2mad.locations_map import get_categories, get_locations

class TPSection(BaseSection):
    def __init__(self, window, controller, watcher, sys_state, schedule):
        super().__init__(window, sys_state)
        self.controller = controller
        self.watcher = watcher
        self.schedule = schedule

    def tp_set_enabled(self, enabled: bool): self.s["tp_enabled"] = bool(enabled)
    def tp_set_method(self, method: str): self.s["tp_method"] = method or TP_METHOD_DASHBOARD
    def tp_set_category(self, cid: str): self.s["tp_category"] = cid or ""; self.s["tp_location"] = ""
    def tp_set_location(self, lid: str): self.s["tp_location"] = lid or ""
    def tp_get_selected_row_id(self) -> str: return str(self.s.get("tp_row_id") or "")
    def tp_set_selected_row_id(self, rid: str): self.s["tp_row_id"] = rid or ""

    def tp_get_categories(self):
        lang = self.s["language"]
        cats = get_categories(lang=lang)
        return [{"id": c["id"], "title": c["display_rus"] if lang == "rus" else c["display_eng"]} for c in cats]

    def tp_get_locations(self, category_id: str):
        lang = self.s["language"]
        locs = get_locations(category_id, lang=lang) if category_id else []
        return [{"id": l["id"], "title": l["display_rus"] if lang == "rus" else l["display_eng"]} for l in locs]

    def tp_teleport_now(self) -> bool:
        if not self.s.get("window"): self.emit("tp", "Окно не найдено", False); return False
        w = TPAfterDeathWorker(
            controller=self.controller,
            window_info=self.s["window"],
            get_language=lambda: self.s["language"],
            on_status=lambda t, ok=None: self.emit("tp", t, ok),
            check_is_dead=lambda: (not self.watcher.is_alive()),
        )
        w.set_method(self.s.get("tp_method") or TP_METHOD_DASHBOARD)
        cat, loc = (self.s.get("tp_category") or ""), (self.s.get("tp_location") or "")
        ok = w.teleport_now(cat, loc, self.s.get("tp_method") or TP_METHOD_DASHBOARD)
        return bool(ok)

    def expose(self) -> dict:
        return {
            "tp_set_enabled": self.tp_set_enabled,
            "tp_set_method": self.tp_set_method,
            "tp_set_category": self.tp_set_category,
            "tp_set_location": self.tp_set_location,
            "tp_get_categories": self.tp_get_categories,
            "tp_get_locations": self.tp_get_locations,
            "tp_get_selected_row_id": self.tp_get_selected_row_id,
            "tp_set_selected_row_id": self.tp_set_selected_row_id,
            "tp_teleport_now": self.tp_teleport_now,
        }
