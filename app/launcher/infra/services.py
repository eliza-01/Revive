# app/launcher/infra/services.py
from __future__ import annotations
from typing import Any, Dict, Optional
import json

from core.state.pool import pool_get, pool_write
from core.engines.player_state.service import PlayerStateService
from core.engines.window_focus.service import WindowFocusService
from core.engines.macros.service import MacrosRepeatService
from core.engines.autofarm.service import AutoFarmService

from core.logging import console

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
    def __init__(self, state: Dict[str, Any], window, hud_window, ui, controller):
        self.state = state
        self.window = window
        self.hud_window = hud_window
        self.ui = ui
        self.controller = controller

        # PS adapter нужен сразу (используется ниже/снаружи)
        self.ps_adapter = PSAdapter(self.state)

        # --- helpers для HUD ---
        def _status_map(ok: Optional[bool]) -> str:
            return "succ" if ok is True else "err" if ok is False else "ok"

        def _on_status(msg: str, ok: Optional[bool] = None):
            # консоль + HUD
            if ok is None:
                console.log(msg)
            else:
                console.log(f"{msg} [{'OK' if ok else 'FAIL'}]")
            console.hud(_status_map(ok), msg)

        def _on_status_macros(msg: str, ok: Optional[bool] = None):
            console.log(f"[MACROS] {msg}")
            console.hud(_status_map(ok), f"Повтор макроса: {msg}")

        # --- Player State service ---
        def _on_ps_update(data: Dict[str, Any]):
            hp = data.get("hp_ratio")
            # не трогаем vitals, если нет фокуса
            if pool_get(self.state, "focus.is_focused") is False:
                return

            alive = None if hp is None else bool(hp > 0.001)
            pool_write(self.state, "player", {
                "alive": alive,
                "hp_ratio": hp,
                "cp_ratio": data.get("cp_ratio"),
            })

            # HUD vitals
            try:
                if self.hud_window and pool_get(self.state, "focus.is_focused"):
                    h = "" if hp is None else str(int(max(0, min(1.0, float(hp))) * 100))
                    cp = data.get("cp_ratio")
                    c = "" if cp is None else str(int(max(0, min(1.0, float(cp))) * 100))
                    self.hud_window.evaluate_js(
                        f"window.ReviveHUD && window.ReviveHUD.setHP({json.dumps(h)}, {json.dumps(c)})"
                    )
            except Exception as e:
                console.log(f"[HUD] hp set error: {e}")

        self.ps_service = PlayerStateService(
            server=lambda: pool_get(self.state, "config.server", "boh"),
            get_window=lambda: pool_get(self.state, "window.info", None),
            on_update=_on_ps_update,
        )

        # --- Window Focus service ---
        def _on_wf_update(data: Dict[str, Any]):
            prev_focus = pool_get(self.state, "focus.is_focused", None)
            try:
                is_focused = bool(data.get("is_focused"))
            except Exception:
                is_focused = False

            pool_write(self.state, "focus", {"is_focused": is_focused})

            # ← ДО любых побочных эффектов: на фронте перехода ON->OFF делаем мгновенный снимок busy
            if (is_focused is False) and (prev_focus is not False):
                saved_busy = {
                    "respawn": bool(pool_get(self.state, "features.respawn.busy", False)),
                    "buff": bool(pool_get(self.state, "features.buff.busy", False)),
                    "macros": bool(pool_get(self.state, "features.macros.busy", False)),
                    "teleport": bool(pool_get(self.state, "features.teleport.busy", False)),
                    "autofarm": bool(pool_get(self.state, "features.autofarm.busy", False)),
                }
                # сохраняем снимок, чтобы правило паузы не «перезаписало» его уже обнулёнными флагами
                pool_write(self.state, "runtime.focus_pause", {"saved_busy": dict(saved_busy)})

            # OFF → сброс vitals
            if is_focused is False:
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
                h = "" if hp is None else str(int(max(0, min(1.0, float(hp))) * 100))
                c = "" if cp is None else str(int(max(0, min(1.0, float(cp))) * 100))
                try:
                    self.hud_window.evaluate_js(
                        f"window.ReviveHUD && window.ReviveHUD.setHP({json.dumps(h)}, {json.dumps(c)})"
                    )
                except Exception:
                    pass

            # статус (раньше шёл в UI через ui_emit) — теперь в HUD
            if prev_focus is None or prev_focus != is_focused:
                txt = f"Фокус окна: {'да' if is_focused else 'нет'}"
                console.hud("succ" if is_focused else "err", txt)

        self.wf_service = WindowFocusService(
            get_window=lambda: pool_get(self.state, "window.info", None),
            on_update=_on_wf_update,
        )

        # --- Macros Repeat service ---
        self.macros_repeat_service = MacrosRepeatService(
            server=lambda: pool_get(self.state, "config.server", "boh"),
            controller=self.controller,
            get_window=lambda: pool_get(self.state, "window.info", None),
            get_language=lambda: pool_get(self.state, "config.language", "rus"),
            get_rows=lambda: list(pool_get(self.state, "features.macros.rows", []) or []),
            is_enabled=lambda: bool(pool_get(self.state, "features.macros.repeat_enabled", False)),
            is_alive=lambda: pool_get(self.state, "player.alive", None),
            is_focused=lambda: bool(pool_get(self.state, "focus.is_focused", False)),
            set_busy=lambda b: pool_write(self.state, "features.macros", {"busy": bool(b)}),
        )

        # --- AutoFarm service ---
        self.autofarm_service = AutoFarmService(
            server=lambda: pool_get(self.state, "config.server", "boh"),
            controller=self.controller,
            get_window=lambda: pool_get(self.state, "window.info", None),
            get_language=lambda: pool_get(self.state, "config.language", "rus"),
            get_cfg=lambda: pool_get(self.state, "features.autofarm", {}),  # ВЕСЬ узел, не только .config
            is_enabled=lambda: bool(pool_get(self.state, "features.autofarm.enabled", False)),
            is_alive=lambda: pool_get(self.state, "player.alive", None),
            is_focused=lambda: bool(pool_get(self.state, "focus.is_focused", False)),
            set_busy=lambda b: pool_write(self.state, "features.autofarm", {"busy": bool(b)}),
        )

        # Доступ сервисов для правил
        try:
            self.state.setdefault("_services", {})
            self.state["_services"].update({
                "autofarm": self.autofarm_service,
                "macros_repeat": self.macros_repeat_service,
                "player_state": self.ps_service,   # нужно для focus_pause_rule
                # "window_focus": self.wf_service,
            })
        except Exception:
            pass

    # --- lifecycle ---
    def start(self):
        self.wf_service.start(poll_interval=1.0)
        pool_write(self.state, "services.window_focus", {"running": True})

        self.ps_service.start(poll_interval=1.0)
        pool_write(self.state, "services.player_state", {"running": True})

        self.macros_repeat_service.start(poll_interval=1.0)
        pool_write(self.state, "services.macros_repeat", {"running": True})

        self.autofarm_service.start(poll_interval=1.0)
        pool_write(self.state, "services.autofarm", {"running": True})

    def stop(self):
        try:
            self.ps_service.stop()
        except Exception as e:
            console.log(f"[shutdown] ps_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.player_state", {"running": False})

        try:
            self.wf_service.stop()
        except Exception as e:
            console.log(f"[shutdown] wf_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.window_focus", {"running": False})

        try:
            self.macros_repeat_service.stop()
        except Exception as e:
            console.log(f"[shutdown] macros_repeat_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.macros_repeat", {"running": False})

        try:
            self.autofarm_service.stop()
        except Exception as e:
            console.log(f"[shutdown] autofarm_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.autofarm", {"running": False})
