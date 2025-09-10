# app/launcher/infra/services.py
from __future__ import annotations
from typing import Any, Dict, Optional
import json

from core.state.pool import pool_get, pool_write
from core.engines.player_state.service import PlayerStateService
from core.engines.window_focus.service import WindowFocusService
from core.engines.macros.service import MacrosRepeatService


class PSAdapter:
    """Лёгкий адаптер поверх пула для оркестратора/секций."""
    def __init__(self, state: Dict[str, Any]):
        self._state = state

    def last(self) -> Dict[str, Any]:
        p = pool_get(self._state, "player", {}) or {}
        return {
            "alive": p.get("alive"),
            "hp_ratio": p.get("hp_ratio"),
            "cp_ratio": p.get("cp_ratio"),
            "ts": p.get("ts"),
        }

    def is_alive(self) -> bool:
        a = pool_get(self._state, "player.alive", None)
        return bool(a) if a is not None else False

    def is_running(self) -> bool:
        return bool(pool_get(self._state, "services.player_state.running", False))


class ServicesBundle:
    """
    Собирает все фоновые сервисы + даёт ps_adapter.
    Использует ui (объект с методами: log, log_ok, hud_push, ui_emit, schedule).
    """

    def __init__(self, state: Dict[str, Any], window, hud_window, ui, controller):
        self.state = state
        self.window = window
        self.hud_window = hud_window
        self.ui = ui
        self.controller = controller

        # --- Player State service ---
        def _on_ps_update(data: Dict[str, Any]):
            hp = data.get("hp_ratio")
            # не трогаем vitals, если нет фокуса
            if pool_get(self.state, "focus.has_focus") is False:
                return

            alive = None if hp is None else bool(hp > 0.001)
            pool_write(self.state, "player", {
                "alive": alive,
                "hp_ratio": hp,
                "cp_ratio": data.get("cp_ratio"),
            })

            # HUD vitals
            try:
                if self.hud_window and pool_get(self.state, "focus.has_focus"):
                    h = "" if hp is None else str(int(max(0, min(1.0, float(hp))) * 100))
                    cp = data.get("cp_ratio")
                    c = "" if cp is None else str(int(max(0, min(1.0, float(cp))) * 100))
                    self.hud_window.evaluate_js(
                        f"window.ReviveHUD && window.ReviveHUD.setHP({json.dumps(h)}, {json.dumps(c)})"
                    )
            except Exception as e:
                print(f"[HUD] hp set error: {e}")

        self.ps_service = PlayerStateService(
            server=lambda: pool_get(self.state, "config.server", "boh"),
            get_window=lambda: pool_get(self.state, "window.info", None),
            on_update=_on_ps_update,
            on_status=self.ui.log,
        )

        # --- Window Focus service ---
        def _on_wf_update(data: Dict[str, Any]):
            prev_focus = pool_get(self.state, "focus.has_focus", None)
            try:
                has_focus = bool(data.get("has_focus"))
            except Exception:
                has_focus = False

            pool_write(self.state, "focus", {"has_focus": has_focus})

            # OFF → сброс vitals
            if has_focus is False:
                pool_write(self.state, "player", {"alive": None, "hp_ratio": None, "cp_ratio": None})
                try:
                    if self.hud_window:
                        self.hud_window.evaluate_js("window.ReviveHUD && window.ReviveHUD.setHP('--','')")
                except Exception:
                    pass
            # ON после OFF → восстановить HUD из пула
            elif self.hud_window and prev_focus is not True:
                last = pool_get(self.state, "player", {}) or {}
                hp = last.get("hp_ratio"); cp = last.get("cp_ratio")
                h = "" if hp is None else str(int(max(0, min(1.0, float(h))) * 100))
                c = "" if cp is None else str(int(max(0, min(1.0, float(cp))) * 100))
                try:
                    self.hud_window.evaluate_js(
                        f"window.ReviveHUD && window.ReviveHUD.setHP({json.dumps(h)}, {json.dumps(c)})"
                    )
                except Exception:
                    pass

            # статус в UI при смене
            if prev_focus is None or prev_focus != has_focus:
                txt = f"Фокус окна: {'да' if has_focus else 'нет'}"
                self.ui.log(f"[FOCUS] {'ON' if has_focus else 'OFF'}")
                self.ui.ui_emit("focus", txt, True if has_focus else None)

        self.wf_service = WindowFocusService(
            get_window=lambda: pool_get(self.state, "window.info", None),
            on_update=_on_wf_update,
            on_status=None,
        )

        # --- Macros Repeat service ---
        self.macros_repeat_service = MacrosRepeatService(
            server=lambda: pool_get(self.state, "config.server", "boh"),
            controller=self.controller,
            get_window=lambda: pool_get(self.state, "window.info", None),
            get_language=lambda: pool_get(self.state, "config.language", "rus"),
            get_rows=lambda: list(pool_get(self.state, "features.macros.rows", []) or []),
            is_enabled=lambda: bool(pool_get(self.state, "features.macros.repeat_enabled", False)),
            is_alive=lambda: bool(pool_get(self.state, "player.alive", False)),
            on_status=self.ui.log_ok,
        )

        self.ps_adapter = PSAdapter(self.state)

    # --- lifecycle ---
    def start(self):
        self.wf_service.start(poll_interval=1.0)
        pool_write(self.state, "services.window_focus", {"running": True})

        self.ps_service.start(poll_interval=1.0)
        pool_write(self.state, "services.player_state", {"running": True})

        self.macros_repeat_service.start(poll_interval=1.0)
        pool_write(self.state, "services.macros_repeat", {"running": True})

    def stop(self):
        try:
            self.ps_service.stop()
        except Exception as e:
            print(f"[shutdown] ps_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.player_state", {"running": False})

        try:
            self.wf_service.stop()
        except Exception as e:
            print(f"[shutdown] wf_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.window_focus", {"running": False})

        try:
            self.macros_repeat_service.stop()
        except Exception as e:
            print(f"[shutdown] macros_repeat_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.macros_repeat", {"running": False})
