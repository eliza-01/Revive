@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

rem === 1) Поиск Python (py -3 или python) ===
set "PYEXE="
for %%P in (py -3) do (%%P -c "import sys" >nul 2>&1 && set "PYEXE=%%P")
if not defined PYEXE for %%P in (python) do (%%P -c "import sys" >nul 2>&1 && set "PYEXE=%%P")
if not defined PYEXE (
  echo [E] Python не найден. Установи 3.11+ и перезапусти.
  pause & exit /b 1
)

rem === 2) Безопасные TEMP каталоги (на случай кириллицы в профиле) ===
set "TMPROOT=%CD%\_tmp"
if not exist "%TMPROOT%" mkdir "%TMPROOT%"
set "TEMP=%TMPROOT%"
set "TMP=%TMPROOT%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem === 3) venv: не трогаем, создаём только если его нет ===
if not exist venv (
  echo [INFO] venv не найден, создаю...
  %PYEXE% -m venv venv || (echo [E] не удалось создать venv & pause & exit /b 1)
) else (
  echo [INFO] использую существующий venv.
)
set "PY=%CD%\venv\Scripts\python.exe"

rem === 4) Готовим requirements.build.txt ===
set "REQSRC=documents\requirements.txt"
set "REQFALL=requirements.txt"
set "REQOUT=requirements.build.txt"

if exist "%REQSRC%" (
  set "REQ=%REQSRC%"
) else if exist "%REQFALL%" (
  set "REQ=%REQFALL%"
) else (
  set "REQ="
)

if defined REQ (
  powershell -NoProfile -Command ^
    "$r=Get-Content '%REQ%';" ^
    "$r=$r | Where-Object {$_ -notmatch '^\s*(win32gui|win32con|atexit)\b'};" ^
    "if(-not ($r -match '^\s*pywin32(\b|=)')){$r+='pywin32'};" ^
    "$r | Set-Content -Encoding ASCII '%REQOUT%'"
) else (
  echo pywin32>"%REQOUT%"
)

rem === 5) Установка зависимостей строго через python -m pip ===
"%PY%" -m pip install --upgrade pip || (echo [E] pip upgrade failed & pause & exit /b 1)
"%PY%" -m pip install -r "%REQOUT%" || (echo [E] deps install failed & pause & exit /b 1)
"%PY%" -m pip install pyinstaller || (echo [E] pyinstaller install failed & pause & exit /b 1)

rem === 6) Опции ресурсов ===
set "NAME=Revive"
set "ICON=assets\icon.ico"
set "ICON_OPT="
if exist "%ICON%" set "ICON_OPT=--icon %ICON%"

set "DATA_OPTS="
if exist assets               set "DATA_OPTS=%DATA_OPTS% --add-data assets;assets"
if exist core\servers         set "DATA_OPTS=%DATA_OPTS% --add-data core\servers;core\servers"
if exist app                  set "DATA_OPTS=%DATA_OPTS% --add-data app;app"
if exist tools                set "DATA_OPTS=%DATA_OPTS% --add-data tools;tools"
if exist latest_version.txt   set "DATA_OPTS=%DATA_OPTS% --add-data latest_version.txt;."

rem === 7) Сборка onefile (без UAC; добавь --uac-admin при необходимости) ===
"%PY%" -m PyInstaller --clean --onefile --uac-admin --noconsole %ICON_OPT% ^
  --name "%NAME%" %DATA_OPTS% main.py ^
  --workpath "%CD%\build" --distpath "%CD%\dist" --specpath "%CD%"
if errorlevel 1 (echo [FAIL] build failed & pause & exit /b 1)

if exist "dist\%NAME%.exe" (
  echo [OK] dist\%NAME%.exe
) else (
  echo [FAIL] exe not found
)
pause
endlocal
