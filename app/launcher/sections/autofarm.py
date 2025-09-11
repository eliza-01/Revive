# app/launcher/sections/autofarm.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ..base import BaseSection

from core.engines.autofarm.runner import run_autofarm
from core.engines.autofarm.zone_repo import list_zones_declared as _af_list_zones_declared
from core.engines.autofarm.zone_repo import get_zone_info as _af_get_zone_info
from core.engines.autofarm.skill_repo import list_professions as _af_list_profs, list_skills as _af_list_skills

from core.state.pool import pool_get, pool_write


class AutofarmSection(BaseSection):
    """
    UI-API автофарма. UI получает *full*-имена мобов (как раньше).
    Сам движок маппит full → short из zones.json.
    Всё состояние хранится в пуле:
      features.autofarm.enabled / mode / profession / skills / zone / monsters
    """

    def __init__(self, window, controller, watcher, state, schedule):
        super().__init__(window, state)
        self.controller = controller
        self.watcher = watcher
        self.schedule = schedule

        # мягкие дефолты в пул (если кто-то не заинициалил ранее)
        if pool_get(self.s, "features.autofarm.mode", None) is None:
            pool_write(self.s, "features.autofarm", {
                "enabled": bool(pool_get(self.s, "features.autofarm.enabled", False)),
                "mode": "auto",            # 'auto' | 'manual'
                "profession": "",
                "skills": [],                  # [{key, slug, cast_ms}]
                "zone": "",
                "monsters": [],                # [full-slug,...]
                "status": pool_get(self.s, "features.autofarm.status", "idle"),
            })

    # ---------- ЗОНЫ (как было) ----------

    def af_list_zones_declared_only(self, lang: Optional[str] = None) -> list[dict]:
        language = (lang or pool_get(self.s, "config.language", "eng"))
        server = pool_get(self.s, "config.server", "boh")
        try:
            return _af_list_zones_declared(server, language)
        except Exception as e:
            print(f"[autofarm] af_list_zones_declared_only error: {e}")
            return []

    def af_zone_info(self, zone_id: str, lang: Optional[str] = None) -> dict:
        language = (lang or pool_get(self.s, "config.language", "eng"))
        server = pool_get(self.s, "config.server", "boh")
        try:
            return _af_get_zone_info(server, zone_id, language)
        except Exception as e:
            print(f"[autofarm] af_zone_info error: {e}")
            return {"id": zone_id, "title": zone_id, "about": "", "images": [], "monsters": []}

    # ---------- ПРОФЫ / СКИЛЛЫ (как было) ----------

    def af_get_professions(self, lang: Optional[str] = None):
        language = (lang or pool_get(self.s, "config.language", "eng"))
        try:
            return _af_list_profs(language)
        except Exception as e:
            print(f"[autofarm] af_get_professions error: {e}")
            return []

    def af_get_attack_skills(self, profession: str, lang: Optional[str] = None):
        language = (lang or pool_get(self.s, "config.language", "eng"))
        server = pool_get(self.s, "config.server", "common")
        try:
            return _af_list_skills(profession, ["attack"], language, server)
        except Exception as e:
            print(f"[autofarm] af_get_attack_skills error: {e}")
            return []

    # ---------- НАСТРОЙКИ ОТ UI ----------

    def autofarm_set_mode(self, mode: str):
        m = (mode or "auto").lower()
        pool_write(self.s, "features.autofarm", {"mode": m})
        pool_write(self.s, "features.autofarm.config", {"mode": m})

    def autofarm_save(self, ui_state: Dict[str, Any]):
        ui_state = dict(ui_state or {})
        payload = {
            "profession": ui_state.get("profession", "") or "",
            "skills": list(ui_state.get("skills") or []),
            "zone": ui_state.get("zone", "") or "",
            "monsters": list(ui_state.get("monsters") or []),
        }
        # верхний уровень
        pool_write(self.s, "features.autofarm", payload)
        # зеркало для совместимости
        pool_write(self.s, "features.autofarm", {"config": dict(payload)})
        return {"ok": True}

    # ---------- СТАРТ/СТОП ----------

    def _build_cfg(self) -> Dict[str, Any]:
        return {
            "zone": pool_get(self.s, "features.autofarm.zone", "") or "",
            "monsters": list(pool_get(self.s, "features.autofarm.monsters", []) or []),
            "skills": list(pool_get(self.s, "features.autofarm.skills", []) or []),
            # profession сейчас движку не нужна; оставим для будущего
            "profession": pool_get(self.s, "features.autofarm.profession", "") or "",
        }

    def autofarm_set_enabled(self, enabled: bool):
        """
        Только выставляем флаг в пуле — фоновой работой занимается AutoFarmService.
        """
        pool_write(self.s, "features.autofarm", {"enabled": bool(enabled)})

        return {"ok": True}

    # ---------- Экспорт в webview.expose ----------

    def expose(self) -> dict:
        return {
            # справочная часть (как была)
            "af_list_zones_declared_only": self.af_list_zones_declared_only,
            "af_zone_info": self.af_zone_info,
            "af_get_professions": self.af_get_professions,
            "af_get_attack_skills": self.af_get_attack_skills,

            # управление/настройки
            "autofarm_set_mode": self.autofarm_set_mode,
            "autofarm_set_enabled": self.autofarm_set_enabled,
            "autofarm_save": self.autofarm_save,
        }
