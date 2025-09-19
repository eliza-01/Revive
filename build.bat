@echo off
setlocal EnableExtensions EnableDelayedExpansion
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
"%PY%" -m pip install -r "%REQOUT%"   || (echo [E] deps install failed & pause & exit /b 1)
"%PY%" -m pip install pyinstaller      || (echo [E] pyinstaller install failed & pause & exit /b 1)

rem === 5) ресурсы ===
set "NAME=Revive"
set "ICON=assets\icon.ico"
set "ICON_OPT="
if exist "%ICON%" set "ICON_OPT=--icon %ICON%"

set "DATA_OPTS="

rem Базовые ассеты/UI/документы
if exist assets                        set "DATA_OPTS=!DATA_OPTS! --add-data assets;assets"
if exist core\servers                  set "DATA_OPTS=!DATA_OPTS! --add-data core\servers;core\servers"
if exist app\webui                     set "DATA_OPTS=!DATA_OPTS! --add-data app\webui;app\webui"
if exist app\dep                       set "DATA_OPTS=!DATA_OPTS! --add-data app\dep;app\dep"
if exist documents                     set "DATA_OPTS=!DATA_OPTS! --add-data documents;documents"
rem ВАЖНО: включаем core\config целиком (servers.manifest.json и т.п.)
if exist core\config                   set "DATA_OPTS=!DATA_OPTS! --add-data core\config;core\config"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.autofarm.server"
rem --- AutoFarm: включаем КАЖДЫЙ сервер целиком (без хардкода) ---
for /d %%S in (core\engines\autofarm\server\*) do (
  set "ABS=%%~fS"
  set "REL=!ABS:%CD%\=!"
  set "DATA_OPTS=!DATA_OPTS! --add-data "!ABS!";"!REL!""
)

rem dashboard templates целиком (кнопки, вкладки и т.д.)
for /d %%S in (core\engines\dashboard\server\*) do (
  if exist "%%S\templates" set "DATA_OPTS=!DATA_OPTS! --add-data %%S\templates;%%S\templates"
)

rem stabilize-данные (anchors.json и templates) для всех серверов
for /d %%S in (core\engines\dashboard\server\*) do (
  if exist "%%S\teleport\stabilize" (
    set "DATA_OPTS=!DATA_OPTS! --add-data %%S\teleport\stabilize;%%S\teleport\stabilize"
  )
)


REM === HIDDEN-IMPORT для всех серверов macros (rules, engine) ===
set "HIDS_MACROS="
for /d %%S in (core\engines\macros\server\*) do (
  set "SRV=%%~nS"
  set "HIDS_MACROS=!HIDS_MACROS! --hidden-import core.engines.macros.server.!SRV!.rules"
  set "HIDS_MACROS=!HIDS_MACROS! --hidden-import core.engines.macros.server.!SRV!.engine"
)

rem === 6) очистка ===
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
for %%F in (*.spec) do del "%%F" >nul 2>&1

rem === 7) сборка
rem Критично: собрать динамически импортируемые движки/резолверы
set "COLLECTS="
set "COLLECTS=!COLLECTS! --collect-submodules app.launcher"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.respawn"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.respawn.server"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.dashboard"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.dashboard.server"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.autofarm"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.autofarm.server"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.player_state"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.ui_guard"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.window_focus"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.macros"
set "COLLECTS=!COLLECTS! --collect-submodules core.engines.macros.server"
set "COLLECTS=!COLLECTS! --collect-submodules core.vision"
set "COLLECTS=!COLLECTS! --collect-submodules core.os.win"


"%PY%" -m PyInstaller --clean --onefile --uac-admin --noconsole %ICON_OPT% ^
  --name "%NAME%" !DATA_OPTS! main.py ^
  --hidden-import app.launcher_html ^
  --hidden-import app.launcher ^
  --hidden-import app.launcher.main ^
  --hidden-import webview.platforms.edgechromium ^
  !COLLECTS! ^
  !HIDS_MACROS! ^
  --collect-submodules webview ^
  --collect-data webview ^
  --workpath "%CD%\build" --distpath "%CD%\dist" --specpath "%CD%"
if errorlevel 1 (echo [FAIL] build failed & pause & exit /b 1)

rem === 8) результат ===
if exist "dist\%NAME%.exe" (
  echo [OK] dist\%NAME%.exe
) else (
  echo [FAIL] exe not found
)
pause
endlocal
