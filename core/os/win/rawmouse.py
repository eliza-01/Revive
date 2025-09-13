# core/os/win/rawmouse.py
from __future__ import annotations
import ctypes as C
import ctypes.wintypes as W
import threading
import time

# ---- кросс-версийные алиасы типов ----
PTR_64 = (C.sizeof(C.c_void_p) == 8)

def _ensure(name: str, typ):
    if not hasattr(W, name):
        setattr(W, name, typ)

# Базовые указатели/интегралы
LONG_PTR  = C.c_longlong if PTR_64 else C.c_long
ULONG_PTR = C.c_ulonglong if PTR_64 else C.c_ulong

_ensure('LRESULT', LONG_PTR)        # LRESULT = LONG_PTR
_ensure('LPARAM',  LONG_PTR)        # LPARAM = LONG_PTR
_ensure('WPARAM',  ULONG_PTR)       # WPARAM = UINT_PTR
_ensure('UINT',    C.c_uint)
_ensure('ATOM',    C.c_ushort)

# HANDLE и родственные
HANDLE_T = getattr(W, 'HANDLE', C.c_void_p)
for _h in ('HCURSOR', 'HICON', 'HBRUSH', 'HMENU', 'HWND', 'HINSTANCE'):
    _ensure(_h, HANDLE_T)
_ensure('LPVOID', C.c_void_p)

# На всякий случай базовые C-типы
USHORT = getattr(W, 'USHORT', C.c_ushort)
ULONG  = getattr(W, 'ULONG',  C.c_ulong)
LONG   = getattr(W, 'LONG',   C.c_long)
DWORD  = getattr(W, 'DWORD',  C.c_ulong)

# ---- WinAPI/константы ----
user32   = C.windll.user32
kernel32 = C.windll.kernel32

WM_INPUT   = 0x00FF
WM_DESTROY = 0x0002
WM_CLOSE   = 0x0010

RIDEV_INPUTSINK = 0x00000100
RIM_TYPEMOUSE   = 0x00000000
RID_INPUT       = 0x10000003   # GetRawInputData

# RAWMOUSE Button flags
RI_MOUSE_LEFT_BUTTON_DOWN   = 0x0001
RI_MOUSE_LEFT_BUTTON_UP     = 0x0002
RI_MOUSE_RIGHT_BUTTON_DOWN  = 0x0004
RI_MOUSE_RIGHT_BUTTON_UP    = 0x0008
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010
RI_MOUSE_MIDDLE_BUTTON_UP   = 0x0020
RI_MOUSE_BUTTON_4_DOWN      = 0x0040
RI_MOUSE_BUTTON_4_UP        = 0x0080
RI_MOUSE_BUTTON_5_DOWN      = 0x0100
RI_MOUSE_BUTTON_5_UP        = 0x0200
RI_MOUSE_WHEEL              = 0x0400
RI_MOUSE_HWHEEL             = 0x0800

# ---- RAW structures ----
class RAWINPUTHEADER(C.Structure):
    _fields_ = [
        ("dwType", DWORD),
        ("dwSize", DWORD),
        ("hDevice", HANDLE_T),
        ("wParam", W.WPARAM),
    ]

class _RAWMOUSE_BUTTONS(C.Structure):
    _fields_ = [
        ("usButtonFlags", USHORT),
        ("usButtonData",  USHORT),
    ]

class _RAWMOUSE_Union(C.Union):
    _fields_ = [
        ("ulButtons", ULONG),
        ("Buttons",   _RAWMOUSE_BUTTONS),
    ]

class RAWMOUSE(C.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("usFlags",           USHORT),
        ("u",                 _RAWMOUSE_Union),
        ("ulRawButtons",      ULONG),
        ("lLastX",            LONG),
        ("lLastY",            LONG),
        ("ulExtraInformation", ULONG),
    ]

class _RAWINPUT_Union(C.Union):
    _fields_ = [
        ("mouse", RAWMOUSE),
    ]

class RAWINPUT(C.Structure):
    _anonymous_ = ("data",)
    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("data",   _RAWINPUT_Union),
    ]

class RAWINPUTDEVICE(C.Structure):
    _fields_ = [
        ("usUsagePage", USHORT),
        ("usUsage",     USHORT),
        ("dwFlags",     DWORD),
        ("hwndTarget",  W.HWND),
    ]

# Объявим WNDPROC заранее, чтобы сослаться в WNDCLASSW
WNDPROC = C.WINFUNCTYPE(W.LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

class WNDCLASSW(C.Structure):
    _fields_ = [
        ("style",        W.UINT),
        ("lpfnWndProc",  WNDPROC),
        ("cbClsExtra",   C.c_int),
        ("cbWndExtra",   C.c_int),
        ("hInstance",    W.HINSTANCE),
        ("hIcon",        W.HICON),
        ("hCursor",      W.HCURSOR),
        ("hbrBackground",W.HBRUSH),
        ("lpszMenuName", W.LPCWSTR),
        ("lpszClassName",W.LPCWSTR),
    ]

# Сигнатуры вызовов
user32.DefWindowProcW.restype  = W.LRESULT
user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]

user32.RegisterClassW.restype  = W.ATOM
user32.RegisterClassW.argtypes = [C.POINTER(WNDCLASSW)]

user32.CreateWindowExW.restype  = W.HWND
user32.CreateWindowExW.argtypes = [
    DWORD, W.LPCWSTR, W.LPCWSTR, DWORD,
    C.c_int, C.c_int, C.c_int, C.c_int,
    W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID
]

user32.RegisterRawInputDevices.restype  = W.BOOL
user32.RegisterRawInputDevices.argtypes = [C.POINTER(RAWINPUTDEVICE), W.UINT, W.UINT]

user32.GetRawInputData.restype  = W.UINT
user32.GetRawInputData.argtypes = [W.HANDLE, W.UINT, W.LPVOID, C.POINTER(W.UINT), W.UINT]

user32.GetMessageW.restype  = C.c_int
user32.GetMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]

user32.TranslateMessage.argtypes = [C.POINTER(W.MSG)]
user32.DispatchMessageW.argtypes = [C.POINTER(W.MSG)]

user32.PostQuitMessage.argtypes = [C.c_int]
user32.PostMessageW.argtypes    = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.DestroyWindow.restype    = W.BOOL
user32.DestroyWindow.argtypes   = [W.HWND]

kernel32.GetModuleHandleW.restype  = W.HINSTANCE
kernel32.GetModuleHandleW.argtypes = [W.LPCWSTR]

# ------------------------------------------------------------------------------
# Поток приёмника RAW мыши
# ------------------------------------------------------------------------------
class RawMouseThread(threading.Thread):
    """
    Создаёт скрытое окно, регистрирует RAW mouse (RIDEV_INPUTSINK) и вызывает
    callback(dx, dy, btn_flags, wheel, ts). wheel — знаковый delta (напр. 120 / -120) либо 0.
    """
    def __init__(self, *, callback):
        super().__init__(daemon=True)
        self._cb = callback
        self._hwnd = None
        self._stop_event = threading.Event()
        self._wndproc = None  # держим ref

    def run(self):
        cls_name = "ReviveRawMouseWnd"

        def _proc(hWnd, msg, wParam, lParam):
            if msg == WM_INPUT:
                try:
                    self._handle_input(lParam)
                except Exception:
                    pass
                return 0
            elif msg == WM_CLOSE:
                user32.DestroyWindow(hWnd)
                return 0
            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hWnd, msg, wParam, lParam)

        self._wndproc = WNDPROC(_proc)

        # Регистрация класса окна
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._wndproc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = "ReviveRawMouseWnd"

        if not user32.RegisterClassW(C.byref(wc)):
            # класс мог быть уже зарегистрирован — ок
            pass

        # Создаём окно (невидимое)
        hwnd = user32.CreateWindowExW(
            0, cls_name, "rawmouse", 0,
            0, 0, 0, 0,
            None, None, hinst, None
        )
        if not hwnd:
            return
        self._hwnd = hwnd

        # Регистрируем RAW mouse на это окно (получаем в фоне)
        rid = RAWINPUTDEVICE()
        rid.usUsagePage = 0x01  # Generic Desktop Controls
        rid.usUsage     = 0x02  # Mouse
        rid.dwFlags     = RIDEV_INPUTSINK
        rid.hwndTarget  = hwnd

        if not user32.RegisterRawInputDevices(C.byref(rid), 1, C.sizeof(RAWINPUTDEVICE)):
            return

        # Цикл сообщений
        msg = W.MSG()
        while not self._stop_event.is_set():
            r = user32.GetMessageW(C.byref(msg), None, 0, 0)
            if r <= 0:
                break
            user32.TranslateMessage(C.byref(msg))
            user32.DispatchMessageW(C.byref(msg))

    def stop(self):
        self._stop_event.set()
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)

    # ---- internal: читать RAW пакет ----
    def _handle_input(self, lParam):
        size = W.UINT(0)
        header_sz = C.sizeof(RAWINPUTHEADER)

        rc = user32.GetRawInputData(C.c_void_p(lParam), RID_INPUT, None, C.byref(size), header_sz)
        if rc == 0 and size.value:
            buf = C.create_string_buffer(size.value)
            rc2 = user32.GetRawInputData(C.c_void_p(lParam), RID_INPUT, buf, C.byref(size), header_sz)
            if rc2 == size.value:
                ri = C.cast(buf, C.POINTER(RAWINPUT)).contents
                if ri.header.dwType == RIM_TYPEMOUSE:
                    m = ri.data.mouse
                    dx = int(m.lLastX)
                    dy = int(m.lLastY)
                    btn_flags = int(m.Buttons.usButtonFlags)
                    wheel = 0
                    if btn_flags & RI_MOUSE_WHEEL:
                        wheel = C.c_short(m.Buttons.usButtonData).value
                    if callable(self._cb):
                        self._cb(dx, dy, btn_flags, wheel, time.time())
