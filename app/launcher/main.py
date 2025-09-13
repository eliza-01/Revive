# app/launcher/main.py
# минимум обязанностей: создать окно, собрать секции, экспортировать их методы.
from __future__ import annotations
import os, sys, json
import webview
from .wiring import build_container
import tempfile, subprocess, ctypes
import screeninfo
from app.api.api_router import APIRouter

api = APIRouter()

_SPLASH_PS = r"""param($gif, $ico)
Add-Type -Name U32 -Namespace Win -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[Win.U32]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -Namespace Shell -Name AppID -MemberDefinition '[DllImport("shell32.dll")] public static extern int SetCurrentProcessExplicitAppUserModelID([MarshalAs(UnmanagedType.LPWStr)] string AppID);'
[Shell.AppID]::SetCurrentProcessExplicitAppUserModelID("Revive.App") | Out-Null

$u = (New-Object System.Uri($gif)).AbsoluteUri

$html = @"
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
html,body{margin:0;height:100%;background:#111;color:#fff}
.container{position:relative;width:360px;height:170px}
img{position:absolute;left:144px;top:28px;width:72px;height:72px}
p{position:absolute;top:110px;width:100%;text-align:center;font:900 13px 'Segoe UI', Tahoma, Verdana, system-ui}
</style></head>
<body>
<div class="container">
  <img src="$u" alt="">
  <p>Загрузка Revive…</p>
</div>
</body></html>
"@

$w=360;$h=170
$wa=[System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$left=[int]($wa.Left + ($wa.Width - $w)/2)
$top =[int]($wa.Top  + ($wa.Height - $h)/2)

$form=New-Object System.Windows.Forms.Form
$form.FormBorderStyle=[System.Windows.Forms.FormBorderStyle]::None
$form.StartPosition=[System.Windows.Forms.FormStartPosition]::Manual
$form.BackColor=[System.Drawing.Color]::FromArgb(17,17,17)
$form.TopMost=$true
$form.ShowInTaskbar=$true
$form.Location=New-Object System.Drawing.Point($left,$top)
$form.Size=New-Object System.Drawing.Size($w,$h)
$form.Icon = New-Object System.Drawing.Icon($ico)

$wb = New-Object System.Windows.Forms.WebBrowser
$wb.ScrollBarsEnabled = $false
$wb.Dock = 'Fill'
$wb.ScriptErrorsSuppressed = $true
$form.Controls.Add($wb)
$wb.DocumentText = $html

[System.Windows.Forms.Application]::Run($form)
"""

def _spawn_splash(gif_path: str):
    try:
        fd, ps1 = tempfile.mkstemp(suffix=".ps1"); os.close(fd)
        with open(ps1, "w", encoding="utf-8") as f:
            f.write(_SPLASH_PS)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.Popen(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden", "-File", ps1, gif_path,  # было так
                _res_path("webui", "assets", "logo.ico")  # ← добавь второй аргумент
            ],
            creationflags=flags
        )
        return p, ps1
    except Exception:
        return None, None

def _kill_splash(proc, ps1_path: str|None):
    if proc:
        try: proc.terminate()
        except Exception: pass
        try: proc.wait(timeout=1)
        except Exception: pass
    if ps1_path and os.path.isfile(ps1_path):
        try: os.remove(ps1_path)
        except Exception: pass

def _res_path(*parts: str) -> str:
    base = os.path.join(getattr(sys, "_MEIPASS", ""), "app") if hasattr(sys, "_MEIPASS") else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.normpath(os.path.join(base, *parts))

def _set_window_icon(title: str, ico_path: str):
    try:
        import os, ctypes
        if not os.path.isfile(ico_path):
            return
        user32 = ctypes.windll.user32
        LR_LOADFROMFILE = 0x0010
        IMAGE_ICON = 1
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        hwnd = user32.FindWindowW(None, str(title))
        if not hwnd:
            return
        hbig = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        hsm  = user32.LoadImageW(None, str(ico_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if hbig:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hbig)
        if hsm:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hsm)
    except Exception as e:
        print("[ICON] set icon error:", e)

def launch_gui(local_version: str):
    # (Опционально, чтобы Windows группировал ярлык красиво)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Revive.App")
    except Exception:
        pass
    # +++ СПЛЭШ +++
    gif_path = _res_path("webui", "assets", "preloader1.gif")
    splash_proc, splash_ps1 = _spawn_splash(gif_path)

    try:
        index_path = _res_path("webui", "index.html")
        hud_path   = _res_path("webui", "hud.html")
        icon_path = _res_path("webui", "assets", "logo.ico")

        if not os.path.exists(index_path):
            raise RuntimeError(f"Не найден UI: {index_path}")
        if not os.path.exists(hud_path):
            raise RuntimeError(f"Не найден HUD UI: {hud_path}")

        # --- HUD окно (создаём первым, чтобы было поверх главного) ---
        # --  создается в крайнем правом углу основного монитора  --
        monitors = screeninfo.get_monitors()
        screen = next((m for m in monitors if getattr(m, "is_primary", False)), monitors[0])
        hud_width, hud_height = 420, 52
        hud_x = screen.x + screen.width - hud_width
        hud_y = screen.y  # самый верх

        hud_window = webview.create_window(
            title="Revive HUD",
            x=hud_x,
            y=hud_y,
            url=hud_path,
            width=420,                 # шире
            height=52,                 # компактнее по высоте
            resizable=False,
            frameless=True,
            easy_drag=True,            # перетаскивание за любую область без рамки
            on_top=True,               # по умолчанию поверх всех
            background_color="#000000",
        )
        hud_window.events.shown += (lambda *_: _set_window_icon("Revive HUD", icon_path))

        # API для HUD
        def hud_state():
            try:
                return {"on_top": bool(getattr(hud_window, "on_top", False))}
            except Exception as e:
                return {"error": str(e)}

        def hud_toggle_on_top():
            try:
                cur = bool(getattr(hud_window, "on_top", False))
                new_state = not cur
                import threading
                def apply():
                    try:
                        hud_window.on_top = new_state
                    except Exception as ex:
                        print("[HUD] toggle error:", ex)
                threading.Timer(0.01, apply).start()
                return {"on_top": new_state}
            except Exception as e:
                return {"error": str(e)}

        def hud_set_hp(hp: int|None, cp: int|None):
            try:
                h = "" if hp is None else f"{int(hp)}"
                c = "" if cp is None else f"{int(cp)}"
                js = f"window.ReviveHUD && window.ReviveHUD.setHP({json.dumps(h)}, {json.dumps(c)})"
                hud_window.evaluate_js(js)
            except Exception as e:
                print(f"[HUD] hp eval error: {e}")

        hud_window.expose(hud_state, hud_toggle_on_top, hud_set_hp)

        # --- Главное окно ---
        window = webview.create_window(
            title="Revive Launcher",
            url=index_path,
            width=820,
            height=900,
            resizable = True,  # не работает)
            frameless = True,  # перетаскивание за любое место тела
            easy_drag = True,
            on_top = True,  # окно поверх всех после запуска
            background_color="#000000",
            js_api=api,
        )
        window.events.shown += (lambda *_: _set_window_icon("Revive Launcher", icon_path))

        # собрать контейнер и экспортировать методы секций
        c = build_container(window, local_version, hud_window=hud_window)
        for name, fn in c["exposed"].items():
            window.expose(fn)

        def exit_app():
            try:
                import threading
                # Закрываем главное окно (сработают ваши обработчики closing → shutdown сервисов и HUD)
                threading.Timer(0.01, lambda: window.destroy()).start()
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        window.expose(exit_app)

        def ui_minimize():
            try:
                window.minimize()
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        window.expose(ui_minimize)

        # --- Инжект небольшой кнопки «свернуть» в правый верх ---
        def _inject_minimize_button(*_):
            try:
                js = r"""
                (function(){
                  const ID='__rv_min_btn__';
                  if (document.getElementById(ID)) return;
                  const b=document.createElement('button');
                  b.id=ID;
                  b.textContent='–';
                  b.title='Свернуть';
                  b.style.cssText='position:fixed;top:8px;right:8px;width:28px;height:28px;'
                    +'line-height:26px;text-align:center;border:none;border-radius:6px;'
                    +'background:#1f2937;color:#fff;opacity:.9;cursor:pointer;z-index:2147483647;';
                  b.onmouseenter=()=>b.style.opacity='1';
                  b.onmouseleave=()=>b.style.opacity='.9';
                  b.addEventListener('click',()=>{ try{ pywebview.api.ui_minimize(); }catch(e){} });
                  document.body.appendChild(b);
                })();
                """
                window.evaluate_js(js)
            except Exception:
                pass
        window.events.loaded += _inject_minimize_button

        # закрыть сплэш при загрузке UI
        def _close_splash(*_):
            _kill_splash(splash_proc, splash_ps1)

        window.events.loaded  += _close_splash
        window.events.shown   += _close_splash
        window.events.closing += _close_splash

        # Снять always-on-top через короткое время после показа окна
        def _drop_on_top():
            try:
                window.on_top = False
            except Exception:
                pass

        def _schedule_drop_on_top(*_):
            try:
                import threading
                threading.Timer(1.5, _drop_on_top).start()
            except Exception:
                pass
        window.events.shown += _schedule_drop_on_top

        # аккуратное завершение сервисов
        def _on_main_closing():
            # 1) не блокируем UI — завершаем сервисы в отдельном потоке
            try:
                import threading
                threading.Thread(target=c["shutdown"], daemon=True).start()
            except Exception:
                pass
            # 2) уничтожаем HUD чуть позже, вне обработчика закрытия главного окна
            try:
                if hud_window:
                    import threading as _th
                    _th.Timer(0.05, lambda: hud_window.destroy()).start()
            except Exception:
                pass

        window.events.closing += _on_main_closing

        # старт
        try:
            webview.start(debug=False, gui="edgechromium", http_server=True)
        finally:
            _kill_splash(splash_proc, splash_ps1)

    except Exception:
        _kill_splash(splash_proc, splash_ps1)
        raise
