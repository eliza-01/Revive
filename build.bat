@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo [>>] Активация среды venv...
call "venv\Scripts\activate.bat" || (
echo [!!] Не удалось активировать venv
exit /b 1
)

echo [>>] Компиляция ReviveLauncher (с правами администратора)...

rmdir /S /Q "dist" 2>nul
rmdir /S /Q "build" 2>nul
del /Q "ReviveLauncher.spec" 2>nul
del /Q "ReviveLauncher.exe" 2>nul

pyinstaller ^
--onefile ^
--windowed ^
--uac-admin ^
--icon="assets\icon.ico" ^
--name="ReviveLauncher" ^
--add-data "core\vision\templates\l2mad;core\vision\templates\l2mad" ^
"main.py"

if exist "dist\ReviveLauncher.exe" (
echo [✓] Готово. Exe находится в dist
) else (
echo [!!] Сборка не создала dist\ReviveLauncher.exe
)

pause
exit /b 0