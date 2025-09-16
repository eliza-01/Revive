# app/launcher/sections/autofarm.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ..base import BaseSection
from core.state.pool import pool_get, pool_write
from core.logging import console

from core.engines.autofarm.zone_repo import (
    list_zones_declared as _af_list_zones_declared,
    get_zone_info as _af_get_zone_info,
)
from core.engines.autofarm.skill_repo import (
    list_professions as _af_list_profs,
    list_skills as _af_list_skills,
)

class AutofarmSection(BaseSection):
    """
    UI-API автофарма.
    Весь рабочий стейт лежит в пуле ТОЛЬКО здесь:
      features.autofarm.enabled : bool
      features.autofarm.mode    : "auto" | "manual" | ""   ← валидировано в wiring/prefs
      features.autofarm.modes   : [строки]                 ← из манифеста
      features.autofarm.config  : { profession, skills[], zone, monsters[] }
    """

    def __init__(self, window, controller, ps_adapter, state, schedule):
        super().__init__(window, state)
        self.controller = controller
        self.ps = ps_adapter
        self.schedule = schedule
        # ВАЖНО: никаких локальных дефолтов здесь не проставляем.
        # Дефолты и загрузка prefs выполняются в ensure_pool()/wiring.

    # ---------- Справочные API (зоны / профы / скиллы) ----------

    def af_list_zones_declared_only(self, lang: Optional[str] = None) -> List[dict]:
        language = (lang or pool_get(self.s, "config.language", "eng"))
        server = pool_get(self.s, "config.server", "boh")
        try:
            return _af_list_zones_declared(server, language)
        except Exception as e:
            console.log(f"[autofarm] af_list_zones_declared_only error: {e}")
            return []

    def af_zone_info(self, zone_id: str, lang: Optional[str] = None) -> dict:
        language = (lang or pool_get(self.s, "config.language", "eng"))
        server = pool_get(self.s, "config.server", "boh")
        try:
            return _af_get_zone_info(server, zone_id, language)
        except Exception as e:
            console.log(f"[autofarm] af_zone_info error: {e}")
            return {"id": zone_id, "title": zone_id, "about": "", "images": [], "monsters": []}

    def af_get_professions(self, lang: Optional[str] = None) -> List[dict]:
        language = (lang or pool_get(self.s, "config.language", "eng"))
        try:
            return _af_list_profs(language)
        except Exception as e:
            console.log(f"[autofarm] af_get_professions error: {e}")
            return []

    def af_get_attack_skills(self, profession: str, lang: Optional[str] = None) -> List[dict]:
        language = (lang or pool_get(self.s, "config.language", "eng"))
        server = pool_get(self.s, "config.server", "common")
        try:
            return _af_list_skills(profession, ["attack"], language, server)
        except Exception as e:
            console.log(f"[autofarm] af_get_attack_skills error: {e}")
            return []

    # ---------- Настройки / состояние для UI ----------

    def autofarm_get(self) -> Dict[str, Any]:
        """Гидратация формы на фронте."""
        try:
            return {
                "ok": True,
                "enabled": bool(pool_get(self.s, "features.autofarm.enabled", False)),
                "mode":     pool_get(self.s, "features.autofarm.mode", "") or "",
                "modes":    list(pool_get(self.s, "features.autofarm.modes", []) or []),
                "config":   dict(pool_get(self.s, "features.autofarm.config", {}) or {}),
            }
        except Exception as e:
            console.log(f"[autofarm] autofarm_get error: {e}")
            return {"ok": False, "error": str(e)}

    def autofarm_set_mode(self, mode: str):
        """Меняем режим, валидируя по features.autofarm.modes."""
        try:
            m = (mode or "").strip().lower()
            modes = list(pool_get(self.s, "features.autofarm.modes", []) or [])
            if modes and m not in modes:
                console.hud("err", f"[autofarm] недопустимый режим: {m}")
                return {"ok": False, "error": "invalid_mode"}
            pool_write(self.s, "features.autofarm", {"mode": m})
            return {"ok": True}
        except Exception as e:
            console.log(f"[autofarm] autofarm_set_mode error: {e}")
            return {"ok": False, "error": str(e)}

    def autofarm_set_enabled(self, enabled: bool):
        """Флаг включения — работу выполняет AutoFarmService."""
        try:
            pool_write(self.s, "features.autofarm", {"enabled": bool(enabled)})
            return {"ok": True}
        except Exception as e:
            console.log(f"[autofarm] autofarm_set_enabled error: {e}")
            return {"ok": False, "error": str(e)}

    def autofarm_save(self, ui_state: Dict[str, Any]):
        """
        Сохраняем ТОЛЬКО payload конфигурации в features.autofarm.config.
        """
        try:
            ui_state = dict(ui_state or {})
            payload = {
                "profession": ui_state.get("profession", "") or "",
                "skills":     list(ui_state.get("skills") or []),
                "zone":       ui_state.get("zone", "") or "",
                "monsters":   list(ui_state.get("monsters") or []),
            }
            pool_write(self.s, "features.autofarm", {"config": payload})
            return {"ok": True}
        except Exception as e:
            console.log(f"[autofarm] autofarm_save error: {e}")
            return {"ok": False, "error": str(e)}

    # ---------- Экспорт в webview.expose ----------

    def expose(self) -> dict:
        return {
            # справочная часть
            "af_list_zones_declared_only": self.af_list_zones_declared_only,
            "af_zone_info": self.af_zone_info,
            "af_get_professions": self.af_get_professions,
            "af_get_attack_skills": self.af_get_attack_skills,

            # состояние/настройки
            "autofarm_get": self.autofarm_get,
            "autofarm_set_mode": self.autofarm_set_mode,
            "autofarm_set_enabled": self.autofarm_set_enabled,
            "autofarm_save": self.autofarm_save,
        }
