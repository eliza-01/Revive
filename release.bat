@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo [>>] Активация venv...
call "venv\Scripts\activate.bat" || (
  echo [!!] Не удалось активировать venv
  exit /b 1
)

REM Убиваем старый EXE, если запущен
taskkill /f /im "ReviveLauncher.exe" >nul 2>nul

REM Очистка
rmdir /S /Q "dist" 2>nul
rmdir /S /Q "build" 2>nul
del /Q "ReviveLauncher.spec" 2>nul

REM Опционально укажем UPX, только если установлен
set "UPX_FLAG="
if exist "C:\Tools\upx" set "UPX_FLAG=--upx-dir=C:\Tools\upx"

echo [>>] Компиляция .exe...
pyinstaller ^
  --onefile ^
  --windowed ^
  --noconsole ^
  --icon="assets\icon.ico" ^
  --name="ReviveLauncher" ^
  --add-data "core\vision\templates\*.png;core\vision\templates" ^
  %UPX_FLAG% ^
  "main.py"

if not exist "dist\ReviveLauncher.exe" (
  echo [!!] Сборка не создала dist\ReviveLauncher.exe
  exit /b 1
)

echo [>>] Получение версии...
for /f "usebackq delims=" %%v in (`python "deploy\version_manager.py"`) do (
    set "VERSION=%%v"
)

if not defined VERSION (
  echo [!!] Версия не получена из deploy\version_manager.py
  exit /b 1
)

echo [>>] Версия: %VERSION%
echo %VERSION%> "latest_version.txt"

REM Переименование exe в формат с версией
set "FINAL_EXE_NAME=Revive v%VERSION%.exe"
if exist "dist\%FINAL_EXE_NAME%" del /q "dist\%FINAL_EXE_NAME%" 2>nul
ren "dist\ReviveLauncher.exe" "%FINAL_EXE_NAME%" || (
  echo [!!] Не удалось переименовать exe
  exit /b 1
)

REM Чтение FTP-данных (формат: host=..., user=..., pass=..., remote_path=/path/)
for /f "usebackq tokens=1,2 delims==" %%a in ("deploy\ftp_credentials.txt") do (
    set "%%a=%%b"
)

if not defined host  echo [!!] host не задан в deploy\ftp_credentials.txt & exit /b 1
if not defined user  echo [!!] user не задан в deploy\ftp_credentials.txt & exit /b 1
if not defined pass  echo [!!] pass не задан в deploy\ftp_credentials.txt & exit /b 1
if not defined remote_path echo [!!] remote_path не задан в deploy\ftp_credentials.txt & exit /b 1

REM Нормализуем remote_path завершая слешем
if not "%remote_path:~-1%"=="/" set "remote_path=%remote_path%/"

REM Генерация скрипта WinSCP
del "deploy\ftp_upload_script.txt" 2>nul
(
  echo option batch abort
  echo option confirm off
  echo open ftp://%user%:%pass%@%host%
  echo binary
  echo put "latest_version.txt" "%remote_path%latest_version.txt"
  echo put "dist\%FINAL_EXE_NAME%" "%remote_path%%FINAL_EXE_NAME%"
  echo exit
) > "deploy\ftp_upload_script.txt"

echo [>>] Загрузка файлов на FTP...
if not exist "C:\Program Files (x86)\WinSCP\WinSCP.com" (
  echo [!!] WinSCP.com не найден по пути "C:\Program Files (x86)\WinSCP\WinSCP.com"
  exit /b 1
)

"C:\Program Files (x86)\WinSCP\WinSCP.com" /script="deploy\ftp_upload_script.txt"
set "ERR=%ERRORLEVEL%"

if not "%ERR%"=="0" (
  echo [!!] Ошибка при загрузке! Код: %ERR%
  exit /b %ERR%
) else (
  echo [✓] Загрузка завершена успешно!
)

echo.
pause
exit /b 0