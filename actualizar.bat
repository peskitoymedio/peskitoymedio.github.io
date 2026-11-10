@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Actualizando Peskito y Medio desde el feed de iVoox...
echo.
python actualizar.py
echo.
pause
