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

        # внутреннее состояние/поток
        self._thread: Optional[threading.Thread] = None
        self._run_lock = threading.Lock()

        # мягкие дефолты в пул (если кто-то не заинициалил ранее)
        if pool_get(self.s, "features.autofarm.mode", None) is None:
            pool_write(self.s, "features.autofarm", {
                "enabled": bool(pool_get(self.s, "features.autofarm.enabled", False)),
                "mode": "after_tp",            # 'after_tp' | 'manual'
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
        pool_write(self.s, "features.autofarm", {"mode": (mode or "after_tp").lower()})

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
        pool_write(self.s, "features.autofarm", {
            "profession": ui_state.get("profession", "") or "",
            "skills": list(ui_state.get("skills") or []),
            "zone": ui_state.get("zone", "") or "",
            "monsters": list(ui_state.get("monsters") or []),
        })
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

    def _emit_af(self, text: str, ok: Optional[bool] = None):
        # Скоуп "autofarm" (можно добавить в UI-мэппинг при желании)
        self.emit("autofarm", text, ok)

    def _enabled(self) -> bool:
        return bool(pool_get(self.s, "features.autofarm.enabled", False))

    def _runner_loop(self):
        """Фоновая нить: пока включено — запускаем движок, если он завершился, даём паузу и можем перезапускать."""
        self._emit_af("Автофарм запущен", True)
        try:
            while self._enabled():
                ok = False
                try:
                    ok = run_autofarm(
                        server=pool_get(self.s, "config.server", "boh"),
                        controller=self.controller,
                        get_window=lambda: pool_get(self.s, "window.info", None),
                        get_language=lambda: pool_get(self.s, "config.language", "rus"),
                        on_status=lambda msg, ok=None: self._emit_af(msg, ok),
                        cfg=self._build_cfg(),
                        should_abort=lambda: (not self._enabled()),
                    )
                except Exception as e:
                    self._emit_af(f"[AF] ошибка запуска/работы: {e}", False)
                    ok = False

                if not self._enabled():
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
        pool_write(self.s, "features.autofarm", {"enabled": enabled})
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
