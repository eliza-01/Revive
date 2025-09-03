# app/launcher/main.py
# минимум обязанностей: создать окно, собрать секции, экспортировать их методы.
from __future__ import annotations
import os, sys, json
import webview
from .wiring import build_container
import tempfile, subprocess, ctypes

_SPLASH_PS = r"""param($gif)
Add-Type -Name U32 -Namespace Win -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[Win.U32]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

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
$form.Location=New-Object System.Drawing.Point($left,$top)
$form.Size=New-Object System.Drawing.Size($w,$h)
$form.ShowInTaskbar=$true

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
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", ps1, gif_path],
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

def launch_gui(local_version: str):
    # +++ СПЛЭШ: запускаем отдельным процессом до загрузки WebView +++
    gif_path = _res_path("webui", "assets", "preloader1.gif")
    splash_proc, splash_ps1 = _spawn_splash(gif_path)

    try:
        index_path = _res_path("webui", "index.html")
        if not os.path.exists(index_path):
            raise RuntimeError(f"Не найден UI: {index_path}")

        window = webview.create_window(
            title="Revive Launcher",
            url=index_path,
            width=820,
            height=900,
            resizable=False,
        )

        # соберём зависимости/секции и отэкспортируем методы
        c = build_container(window, local_version)
        for name, fn in c["exposed"].items():
            window.expose(fn)

        # — закроем сплэш, когда окно показано/загружено
        def _close_splash(*_):
            _kill_splash(splash_proc, splash_ps1)

        window.events.loaded  += _close_splash
        window.events.shown   += _close_splash
        window.events.closing += _close_splash

        # чтобы в случае исключения сплэш не остался висеть
        try:
            webview.start(debug=False, gui="edgechromium", http_server=True)
        finally:
            _kill_splash(splash_proc, splash_ps1)

    except Exception:
        # на всякий пожарный — тоже прибьём сплэш
        _kill_splash(splash_proc, splash_ps1)
        raise