# app/launcher/sections/system.py
from __future__ import annotations
import threading
import json
from typing import Any, Dict
from ..base import BaseSection

from core.arduino.connection import ReviveController
from core.vision.capture.gdi import find_window, get_window_info
from core.arduino.connection_test import run_test_command
from core.updater import get_remote_version, is_newer_version

# новая конфигурация через manifest
from core.config.servers import (
    list_servers,
    get_languages,
    get_section_flags,
    get_buff_methods,
    get_buff_modes,
    get_tp_methods,
)

from core.state.pool import pool_write, pool_get, ensure_pool


def _schedule(fn, ms: int):
    t = threading.Timer(max(0.0, ms) / 1000.0, fn)
    t.daemon = True
    t.start()


class SystemSection(BaseSection):
    """
    Инициализация контроллера и бэк-сервисов. Весь конфиг/состояние — в пуле.
    Экспорт: get_init_state, set_program_language, set_language, set_server,
             find_window, test_connect, account_get/account_save,
             get_state_snapshot, get_status_snapshot, run_update_check, shutdown
    """

    def __init__(self, window, local_version: str, controller: ReviveController,
                 ps_adapter, state: Dict[str, Any], schedule):
        super().__init__(window, state)
        ensure_pool(self.s)

        # servers & initial server
        servers = list_servers()
        if not servers:
            raise RuntimeError("No servers in manifest")
        server = pool_get(self.s, "config.server", servers[0])

        # L2 languages for server
        l2_langs = get_languages(server)
        language = pool_get(self.s, "config.language", l2_langs[0] if l2_langs else "rus")

        # app/config
        pool_write(self.s, "app", {"version": local_version, "lang": pool_get(self.s, "app.lang", "ru")})
        pool_write(self.s, "config", {
            "server": server,
            "language": language,          # язык интерфейса L2
            "profiles": servers
        })

        # respawn defaults (если кто-то не выставил раньше)
        pool_write(self.s, "features.respawn", {
            "enabled": bool(pool_get(self.s, "features.respawn.enabled", True)),
            "wait_enabled": bool(pool_get(self.s, "features.respawn.wait_enabled", False)),
            "wait_seconds": int(pool_get(self.s, "features.respawn.wait_seconds", 120)),
            "click_threshold": float(pool_get(self.s, "features.respawn.click_threshold", 0.70)),
            "confirm_timeout_s": float(pool_get(self.s, "features.respawn.confirm_timeout_s", 6.0)),
        })

        # buff/tp methods from manifest
        buff_methods = get_buff_methods(server)
        buff_modes = get_buff_modes(server)
        tp_methods = get_tp_methods(server)
        cur_mode = pool_get(self.s, "features.buff.mode", (buff_modes[0] if buff_modes else ""))
        if cur_mode and cur_mode not in buff_modes:
            cur_mode = (buff_modes[0] if buff_modes else "")
        pool_write(self.s, "features.buff", {"methods": buff_methods, "modes": buff_modes, "mode": cur_mode})
        pool_write(self.s, "features.tp", {"methods": tp_methods})
        try:
            self.window.evaluate_js(
                f"window.ReviveUI && window.ReviveUI.onBuffMethods({json.dumps(buff_methods)}, {json.dumps(cur_mode)})"
            )
            self.window.evaluate_js(
                f"window.ReviveUI && window.ReviveUI.onBuffModes({json.dumps(buff_modes)}, {json.dumps(cur_mode)})"
            )
        except Exception:
            pass

        # sections visibility for current server
        pool_write(self.s, "ui.sections", get_section_flags(server))

        self.controller = controller
        self.ps = ps_adapter
        self.schedule = schedule

        # Arduino ping status
        try:
            self.controller.send("ping")
            ok = (self.controller.read() == "pong")
            self.emit("driver", "[✓] Arduino ответила" if ok else "[×] Нет ответа", ok)
        except Exception as e:
            self.emit("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        # авто-поиск окна + периодическая проверка апдейта
        _schedule(self._autofind_tick, 10)
        _schedule(self._periodic_update_check, 2_000)

        # account init
        if not pool_get(self.s, "account.login", None):
            pool_write(self.s, "account", {"login": "", "password": "", "pin": ""})

    # ---------- helpers ----------
    def _apply_server(self, server: str):
        server = (server or "").lower()
        # обновляем сервер и зависящие настройки
        pool_write(self.s, "config", {"server": server})

        l2_langs = get_languages(server)
        # если текущий язык L2 не входит — переключим на первый из разрешённых
        cur_lang = pool_get(self.s, "config.language", None)
        if not l2_langs:
            pool_write(self.s, "config", {"language": "rus"})
        elif cur_lang not in l2_langs:
            pool_write(self.s, "config", {"language": l2_langs[0]})

        # buff/tp
        buff_methods = get_buff_methods(server)
        buff_modes = get_buff_modes(server)
        tp_methods = get_tp_methods(server)

        cur_mode = pool_get(self.s, "features.buff.mode", "")
        if cur_mode not in buff_modes:
            cur_mode = (buff_modes[0] if buff_modes else "")
        pool_write(self.s, "features.buff", {"methods": buff_methods, "modes": buff_modes, "mode": cur_mode})
        pool_write(self.s, "features.tp", {"methods": tp_methods})

        try:
            self.window.evaluate_js(
                f"window.ReviveUI && window.ReviveUI.onBuffMethods({json.dumps(buff_methods)}, {json.dumps(cur_mode)})"
            )
            self.window.evaluate_js(
                f"window.ReviveUI && window.ReviveUI.onBuffModes({json.dumps(buff_modes)}, {json.dumps(cur_mode)})"
            )
        except Exception:
            pass

        # sections
        pool_write(self.s, "ui.sections", get_section_flags(server))

        # Сбросить пользовательские настройки, как просили (макросы/флаги)
        pool_write(self.s, "features.macros", {
            "enabled": False, "repeat_enabled": False, "rows": [],
            "run_always": False, "delay_s": 1.0, "duration_s": 2.0,
            "sequence": ["1"], "status": "idle",
        })
        pool_write(self.s, "features.respawn", {
            **pool_get(self.s, "features.respawn", {}),
            "enabled": False, "wait_enabled": False,
        })
        pool_write(self.s, "features.autofarm", {"enabled": False, "status": "idle"})

    # ---------- auto-find window ----------
    def _autofind_tick(self):
        if self.s.get("_autofind_stop") or pool_get(self.s, "window.found", False):
            return
        self.find_window()
        if not pool_get(self.s, "window.found", False):
            _schedule(self._autofind_tick, 3000)

    # ---------- update check ----------
    def _periodic_update_check(self):
        try:
            local_v = pool_get(self.s, "app.version", "")
            rv = get_remote_version()
            newer = is_newer_version(rv, local_v)
            pool_write(self.s, "app.update", {"available": bool(newer), "remote": rv})
            self.emit("update",
                      f"Доступно обновление: {rv}" if newer else f"Установлена последняя версия: {local_v}",
                      None if newer else True)
        except Exception:
            self.emit("update", "Сбой проверки актуальности версии", False)
        finally:
            _schedule(self._periodic_update_check, 600_000)

    # ---------- API ----------
    def get_init_state(self) -> Dict[str, Any]:
        servers = list_servers()
        cur_server = pool_get(self.s, "config.server", servers[0])

        # Проводим ping здесь и формируем driver_status напрямую (без ui_status)
        try:
            self.controller.send("ping")
            ok = (self.controller.read() == "pong")
            driver_status = {"text": ("[✓] Arduino ответила" if ok else "[×] Нет ответа"), "ok": ok}
        except Exception as e:
            driver_status = {"text": f"[×] Ошибка связи с Arduino: {e}", "ok": False}

        # данные для UI из манифеста
        l2_langs = get_languages(cur_server)
        tp_methods = get_tp_methods(cur_server)
        buff_methods = get_buff_methods(cur_server)
        buff_modes = get_buff_modes(cur_server)
        sections = get_section_flags(cur_server)

        return {
            "version": pool_get(self.s, "app.version", ""),
            "app_language": pool_get(self.s, "app.lang", "ru"),  # язык программы (ru/en)
            "language": pool_get(self.s, "config.language", (l2_langs[0] if l2_langs else "rus")),  # язык L2
            "system_languages": l2_langs,  # доступные языки L2 для сервера
            "server": cur_server,
            "servers": servers,
            "sections": sections,          # видимость секций
            "window_found": bool(pool_get(self.s, "window.found", False)),
            "monitoring": bool(self.ps.is_running() if hasattr(self.ps, "is_running") else False),

            "buff_methods": buff_methods,
            "buff_modes": buff_modes,  # ← ДОБАВЛЕНО
            "buff_current": pool_get(self.s, "features.buff.mode", ""),
            "tp_methods": tp_methods,

            # driver_status теперь формируется локально, без ui_status
            "driver_status": driver_status,
            "respawn": {
                "enabled": bool(pool_get(self.s, "features.respawn.enabled", False)),
                "wait_enabled": bool(pool_get(self.s, "features.respawn.wait_enabled", False)),
                "wait_seconds": int(pool_get(self.s, "features.respawn.wait_seconds", 120)),
            },
        }

    def set_program_language(self, lang: str):
        # локальная настройка UI приложения (не язык L2)
        lang = (lang or "ru").lower()
        pool_write(self.s, "app", {"lang": lang})

    def set_language(self, lang: str):
        # язык интерфейса L2
        lang = (lang or "rus").lower()
        pool_write(self.s, "config", {"language": lang})
        try:
            self.ps.set_language(lang)
        except Exception:
            pass

    def set_server(self, server: str):
        self._apply_server(server)
        try:
            self.ps.set_server(pool_get(self.s, "config.server", server))
        except Exception:
            pass

        # ui: обновить методы/режимы бафа через событие (повторно — на случай, если фронт не поймал вызовы из _apply_server)
        methods = pool_get(self.s, "features.buff.methods", [])
        modes   = pool_get(self.s, "features.buff.modes", [])
        cur     = pool_get(self.s, "features.buff.mode", "")
        try:
            self.window.evaluate_js(
                f"window.ReviveUI && window.ReviveUI.onBuffMethods({json.dumps(methods)}, {json.dumps(cur)})"
            )
            self.window.evaluate_js(
                f"window.ReviveUI && window.ReviveUI.onBuffModes({json.dumps(modes)}, {json.dumps(cur)})"
            )
        except Exception:
            pass

    def find_window(self) -> Dict[str, Any]:
        titles = ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]
        for t in titles:
            hwnd = find_window(t)
            if hwnd:
                win_info = get_window_info(hwnd, client=True) or {}
                try:
                    win_info["hwnd"] = int(hwnd)
                except Exception:
                    pass
                if isinstance(win_info, dict) and all(k in win_info for k in ("x", "y", "width", "height")):
                    pool_write(self.s, "window", {"info": win_info, "found": True, "title": t})
                    self.emit("window", "[✓] Окно найдено", True)
                    return {"found": True, "title": t, "info": win_info}
        pool_write(self.s, "window", {"info": None, "found": False, "title": ""})
        self.emit("window", "[×] Окно не найдено", False)
        return {"found": False}

    def test_connect(self) -> str:
        # Arduino ping status
        try:
            self.controller.send("ping")
            ok = (self.controller.read() == "pong")
            self.emit("driver", "[✓] Arduino ответила" if ok else "[×] Нет ответа", ok)
        except Exception as e:
            self.emit("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        label_proxy = type("L", (), {"config": lambda *_a, **_k: None})
        run_test_command(self.controller, label_proxy)
        return "ok"

    def account_get(self) -> Dict[str, str]:
        return dict(pool_get(self.s, "account", {"login": "", "password": "", "pin": ""}))

    def account_save(self, data: Dict[str, str]):
        pool_write(self.s, "account", {
            "login": data.get("login",""),
            "password": data.get("password",""),
            "pin": data.get("pin",""),
        })

    def get_status_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return dict(pool_get(self.s, "ui_status", {}) or {})

    def get_state_snapshot(self) -> Dict[str, Any]:
        try:
            st = self.ps.last() or {}
            hp_ratio = st.get("hp_ratio")
            if hp_ratio is None:
                return {"hp": None, "cp": None, "alive": None}
            hp = max(0, min(100, int(round(float(hp_ratio) * 100))))
            alive_val = st.get("alive")
            alive = bool(alive_val) if alive_val is not None else (hp > 0)
            return {"hp": hp, "cp": 100, "alive": alive}
        except Exception:
            return {"hp": None, "cp": None, "alive": None}

    def run_update_check(self) -> Dict[str, Any]:
        try:
            remote = get_remote_version()
            local = pool_get(self.s, "app.version", "")
            newer = is_newer_version(remote, local)
            pool_write(self.s, "app.update", {"available": bool(newer), "remote": remote})
            return {"remote": remote, "local": local, "update": bool(newer)}
        except Exception as e:
            return {"error": str(e)}

    def shutdown(self) -> None:
        try:
            self.s["_autofind_stop"] = True
            if hasattr(self.ps, "stop"):
                self.ps.stop()
        except Exception:
            pass
        try:
            self.controller.close()
        except Exception:
            pass

    def expose(self) -> dict:
        return {
            "get_init_state": self.get_init_state,
            "set_program_language": self.set_program_language,  # язык программы (ru/en)
            "set_language": self.set_language,                  # язык интерфейса L2 (rus/eng)
            "set_server": self.set_server,
            "find_window": self.find_window,
            "test_connect": self.test_connect,
            "account_get": self.account_get,
            "account_save": self.account_save,
            "get_state_snapshot": self.get_state_snapshot,
            "get_status_snapshot": self.get_status_snapshot,
            "run_update_check": self.run_update_check,
            "shutdown": self.shutdown,
        }
