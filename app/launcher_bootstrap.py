# app/launcher_bootstrap.py
from __future__ import annotations
import os, sys, glob, tempfile, subprocess, struct
import importlib

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

# Основная точка входа нового HTML-лаунчера
# (оставляем кортеж для обратной совместимости, но дальше используем расширенный список кандидатов)
HTML_LAUNCH_FN = ("app.launcher.main", "launch_gui")

# ---- поиск WebView2 / Edge ----
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
    # Prefer runtime
    for base in (USER, PF64, PF86):
        p = scan(base, "msedgewebview2.exe")
        if p: return p
    # Fallback to full Edge if runtime absent
    if BITS==64:
        for base in (EC64, EA64):
            p = scan(base, "msedge.exe")
            if p: return p
    else:
        for base in (EC86, EA86):
            p = scan(base, "msedge.exe")
            if p: return p
    return None

# ---- сеть/установка (без GUI) ----
def _download(url: str, dst_path: str):
    import requests
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dst_path, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)

def _is_signature_valid(path: str) -> bool:
    # PowerShell-проверка подписи (не критично — используется как best-effort)
    cmd = "(Get-AuthenticodeSignature '{}').Status".format(path.replace("'", "''"))
    ps = ["powershell","-NoProfile","-ExecutionPolicy","Bypass", cmd]
    try:
        out = subprocess.check_output(ps, stderr=subprocess.STDOUT, text=True, timeout=20)  # <-- фикс опечатки
        return "Valid" in out
    except Exception:
        return False

def _run_installer(path: str, repair: bool=False) -> int:
    args = [path, "/silent"] + (["/repair"] if repair else ["/install"])
    try:
        return subprocess.run(args, check=False).returncode
    except Exception:
        return -1

def _ensure_webview2_installed() -> None:
    """Пробует найти WebView2; при отсутствии — выполнить тихую установку.
       Если установка не удалась — бросает RuntimeError."""
    if not FORCE_INSTALL:
        folder = _pick_webview_folder()
        if folder:
            os.environ["WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"] = folder
            return

    # Нужна установка / ремонт
    if os.path.isfile(OFFLINE_INSTALLER_PATH):
        installer = OFFLINE_INSTALLER_PATH
    else:
        tmp = tempfile.gettempdir()
        installer = os.path.join(tmp, "MicrosoftEdgeWebView2RuntimeInstallerX64.exe")
        _download(DOWNLOAD_URL, installer)

    # Подпись (best-effort)
    _is_signature_valid(installer)  # результат не критичен

    code = _run_installer(installer, repair=False)
    if code != 0:
        # попробуем ремонт/повтор
        _run_installer(installer, repair=True)

    # финальная проверка
    folder = _pick_webview_folder()
    if not folder:
        raise RuntimeError("Компонент WebView2 не обнаружен после установки/ремонта.")
    os.environ["WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"] = folder

# ---- запуск HTML UI ----
def start_html_ui(local_version: str) -> None:
    _ensure_webview2_installed()

    try:
        import webview  # noqa: F401
    except Exception as e:
        raise RuntimeError(f"Модуль 'webview' недоступен: {e}")

    # Сценарии импорта: поддерживаем разные названия модулей/функций.
    candidates: list[tuple[str, str]] = [
        (HTML_LAUNCH_FN[0], HTML_LAUNCH_FN[1]),     # ("app.launcher.main","launch_gui") — исторический
        ("app.launcher.main", "start"),             # возможная новая сигнатура
        ("app.launcher_html", "start"),             # старый HTML-лаунчер
        ("app.launcher", "start"),                  # пакет с функцией start
    ]

    mod = None
    fn = None
    last_err: Exception | None = None

    for mod_name, fn_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, fn_name, None)
            if callable(fn):
                break
            last_err = RuntimeError(f"Module '{mod_name}' has no callable '{fn_name}'")
            mod = None
            fn = None
        except Exception as e:
            last_err = e
            mod = None
            fn = None

    if not (mod and callable(fn)):
        tried = ", ".join(f"{m}.{f}" for m, f in candidates)
        raise ModuleNotFoundError(f"UI launcher module not found; tried: {tried}. Last error: {last_err}")

    # Запуск
    fn(local_version)

# ---- публичная точка ----
def launch_universal(local_version: str):
    # единственный сценарий — HTML UI через новый ланчер
    start_html_ui(local_version)

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
