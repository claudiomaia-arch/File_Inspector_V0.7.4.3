@echo off
title File Inspector V0.7.4.3
cd /d "%~dp0"

if exist "config.local.bat" call "config.local.bat"

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente virtual nao encontrado.
    echo Execute primeiro install.bat.
    pause
    exit /b
)

echo ============================================
echo  FILE INSPECTOR V0.7.4.3
echo ============================================
echo Dados persistentes:
echo %USERPROFILE%\CAD_Usinagem_Inspector_DATA
echo.
echo Servidor: http://127.0.0.1:8010
echo.

start "" http://127.0.0.1:8010
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8010
pause
