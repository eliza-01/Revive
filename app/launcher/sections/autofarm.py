# app/launcher/sections/autofarm.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import threading
import time

from ..base import BaseSection

from core.engines.autofarm.runner import run_autofarm
from core.engines.autofarm.zone_repo import list_zones_declared as _af_list_zones_declared
from core.engines.autofarm.zone_repo import get_zone_info as _af_get_zone_info
from core.engines.autofarm.skill_repo import list_professions as _af_list_profs, list_skills as _af_list_skills


class AutofarmSection(BaseSection):
    """
    UI-API автофарма. UI получает *full*-имена мобов (как раньше).
    Сам движок (boh/l2mad и т.п.) сам маппит full → short из zones.json.
    """
    def __init__(self, window, controller, watcher, sys_state, schedule):
        super().__init__(window, sys_state)
        self.controller = controller
        self.watcher = watcher
        self.schedule = schedule

        # внутреннее состояние/поток
        self._thread: Optional[threading.Thread] = None
        self._run_lock = threading.Lock()

        # дефолты в shared state (если не заданы)
        self.s.setdefault("af_enabled", False)
        self.s.setdefault("af_mode", "after_tp")     # 'after_tp' | 'manual' (пока для совместимости)
        self.s.setdefault("af_profession", "")
        self.s.setdefault("af_skills", [])           # [{key, slug, cast_ms}]
        self.s.setdefault("af_zone", "")
        self.s.setdefault("af_monsters", [])         # [full-slug,...]

    # ---------- ЗОНЫ (как было) ----------

    def af_list_zones_declared_only(self, lang: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Возвращает список зон, объявленных для текущего сервера (server/<server>/zones.json),
        с fallback внутри zone_repo (server/common/...).
        """
        language = (lang or self.s["language"] or "eng")
        server = self.s["server"] or "common"
        try:
            return _af_list_zones_declared(server, language)
        except Exception as e:
            print(f"[autofarm] af_list_zones_declared_only error: {e}")
            return []

    def af_zone_info(self, zone_id: str, lang: Optional[str] = None) -> Dict[str, Any]:
        """
        Возвращаем как раньше: monsters = FULL-имена (для чекбоксов в UI).
        """
        language = (lang or self.s["language"] or "eng")
        server = self.s["server"] or "common"
        try:
            return _af_get_zone_info(server, zone_id, language)
        except Exception as e:
            print(f"[autofarm] af_zone_info error: {e}")
            return {"id": zone_id, "title": zone_id, "about": "", "images": [], "monsters": []}

    # ---------- ПРОФЫ / СКИЛЛЫ (как было) ----------

    def af_get_professions(self, lang: Optional[str] = None):
        language = (lang or self.s["language"] or "eng")
        try:
            return _af_list_profs(language)
        except Exception as e:
            print(f"[autofarm] af_get_professions error: {e}")
            return []

    def af_get_attack_skills(self, profession: str, lang: Optional[str] = None):
        language = (lang or self.s["language"] or "eng")
        server = self.s["server"] or "common"
        try:
            return _af_list_skills(profession, ["attack"], language, server)
        except Exception as e:
            print(f"[autofarm] af_get_attack_skills error: {e}")
            return []

    # ---------- НАСТРОЙКИ ОТ UI ----------

    def autofarm_set_mode(self, mode: str):
        self.s["af_mode"] = (mode or "after_tp").lower()

    def autofarm_save(self, ui_state: Dict[str, Any]):
        """
        Принимает от UI:
          {
            profession: str,
            skills: [{key, slug, cast_ms}],
            zone: str,
            monsters: [full-slug,...]
          }
        Не включает/выключает фарм — только сохраняет.
        """
        ui_state = dict(ui_state or {})
        self.s["af_profession"] = ui_state.get("profession", "") or ""
        self.s["af_skills"]     = list(ui_state.get("skills") or [])
        self.s["af_zone"]       = ui_state.get("zone", "") or ""
        self.s["af_monsters"]   = list(ui_state.get("monsters") or [])
        return {"ok": True}

    # ---------- СТАРТ/СТОП ----------

    def _build_cfg(self) -> Dict[str, Any]:
        return {
            "zone": self.s.get("af_zone") or "",
            "monsters": list(self.s.get("af_monsters") or []),
            "skills": list(self.s.get("af_skills") or []),
            # profession сейчас движку не нужна; оставим для будущего
            "profession": self.s.get("af_profession") or "",
        }

    def _emit_af(self, text: str, ok: Optional[bool] = None):
        self.emit("af", text, ok)

    def _runner_loop(self):
        """Фоновая нить: пока включено — запускаем движок, если он завершился, даём паузу и можно перезапускать."""
        self._emit_af("Автофарм запущен", True)
        try:
            while self.s.get("af_enabled", False):
                ok = False
                try:
                    ok = run_autofarm(
                        server=self.s["server"],
                        controller=self.controller,
                        get_window=lambda: self.s.get("window"),
                        get_language=lambda: self.s["language"],
                        on_status=lambda msg, ok=None: self._emit_af(msg, ok),
                        cfg=self._build_cfg(),
                        should_abort=lambda: (not self.s.get("af_enabled", False)),
                    )
                except Exception as e:
                    self._emit_af(f"[AF] ошибка запуска/работы: {e}", False)
                    ok = False

                # если выключили — выходим без перезапуска
                if not self.s.get("af_enabled", False):
                    break

                # движок вернулся сам (ок/не ок). Дадим короткую паузу и пойдём на новый круг
                if ok:
                    self._emit_af("АФ цикл завершён, поиск новой цели…", True)
                else:
                    self._emit_af("АФ перезапуск…", None)
                time.sleep(0.4)
        finally:
            self._emit_af("Автофарм остановлен", None)

    def autofarm_set_enabled(self, enabled: bool):
        enabled = bool(enabled)
        self.s["af_enabled"] = enabled
        if enabled:
            with self._run_lock:
                if self._thread and self._thread.is_alive():
                    # уже бежит
                    return {"ok": True}
                self._thread = threading.Thread(target=self._runner_loop, daemon=True)
                self._thread.start()
            return {"ok": True}
        else:
            # мягкая остановка: should_abort вернёт True, поток сам завершится
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
