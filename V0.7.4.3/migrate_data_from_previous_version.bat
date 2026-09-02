@echo off
title CAD Inspector V0.5 - Migrar dados anteriores
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente virtual nao encontrado.
    echo Execute primeiro install.bat.
    pause
    exit /b
)
".venv\Scripts\python.exe" "tools\migrate_legacy_db.py"
