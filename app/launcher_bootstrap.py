# app/launcher_bootstrap.py
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
OFFLINE_INSTALLER_PATH = os.path.join(os.path.dirname(__file__), "dep", "MicrosoftEdgeWebView2RuntimeInstallerX64.exe")
DOWNLOAD_URL = os.getenv("WV2_URL") or \
    "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/0d95f327-a869-4d28-9746-2212baa3228f/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
FORCE_INSTALL = os.getenv("WV2_FORCE") == "1"

# ВАЖНО: точка входа HTML-лаунчера называется launch_gui
HTML_LAUNCH_FN = ("app.launcher_html", "launch_gui")
TK_LAUNCH_FN   = ("app.launcher",      "launch_gui")

# ---- поиск WebView2/Edge папки ----
PF64  = r"C:\Program Files\Microsoft\EdgeWebView\Application"
PF86  = r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application"
USER  = os.path.join(os.environ.get("LOCALAPPDATA",""), "Microsoft","EdgeWebView","Application")
EC64  = r"C:\Program Files\Microsoft\EdgeCore"
EC86  = r"C:\Program Files (x86)\Microsoft\EdgeCore"
EA64  = r"C:\Program Files\Microsoft\Edge\Application"
EA86  = r"C:\Program Files (x86)\Microsoft\Edge\Application"

def _pick_webview_folder() -> str|None:
    def scan(base: str, exe: str) -> str|None:
        if not base or not os.path.isdir(base): return None
        vers = sorted(glob.glob(os.path.join(base, "*.*.*.*")), reverse=True)
        for d in vers:
            if os.path.isfile(os.path.join(d, exe)):
                return d
        return None
    for base in (USER, PF64, PF86):
        p = scan(base, "msedgewebview2.exe")
        if p: return p
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
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        with open(dst_path, "wb") as f:
            if not total:
                progress_cb(indeterminate=True, text="Загрузка…")
            for chunk in r.iter_content(65536):
                if not chunk: continue
                f.write(chunk); got += len(chunk)
                if total:
                    mb_got = got / (1024*1024)
                    mb_tot = total / (1024*1024)
                    progress_cb(value=int(got*100/total), text=f"{mb_got:.1f} / {mb_tot:.1f} МБ")

def is_signature_valid(path: str) -> bool:
    cmd = "(Get-AuthenticodeSignature '{}').Status".format(path.replace("'", "''"))
    ps = ["powershell","-NoProfile","-ExecutionPolicy","Bypass", cmd]
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
    try:
        import webview  # noqa
    except Exception as e:
        raise RuntimeError(f"Не найден модуль 'webview': {e}")
    mod_name, fn_name = HTML_LAUNCH_FN
    mod = __import__(mod_name, fromlist=[fn_name])
    getattr(mod, fn_name)(local_version)

def start_tk_ui(local_version: str) -> None:
    try:
        mod_name, fn_name = TK_LAUNCH_FN
        mod = __import__(mod_name, fromlist=[fn_name])
        getattr(mod, fn_name)(local_version); return
    except Exception:
        root = tk.Tk(); root.title("Revive — упрощённый режим"); root.geometry("440x190"); root.resizable(False, False)
        tk.Label(root, text=f"Revive {local_version}", font=("Segoe UI",14,"bold")).pack(pady=10)
        tk.Label(root, text="Современный интерфейс недоступен. Открыт упрощённый UI.", fg="#c62828").pack()
        ttk.Button(root, text="Закрыть", command=root.destroy).pack(pady=20)
        root.mainloop()

# ---- окно установки/ремонта ----
class WV2BootstrapUI:
    def __init__(self, root: tk.Tk, local_version: str):
        self.root = root; self.local_version = local_version
        root.title("Подготовка Revive"); root.geometry("620x420"); root.resizable(False, False)

        # Шапка
        tk.Label(root, text=f"Revive {local_version}", font=("Segoe UI",16,"bold")).pack(anchor="w", padx=16, pady=(12,4))
        tk.Label(root, text=f"Windows: {platform.platform()}", fg="#6b6f78").pack(anchor="w", padx=16)
        tk.Label(root, text=f"Python: {platform.architecture()[0]}", fg="#6b6f78").pack(anchor="w", padx=16, pady=(0,6))

        # Пояснение
        expl = ("Для запуска современного интерфейса нужен компонент Microsoft WebView2.\n"
                "Если компонент уже установлен — сразу запускайте Revive.")
        tk.Label(root, text=expl, justify="left").pack(anchor="w", padx=16, pady=(0,8))

        # Статус
        self.status = tk.Label(root, text="Проверка WebView2…", fg="gray"); self.status.pack(anchor="w", padx=16, pady=6)

        # Прогресс
        bar = tk.Frame(root); bar.pack(fill="x", padx=16)
        self.progress = ttk.Progressbar(bar, orient="horizontal", mode="determinate", maximum=100); self.progress.pack(fill="x")
        self.progress_label = tk.Label(root, text="", fg="gray"); self.progress_label.pack(anchor="w", padx=16, pady=(4,8))

        # Кнопки
        row1 = tk.Frame(root); row1.pack(fill="x", padx=16, pady=(6,2))
        self.btn_html = ttk.Button(row1, text="Запустить Revive (современный интерфейс)", command=self.on_run_html, state="disabled"); self.btn_html.pack(side="left")
        ttk.Button(row1, text="Запустить Revive (упрощённый интерфейс)", command=self.on_run_tk).pack(side="right")

        row2 = tk.Frame(root); row2.pack(fill="x", padx=16, pady=(8,2))
        self.btn_install = ttk.Button(row2, text="Установить / починить компонент WebView2", command=self.on_install_clicked)
        self.btn_install.pack(side="left")

        # Подсказка
        hint = ("Подсказка: установка занимает 1–2 минуты. Требуется интернет или офлайн-установщик в app/dep.")
        tk.Label(root, text=hint, fg="#6b6f78").pack(anchor="w", padx=16, pady=(6,0))

        self._set_progress(reset=True)
        self.refresh_state()

    def _set_progress(self, value: int|None=None, text: str|None=None, indeterminate: bool=False, reset: bool=False):
        if reset:
            self.progress.config(mode="determinate"); self.progress["value"]=0; self.progress_label.config(text=""); self.progress.stop(); return
        if indeterminate:
            self.progress.config(mode="indeterminate"); self.progress.start(12); self.progress_label.config(text=text or ""); return
        if value is not None:
            self.progress.config(mode="determinate"); self.progress["value"]=max(0,min(100,int(value)))
            if text is not None: self.progress_label.config(text=text)
            self.progress.update_idletasks()

    def refresh_state(self):
        folder = _pick_webview_folder()
        if folder and not FORCE_INSTALL:
            self.status.config(text=f"Компонент WebView2 установлен: {folder}", fg="#2e7d32")
            self.btn_html.config(state="normal")
            self.btn_install.config(text="Переустановить / починить WebView2")
        else:
            self.status.config(text="Компонент WebView2 не найден. Требуется установка.", fg="#c62828")
            self.btn_html.config(state="disabled")
            self.btn_install.config(text="Установить компонент WebView2")

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
        self._set_progress(indeterminate=True, text="Подготовка…"); self.status.config(text="Выполняется установка/ремонт WebView2…", fg="gray")

        def worker():
            err = None
            try:
                if os.path.isfile(OFFLINE_INSTALLER_PATH):
                    installer = OFFLINE_INSTALLER_PATH
                else:
                    tmp = tempfile.gettempdir(); dst = os.path.join(tmp, "MicrosoftEdgeWebView2RuntimeInstallerX64.exe")
                    def cb(value=None, text=None, indeterminate=False):
                        self.root.after(0, lambda: self._set_progress(value=value, text=(text or ""), indeterminate=indeterminate))
                    download_with_progress(DOWNLOAD_URL, dst, cb); installer = dst

                if not is_signature_valid(installer):
                    self.root.after(0, lambda: self.status.config(text="Предупреждение: подпись не подтверждена PowerShell. Продолжаем установку.", fg="orange"))

                self.root.after(0, lambda: self._set_progress(indeterminate=True, text="Установка…"))
                code = run_installer(installer, repair=False)
                if code != 0:
                    raise RuntimeError(f"Инсталлятор вернул код {code}")

                # Ожидание появления компонента
                for _ in range(40):
                    if _pick_webview_folder(): break
                    time.sleep(1)
                if not _pick_webview_folder():
                    self.root.after(0, lambda: self.status.config(text="Пробую ремонт…", fg="orange"))
                    run_installer(installer, repair=True)
                    for _ in range(20):
                        if _pick_webview_folder(): break
                        time.sleep(1)
                    if not _pick_webview_folder():
                        raise RuntimeError("После установки/ремонта компонент не обнаружен")
            except Exception as e:
                err = str(e)

            def after():
                self._set_progress(reset=True)
                if err:
                    self.status.config(text=f"Ошибка: {err}", fg="#c62828"); self.btn_install.config(state="normal")
                else:
                    folder = _pick_webview_folder()
                    self.status.config(text=f"Готово. Компонент установлен: {folder}", fg="#2e7d32")
                    self.btn_html.config(state="normal"); self.btn_install.config(state="normal", text="Переустановить / починить WebView2")
            self.root.after(0, after)

        threading.Thread(target=worker, daemon=True).start()

# ---- публичная точка ----
def start_html_or_bootstrap(local_version: str):
    folder = _pick_webview_folder()
    if folder and not FORCE_INSTALL:
        os.environ["WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"] = folder
        try:
            start_html_ui(local_version); return
        except Exception as e:
            print("[bootstrap] HTML-UI не стартовал:", e)
    root = tk.Tk(); WV2BootstrapUI(root, local_version); root.mainloop()

def launch_universal(local_version: str):
    # совместимость со старым именем
    start_html_or_bootstrap(local_version)

if __name__ == "__main__":
    # поддержка: python -m app.launcher_bootstrap 1.0.0
    ver = None
    if len(sys.argv) > 1:
        ver = sys.argv[1]
    else:
        try:
            with open(os.path.join(PROJ_ROOT, "documents", "latest_version.txt"), "r", encoding="utf-8") as f:
                ver = (f.read() or "").strip() or "dev"
        except Exception:
            ver = "dev"
    launch_universal(ver)
