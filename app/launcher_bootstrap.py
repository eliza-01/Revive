# File: app/launcher_bootstrap.py
from __future__ import annotations
import os, sys, glob, time, tempfile, subprocess, threading, platform, struct
import tkinter as tk
import tkinter.ttk as ttk

# ---- импорт пакета app ----
PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJ_ROOT not in sys.path:
    sys.path.insert(0, PROJ_ROOT)

# ---- конфиг ----
BITS = 64 if struct.calcsize("P")==8 else 32
# offline-файл (если есть — используем его)
OFFLINE_INSTALLER_PATH = os.path.join(os.path.dirname(__file__), "dep", "MicrosoftEdgeWebView2RuntimeInstallerX64.exe")
# online-URL (фиксированный x64, можно переопределить переменной окружения WV2_URL)
DOWNLOAD_URL = os.getenv("WV2_URL") or \
    "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/0d95f327-a869-4d28-9746-2212baa3228f/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
FORCE_INSTALL = os.getenv("WV2_FORCE") == "1"

HTML_LAUNCH_FN = ("app.launcher_html", "launch_gui_html")  # основной UI (HTML)
TK_LAUNCH_FN   = ("app.launcher",      "launch_gui")       # запасной UI (Tk)

# ---- поиск WebView2/Edge папки ----
PF64  = r"C:\Program Files\Microsoft\EdgeWebView\Application"
PF86  = r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application"
USER  = os.path.join(os.environ.get("LOCALAPPDATA",""), "Microsoft","EdgeWebView","Application")
EC64  = r"C:\Program Files\Microsoft\EdgeCore"
EC86  = r"C:\Program Files (x86)\Microsoft\EdgeCore"
EA64  = r"C:\Program Files\Microsoft\Edge\Application"
EA86  = r"C:\Program Files (x86)\Microsoft\Edge\Application"

def _pick_webview_folder() -> str|None:
    """Возвращает папку версии с движком. Приоритет: user-runtime → system-runtime → EdgeCore/Edge."""
    def scan(base: str, exe: str) -> str|None:
        if not base or not os.path.isdir(base): return None
        vers = sorted(glob.glob(os.path.join(base, "*.*.*.*")), reverse=True)
        for d in vers:
            if os.path.isfile(os.path.join(d, exe)):
                return d
        return None
    # runtime
    for base in (USER, PF64, PF86):
        p = scan(base, "msedgewebview2.exe")
        if p: return p
    # fallback на EdgeCore/Edge той же «битности» процесса
    if BITS==64:
        for base in (EC64, EA64):
            p = scan(base, "msedge.exe")
            if p: return p
    else:
        for base in (EC86, EA86):
            p = scan(base, "msedge.exe")
            if p: return p
    return None

# ---- сеть/установка ----
def download_with_progress(url: str, dst_path: str, progress_cb):
    import requests
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        with open(dst_path, "wb") as f:
            if not total:
                progress_cb(indeterminate=True)
            for chunk in r.iter_content(65536):
                if not chunk: continue
                f.write(chunk); got += len(chunk)
                if total:
                    progress_cb(value=int(got*100/total), text=f"{got//1024} / {total//1024} КБ")

def is_signature_valid(path: str) -> bool:
    ps = ["powershell","-NoProfile","-ExecutionPolicy","Bypass",
          "(Get-AuthenticodeSignature '{}').Status".format(path.replace(\"'\",\"''\"))]
    try:
        out = subprocess.check_output(ps, stderr=subprocess.STDOUT, text=True, timeout=20)
        return "Valid" in out
    except Exception:
        return False

def run_installer(path: str, repair: bool=False) -> int:
    args = [path, "/silent"] + (["/repair"] if repair else ["/install"])
    try:
        return subprocess.run(args, check=False).returncode
    except Exception:
        return -1

# ---- запуск UI ----
def start_html_ui(local_version: str) -> None:
    folder = _pick_webview_folder()
    if folder:
        os.environ["WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"] = folder
    import webview
    mod_name, fn_name = HTML_LAUNCH_FN
    try:
        mod = __import__(mod_name, fromlist=[fn_name])
        getattr(mod, fn_name)(local_version); return
    except Exception:
        html = f"""<!doctype html><meta charset='utf-8'>
        <div style="font:14px Segoe UI,Arial;padding:24px">
          <h2 style="color:#2e7d32;margin:0 0 8px">WebView2 OK</h2>
          <p>Revive {local_version}</p>
          <p>Runtime folder: {os.environ.get('WEBVIEW2_BROWSER_EXECUTABLE_FOLDER','—')}</p>
        </div>"""
        webview.create_window("HTML UI тест", html=html, width=560, height=420, resizable=False)
        webview.start(gui="edgechromium", debug=False)

def start_tk_ui(local_version: str) -> None:
    try:
        mod_name, fn_name = TK_LAUNCH_FN
        mod = __import__(mod_name, fromlist=[fn_name])
        getattr(mod, fn_name)(local_version); return
    except Exception:
        root = tk.Tk(); root.title("Fallback UI"); root.geometry("420x180"); root.resizable(False, False)
        tk.Label(root, text=f"Revive {local_version}", font=("Segoe UI",14,"bold")).pack(pady=10)
        tk.Label(root, text="WebView2 недоступен. Открыт резервный UI.", fg="#c62828").pack()
        ttk.Button(root, text="Выход", command=root.destroy).pack(pady=20)
        root.mainloop()

# ---- окно установки/ремонта ----
class WV2BootstrapUI:
    def __init__(self, root: tk.Tk, local_version: str):
        self.root = root; self.local_version = local_version
        root.title("Инициализация компонентов UI"); root.geometry("560x380"); root.resizable(False, False)

        tk.Label(root, text=f"OS: {platform.platform()}").pack(anchor="w", padx=16, pady=(12,0))
        tk.Label(root, text=f"Python: {platform.architecture()[0]}").pack(anchor="w", padx=16)

        self.status = tk.Label(root, text="Проверка WebView2…", fg="gray"); self.status.pack(anchor="w", padx=16, pady=6)

        bar = tk.Frame(root); bar.pack(fill="x", padx=16)
        self.progress = ttk.Progressbar(bar, orient="horizontal", mode="determinate", maximum=100); self.progress.pack(fill="x")
        self.progress_label = tk.Label(root, text="", fg="gray"); self.progress_label.pack(anchor="w", padx=16, pady=(4,8))

        row = tk.Frame(root); row.pack(fill="x", padx=16, pady=8)
        self.btn_install = ttk.Button(row, text="Установить/починить WebView2", command=self.on_install_clicked); self.btn_install.pack(side="left")
        self.btn_html = ttk.Button(row, text="Запустить HTML-UI", command=self.on_run_html, state="disabled"); self.btn_html.pack(side="left", padx=8)
        ttk.Button(row, text="Открыть стандартный UI", command=self.on_run_tk).pack(side="right")

        self._set_progress(reset=True); self.refresh_state()

    def _set_progress(self, value: int|None=None, text: str|None=None, indeterminate: bool=False, reset: bool=False):
        if reset:
            self.progress.config(mode="determinate"); self.progress["value"]=0; self.progress_label.config(text=""); self.progress.stop(); return
        if indeterminate:
            self.progress.config(mode="indeterminate"); self.progress.start(12); self.progress_label.config(text=text or ""); return
        if value is not None:
            self.progress.config(mode="determinate"); self.progress["value"]=max(0,min(100,int(value)))
            if text: self.progress_label.config(text=text)
            self.progress.update_idletasks()

    def refresh_state(self):
        folder = _pick_webview_folder()
        if folder and not FORCE_INSTALL:
            self.status.config(text=f"WebView2 найден: {folder}", fg="#2e7d32")
            self.btn_install.config(state="normal")  # оставим как «починить»
            self.btn_html.config(state="normal")
        else:
            self.status.config(text="WebView2 не найден или принудительная установка.", fg="#c62828")
            self.btn_install.config(state="normal"); self.btn_html.config(state="disabled")

    def on_run_html(self):
        self.root.destroy()
        try:
            start_html_ui(self.local_version)
        except Exception as e:
            print("[html-ui] error:", e); start_tk_ui(self.local_version)

    def on_run_tk(self):
        self.root.destroy(); start_tk_ui(self.local_version)

    def on_install_clicked(self):
        self.btn_install.config(state="disabled")
        self._set_progress(indeterminate=True, text="Подготовка…"); self.status.config(text="Установка/ремонт WebView2…", fg="gray")

        def worker():
            err = None
            try:
                # источник: оффлайн или скачивание
                if os.path.isfile(OFFLINE_INSTALLER_PATH):
                    installer = OFFLINE_INSTALLER_PATH
                else:
                    tmp = tempfile.gettempdir(); dst = os.path.join(tmp, "MicrosoftEdgeWebView2RuntimeInstallerX64.exe")
                    def cb(value=None, text=None, indeterminate=False):
                        self.root.after(0, lambda: self._set_progress(value=value, text=("Загрузка: "+text if text else ""), indeterminate=indeterminate))
                    download_with_progress(DOWNLOAD_URL, dst, cb); installer = dst

                if not is_signature_valid(installer):
                    self.root.after(0, lambda: self.status.config(text="Подпись не подтверждена PowerShell. Продолжаю…", fg="orange"))

                # установка; при проблемах можно повторить с /repair
                self.root.after(0, lambda: self._set_progress(indeterminate=True, text="Установка…"))
                code = run_installer(installer, repair=False)
                if code != 0:
                    raise RuntimeError(f"Инсталлятор вернул код {code}")

                # ждём появление движка
                for _ in range(40):
                    if _pick_webview_folder():
                        break
                    time.sleep(1)
                if not _pick_webview_folder():
                    self.root.after(0, lambda: self.status.config(text="Пробую ремонт…", fg="orange"))
                    run_installer(installer, repair=True)
                    for _ in range(20):
                        if _pick_webview_folder(): break
                        time.sleep(1)
                    if not _pick_webview_folder():
                        raise RuntimeError("После установки/ремонта WebView2 не обнаружен")

            except Exception as e:
                err = str(e)

            def after():
                self._set_progress(reset=True)
                if err:
                    self.status.config(text=f"Ошибка установки: {err}", fg="#c62828"); self.btn_install.config(state="normal")
                else:
                    folder = _pick_webview_folder()
                    self.status.config(text=f"Готово. Найден: {folder}", fg="#2e7d32"); self.btn_html.config(state="normal")
            self.root.after(0, after)

        threading.Thread(target=worker, daemon=True).start()

# ---- публичная точка ----
def launch_universal(local_version: str):
    folder = _pick_webview_folder()
    if folder and not FORCE_INSTALL:
        os.environ["WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"] = folder
        try:
            start_html_ui(local_version); return
        except Exception as e:
            print("[bootstrap] HTML-UI не стартовал:", e)
    root = tk.Tk(); WV2BootstrapUI(root, local_version); root.mainloop()

if __name__ == "__main__":
    launch_universal("dev")
