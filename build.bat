@echo off
setlocal
cd /d "%~dp0"

rem 0) Очистка прошлых сборок
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
for %%F in (*.spec) do del "%%F" >nul 2>&1

rem 1) Python + venv
where py >nul 2>&1 && set PY=py -3 || set PY=python
if not exist venv (%PY% -m venv venv) || (echo venv OK)
call "venv\Scripts\activate"

rem 2) Зависимости
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

rem 3) Опции сборки
set NAME=Revive
set ICON=assets\icon.ico
set UPXDIR=
if exist "assets\upx\upx.exe" set UPXDIR=--upx-dir "assets\upx"

set DATA_OPTS=^
 --add-data "assets;assets" ^
 --add-data "core\servers;core\servers" ^
 --add-data "app;app" ^
 --add-data "tools;tools" ^
 --add-data "latest_version.txt;."

rem 4) Сборка onefile
if exist "%ICON%" (set ICON_OPT=--icon "%ICON%") else (set ICON_OPT=)
pyinstaller --onefile --noconsole %ICON_OPT% %UPXDIR% ^
 --name "%NAME%" %DATA_OPTS% main.py

rem 5) Результат
if exist "dist\%NAME%.exe" (
  echo Done: dist\%NAME%.exe
) else (
  echo ERROR: exe not produced. Check PyInstaller log above.
  exit /b 1
)
endlocal
