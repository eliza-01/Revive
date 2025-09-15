# app/launcher/sections/record.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import time, threading

from core.state.pool import pool_get, pool_write
from core.logging import console
from core.engines.record.runner import RecordRunner

# RAW мышь (без фолбэков)
from core.os.win.rawmouse import RawMouseThread

# --- глобальные хоткеи/мышь через pynput ---
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
    record_play_now, record_hotkey, record_set_enabled
    """

    def __init__(self, *, state: Dict[str, Any], controller: Any, get_window):
        self.state = state
        self.runner = RecordRunner(state, controller, get_window)
        # первичная синхронизация списка файлов в пул
        self.runner.sync_records_to_pool()

        # дескрипторы глобальных хуков
        self._hk_available = _HK_AVAILABLE
        self._mouse_listener = None
        self._kbd_listener = None
        self._ctrl_down = False

        # RAW input
        self._raw_thread: Optional[RawMouseThread] = None

        # анти-дребезг для Ctrl + wheel_down
        self._last_ctrl_wheel_ts = 0.0
        self._ctrl_wheel_cooldown_s = 1.0
        self._last_stop_reason: Optional[str] = None

    def last_stop_reason(self) -> Optional[str]:
        return self._last_stop_reason

    # ---------- глобальные хуки ----------
    def start_global_hooks(self):
        """Запустить глобальные хуки ввода."""
        # --- клавиатура: Ctrl+R ---
        if self._hk_available and self._kbd_listener is None:
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
                        # (а также подстрахуемся по символу 'r'/'к')
                        if self._ctrl_down and (vk == VK_R or (ch and ch.lower() in ("r", "к"))):
                            console.log("[hotkey] CTRL+R fired (listener)")
                            self.record_hotkey("ctrlR")
                    except Exception as e:
                        console.log(f"[hotkey] listener press error: {e}")

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

        # --- мышь через pynput (клики и резервное колесо/движение) ---
        if self._hk_available and self._mouse_listener is None:
            try:
                eng = self.runner.engine

                def raw_alive() -> bool:
                    return bool(self._raw_thread and self._raw_thread.is_alive())

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
                        # Если RAW поток жив — он отдаёт dx/dy; движение через pynput не пишем
                        if raw_alive():
                            return
                        eng.on_mouse_move(x, y)
                    except Exception:
                        pass

                def _on_scroll(x, y, dx, dy):
                    try:
                        # Ctrl + wheel_down => «Запустить сейчас» с ожиданием фокуса
                        if self._ctrl_down and dy < 0:
                            now = time.time()
                            if now - self._last_ctrl_wheel_ts >= self._ctrl_wheel_cooldown_s:
                                self._last_ctrl_wheel_ts = now
                                console.log("[hotkey] CTRL + wheel_down -> record_play_now(wait focus)")
                                self._play_now_hotkey()
                            return  # не писать это в запись

                        # Если RAW поток жив — колесо прийдёт оттуда; тут не пишем (чтобы не задублировать)
                        if raw_alive():
                            return

                        # обычная запись колеса через pynput (когда RAW недоступен)
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

        # --- RAW mouse ---
        if self._raw_thread is None:
            try:
                def _raw_cb(dx: int, dy: int, flags: int, wheel: int, ts: float):
                    # Все сырые события отдаём движку
                    try:
                        self.runner.engine.on_raw_input(dx, dy, flags, wheel, ts)
                    except Exception as e:
                        console.log(f"[record] on_raw_input error: {e}")

                self._raw_thread = RawMouseThread(callback=_raw_cb)
                self._raw_thread.start()
                console.log("[record] raw mouse thread started")
            except Exception as e:
                # без фолбэков: если RAW не поднялся — пишем ошибку в лог
                console.log(f"[record] raw mouse start error: {e}")
                self._raw_thread = None

    def stop_global_hooks(self):
        """Остановить глобальные хуки, если они были запущены."""
        # клавиатура
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

        # мышь pynput
        try:
            if self._mouse_listener:
                self._mouse_listener.stop()
                self._mouse_listener.join(0.5)
                console.log("[record] mouse listener stopped")
        except Exception:
            pass
        finally:
            self._mouse_listener = None

        # RAW
        try:
            if self._raw_thread:
                self._raw_thread.stop()
                self._raw_thread.join(0.5)
                console.log("[record] raw mouse thread stopped")
        except Exception:
            pass
        finally:
            self._raw_thread = None

    # ---------- helpers ----------
    def _wait_focus(self, timeout_s: float = 6.0) -> bool:
        end = time.time() + max(0.0, timeout_s)
        while time.time() < end:
            v = pool_get(self.state, "focus.is_focused", None)
            if v is not False:   # True или None — считаем, что можно
                return True
            time.sleep(0.05)
        v = pool_get(self.state, "focus.is_focused", None)
        return v is not False

    def _focus_now(self) -> Optional[bool]:
        try:
            v = pool_get(self.state, "focus.is_focused", None)
            return bool(v) if isinstance(v, bool) else None
        except Exception:
            return None

    def _play_now_hotkey(self):
        """Горячий вызов 'Запустить сейчас' в отдельном потоке (не блокировать слушатели)."""
        def _run():
            try:
                r = self.record_play_now()
                console.log(f"[record.hotkey] Ctrl+wheel_down -> play_now: {r}")
            except Exception as e:
                console.log(f"[record.hotkey] play_now error: {e}")
        threading.Thread(target=_run, daemon=True).start()

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
        try:
            ok = self.runner.engine.play(
                wait_focus_cb=self._wait_focus,  # ждём фокус
                countdown_s=1.0
            )
            return {"ok": bool(ok), "mode": "played" if ok else "error"}
        except Exception as e:
            console.log(f"[record.hotkey] play_now error: {e}")
            return {"ok": False, "mode": "error"}

    def record_hotkey(self, key: str) -> Dict[str, Any]:
        try:
            console.log(f"[record.ui] record_hotkey({key})")
            self.runner.handle_hotkey(str(key or ""))
            return {"ok": True}
        except Exception as e:
            console.log(f"[record.ui] record_hotkey error: {e}")
            return {"ok": False}

    def record_set_enabled(self, enabled: bool) -> Dict[str, Any]:
        val = bool(enabled)
        pool_write(self.state, "features.record", {"enabled": val})
        console.log(f"[record.ui] set enabled={val}")
        return {"ok": True, "enabled": val}

    def expose(self) -> dict:
        """Экспорт API в pywebview."""
        return {
            "record_state": self.record_state,
            "record_list": self.record_list,
            "record_create": self.record_create,
            "record_set_current": self.record_set_current,
            "record_play_now": self.record_play_now,
            "record_hotkey": self.record_hotkey,
            "record_set_enabled": self.record_set_enabled,
        }


# Фабрика для регистратора секций лаунчера
def create(*, state: Dict[str, Any], controller: Any, get_window):
    return RecordSection(state=state, controller=controller, get_window=get_window)
