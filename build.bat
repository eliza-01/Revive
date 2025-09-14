@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

rem === 1) Python ===
set "PYEXE="
py -3 -c "import sys" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE python -c "import sys" >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
  echo [E] Python не найден. Установи 3.11+ и добавь в PATH.
  pause & exit /b 1
)

rem === 2) TEMP/UTF-8 ===
set "TMPROOT=%CD%\_tmp"
if not exist "%TMPROOT%" mkdir "%TMPROOT%"
set "TEMP=%TMPROOT%"
set "TMP=%TMPROOT%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem === 3) venv ===
if not exist venv (
  echo [INFO] Создаю venv...
  %PYEXE% -m venv venv || (echo [E] venv failed & pause & exit /b 1)
) else (
  echo [INFO] Использую существующий venv.
)
set "PY=%CD%\venv\Scripts\python.exe"

rem === 4) deps ===
set "REQOUT=requirements.build.txt"
> "%REQOUT%" echo pywin32
>>"%REQOUT%" echo requests
>>"%REQOUT%" echo comtypes
>>"%REQOUT%" echo pywebview>=4.4
"%PY%" -m pip install --upgrade pip || (echo [E] pip upgrade failed & pause & exit /b 1)
"%PY%" -m pip install -r "%REQOUT%" || (echo [E] deps install failed & pause & exit /b 1)
"%PY%" -m pip install pyinstaller || (echo [E] pyinstaller install failed & pause & exit /b 1)

rem === 5) ресурсы ===
set "NAME=Revive"
set "ICON=assets\icon.ico"
set "ICON_OPT="
if exist "%ICON%" set "ICON_OPT=--icon %ICON%"

set "DATA_OPTS="
if exist assets                        set "DATA_OPTS=%DATA_OPTS% --add-data assets;assets"
if exist core\servers                  set "DATA_OPTS=%DATA_OPTS% --add-data core\servers;core\servers"
if exist app\webui                     set "DATA_OPTS=%DATA_OPTS% --add-data app\webui;app\webui"
if exist app\dep                       set "DATA_OPTS=%DATA_OPTS% --add-data app\dep;app\dep"
if exist documents                     set "DATA_OPTS=%DATA_OPTS% --add-data documents;documents"

rem === 6) очистка ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
for %%F in (*.spec) do del "%%F" >nul 2>&1

rem === 7) сборка (включаем HTML-лаунчер и Tk-фолбэк) ===
"%PY%" -m PyInstaller --clean --onefile --uac-admin --noconsole %ICON_OPT% ^
  --name "%NAME%" %DATA_OPTS% main.py ^
  --hidden-import app.launcher_html ^
  --hidden-import app.launcher ^
  --hidden-import webview.platforms.edgechromium ^
  --collect-submodules webview ^
  --collect-data webview ^
  --workpath "%CD%\build" --disteleportath "%CD%\dist" --specpath "%CD%"
if errorlevel 1 (echo [FAIL] build failed & pause & exit /b 1)

rem === 8) результат ===
if exist "dist\%NAME%.exe" (
  echo [OK] dist\%NAME%.exe
) else (
  echo [FAIL] exe not found
)
pause
endlocal
