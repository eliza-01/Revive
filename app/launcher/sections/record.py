# app/launcher/sections/record.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.state.pool import pool_get, pool_write
from core.logging import console
from core.engines.record.runner import RecordRunner

# --- опционально: глобальные хоткеи/мышь через pynput ---
try:
    from pynput import keyboard as _hk_keyboard
    from pynput import mouse as _hk_mouse
    _HK_AVAILABLE = True
except Exception as _e:
    _HK_AVAILABLE = False


class RecordSection:
    """
    Секция лаунчера для блока «Запись».
    Экспортируемые методы: record_state, record_list, record_create, record_set_current,
    record_play_now, record_hotkey
    """

    def __init__(self, *, state: Dict[str, Any], controller: Any, get_window):
        self.state = state
        self.runner = RecordRunner(state, controller, get_window)
        # первичная синхронизация списка файлов в пул
        self.runner.sync_records_to_pool()

        # дескрипторы глобальных хуков
        self._hk_available = _HK_AVAILABLE
        self._hotkey_handle = None
        self._mouse_listener = None

        self._kbd_listener = None
        self._ctrl_down = False

    # ---------- глобальные хуки ----------
    def start_global_hooks(self):
        """Запустить глобальный хоткей Ctrl+R и хук мыши (если есть pynput)."""
        if not self._hk_available:
            console.log("[record] pynput not available — global hooks disabled")
            return

        # --- Ctrl+R ---
        if self._kbd_listener is None:
            try:
                VK_R = 0x52  # виртуальный код клавиши R на Windows
                CTRL_KEYS = {_hk_keyboard.Key.ctrl, _hk_keyboard.Key.ctrl_l, _hk_keyboard.Key.ctrl_r}

                def _on_press(key):
                    try:
                        if key in CTRL_KEYS:
                            self._ctrl_down = True
                            return
                        vk = getattr(key, "vk", None)
                        ch = getattr(key, "char", None)
                        # Срабатываем, если зажат Ctrl и нажата физическая клавиша R
                        # (а также подстрахуемся по символу 'r'/'к' на всякий случай)
                        if self._ctrl_down and (vk == VK_R or (ch and ch.lower() in ("r", "к"))):
                            from core.logging import console as _c
                            _c.log("[hotkey] CTRL+R fired (listener)")
                            self.record_hotkey("ctrlR")
                    except Exception as e:
                        from core.logging import console as _c
                        _c.log(f"[hotkey] listener press error: {e}")

                def _on_release(key):
                    try:
                        if key in CTRL_KEYS:
                            self._ctrl_down = False
                    except Exception:
                        pass

                self._kbd_listener = _hk_keyboard.Listener(
                    on_press=_on_press, on_release=_on_release
                )
                self._kbd_listener.start()
                console.log("[hotkey] keyboard listener started (VK=0x52)")
            except Exception as e:
                console.log(f"[hotkey] keyboard listener start error: {e}")
                self._kbd_listener = None

        # --- Mouse listener ---
        if self._mouse_listener is None:
            try:
                eng = self.runner.engine

                def _on_click(x, y, button, pressed):
                    try:
                        if button == _hk_mouse.Button.left and pressed:
                            eng.on_mouse_left_click(x, y)
                        elif button == _hk_mouse.Button.right:
                            if pressed:
                                eng.on_mouse_right_press(x, y)
                            else:
                                eng.on_mouse_right_release(x, y)
                    except Exception:
                        pass

                def _on_move(x, y):
                    try:
                        eng.on_mouse_move(x, y)
                    except Exception:
                        pass

                def _on_scroll(x, y, dx, dy):
                    try:
                        if dy > 0:
                            eng.on_wheel_up()
                        elif dy < 0:
                            eng.on_wheel_down()
                    except Exception:
                        pass

                self._mouse_listener = _hk_mouse.Listener(
                    on_click=_on_click,
                    on_move=_on_move,
                    on_scroll=_on_scroll
                )
                self._mouse_listener.start()
                console.log("[record] global mouse listener started")
            except Exception as e:
                console.log(f"[record] mouse listener start error: {e}")
                self._mouse_listener = None

    def stop_global_hooks(self):
        """Остановить глобальные хуки, если они были запущены."""
        try:
            if self._kbd_listener:
                self._kbd_listener.stop()
                self._kbd_listener.join(0.5)
                console.log("[hotkey] keyboard listener stopped")
        except Exception:
            pass
        finally:
            self._kbd_listener = None
            self._ctrl_down = False

        try:
            if self._mouse_listener:
                self._mouse_listener.stop()
                self._mouse_listener.join(0.5)
                console.log("[record] mouse listener stopped")
        except Exception:
            pass
        finally:
            self._mouse_listener = None

    # ---------- helpers ----------

    def _focus_now(self) -> Optional[bool]:
        try:
            v = pool_get(self.state, "focus.is_focused", None)
            return bool(v) if isinstance(v, bool) else None
        except Exception:
            return None

    # ---------- API ----------

    def record_state(self) -> Dict[str, Any]:
        rec = dict(pool_get(self.state, "features.record", {}) or {})
        rec["focused"] = self._focus_now()
        return rec

    def record_list(self) -> List[Dict[str, str]]:
        self.runner.sync_records_to_pool()
        return list(pool_get(self.state, "features.record.records", []) or [])

    def record_create(self, name: str) -> Dict[str, Any]:
        name = str(name or "").strip()
        if not name:
            return {"ok": False, "error": "empty_name"}
        slug = self.runner.create_record(name)
        try:
            pool_write(self.state, "features.record", {"current_record": slug})
        except Exception:
            pass
        return {"ok": True, "slug": slug}

    def record_set_current(self, slug: str) -> Dict[str, Any]:
        slug = str(slug or "").strip()
        if not slug:
            return {"ok": False}
        self.runner.set_current(slug)
        return {"ok": True}

    def record_play_now(self) -> Dict[str, Any]:
        focused = (self._focus_now() is not False)
        if focused:
            ok = self.runner.engine.play(wait_focus_cb=None, countdown_s=3.0)
            return {"ok": bool(ok), "mode": "played" if ok else "error"}
        else:
            try:
                pool_write(self.state, "features.record", {"enabled": True})
                console.hud("ok", "[record] нет фокуса — поставлено в очередь")
            except Exception:
                return {"ok": False, "mode": "error"}
            return {"ok": True, "mode": "queued"}

    def record_hotkey(self, key: str) -> Dict[str, Any]:
        try:
            console.log(f"[record.ui] record_hotkey({key})")
            self.runner.handle_hotkey(str(key or ""))
            return {"ok": True}
        except Exception as e:
            console.log(f"[record.ui] record_hotkey error: {e}")
            return {"ok": False}


    def expose(self) -> dict:
        """Экспорт API в pywebview."""
        return {
            "record_state": self.record_state,
            "record_list": self.record_list,
            "record_create": self.record_create,
            "record_set_current": self.record_set_current,
            "record_play_now": self.record_play_now,
            "record_hotkey": self.record_hotkey,
        }

# Фабрика для регистратора секций лаунчера
def create(*, state: Dict[str, Any], controller: Any, get_window):
    return RecordSection(state=state, controller=controller, get_window=get_window)
