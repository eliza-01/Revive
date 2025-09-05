# core/engines/window_focus/server/common/engine.py
from __future__ import annotations
import time
import ctypes
from ctypes import wintypes
from typing import Dict, Any, Optional, Callable

DEFAULT_POLL_INTERVAL: float = 2.0  # сек

user32 = ctypes.WinDLL("user32", use_last_error=True)

_GetForegroundWindow = user32.GetForegroundWindow
_GetForegroundWindow.restype = wintypes.HWND
_GetForegroundWindow.argtypes = []

_GetAncestor = user32.GetAncestor
_GetAncestor.restype = wintypes.HWND
_GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]

GA_ROOT      = 2
GA_ROOTOWNER = 3

def _emit(status_cb: Optional[Callable[[str, Optional[bool]], None]], msg: str, ok: Optional[bool] = None):
    try:
        if callable(status_cb):
            status_cb(msg, ok)
        else:
            print(f"[window_focus/common] {msg}")
    except Exception:
        print(f"[window_focus/common] {msg}")

def _extract_hwnd(win: Dict[str, Any]) -> int:
    if not isinstance(win, dict):
        return 0
    for key in ("hwnd", "hWnd", "handle", "id"):
        if key in win:
            try:
                val = int(win[key])
                if val > 0:
                    return val
            except Exception:
                pass
    return 0

def _hwnd_value(h) -> int:
    try:
        # поддержка: int, ctypes HWND (имеет .value), None
        return int(h) if isinstance(h, int) else int(getattr(h, "value", 0)) or 0
    except Exception:
        return 0

def _normalize_hwnd(hwnd: int) -> int:
    try:
        h = wintypes.HWND(hwnd)
        root = _GetAncestor(h, GA_ROOT)
        return _hwnd_value(root) or _hwnd_value(h)
    except Exception:
        return _hwnd_value(hwnd)

def _is_window_focused(target_hwnd: int) -> bool:
    t = _hwnd_value(target_hwnd)
    if not t:
        return False
    try:
        fg = _hwnd_value(_GetForegroundWindow())
        if not fg:
            return False

        # 1) сравнение по GA_ROOT
        a = _normalize_hwnd(fg)
        b = _normalize_hwnd(t)
        if a and b and a == b:
            return True

        # 2) fallback: сравнение по GA_ROOTOWNER
        try:
            h_fg = wintypes.HWND(fg)
            h_t  = wintypes.HWND(t)
            a2 = _hwnd_value(_GetAncestor(h_fg, GA_ROOTOWNER)) or _hwnd_value(h_fg)
            b2 = _hwnd_value(_GetAncestor(h_t,  GA_ROOTOWNER)) or _hwnd_value(h_t)
            return a2 and b2 and a2 == b2
        except Exception:
            return False
    except Exception:
        return False


def start(ctx_base: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """
    Движок window_focus (пока только фокус окна).
    Каждые poll_interval секунд публикует:
      on_update({"has_focus": bool, "ts": now})
    Работает, пока should_abort() не вернёт True.
    """
    get_window = ctx_base.get("get_window")
    on_status: Callable[[str, Optional[bool]], None] = ctx_base.get("on_status") or (lambda *_: None)
    on_update: Optional[Callable[[Dict[str, Any]], None]] = ctx_base.get("on_update")
    should_abort: Callable[[], bool] = ctx_base.get("should_abort") or (lambda: False)

    poll_interval = float(cfg.get("poll_interval", DEFAULT_POLL_INTERVAL))
    debug_focus = bool(cfg.get("debug_focus", False))

    _emit(on_status, f"[window_focus] старт (poll={poll_interval}s)…", None)

    last_state: Optional[bool] = None
    try:
        while True:
            if should_abort():
                _emit(on_status, "[window_focus] остановлено пользователем", True)
                return True

            win = None
            try:
                win = get_window() if callable(get_window) else None
            except Exception:
                win = None

            hwnd = _extract_hwnd(win or {})
            focused = _is_window_focused(hwnd)

            # DEBUG: одна строка с конкретными хэндлами (по запросу через cfg)
            if debug_focus:
                try:
                    fg = _hwnd_value(_GetForegroundWindow())
                    a = _normalize_hwnd(fg)
                    b = _normalize_hwnd(hwnd)
                    _emit(on_status, f"[window_focus] dbg: target={hwnd} norm={b} fg={fg} fg_norm={a}", None)
                except Exception:
                    pass

            if on_update:
                try:
                    on_update({"has_focus": bool(focused), "ts": time.time()})
                except Exception:
                    pass

            if last_state is None or focused != last_state:
                _emit(on_status, f"[window_focus] фокус окна: {'да' if focused else 'нет'}", True if focused else None)
                last_state = focused

            time.sleep(poll_interval)
    except Exception as e:
        _emit(on_status, f"[window_focus] ошибка: {e}", False)
        return False
