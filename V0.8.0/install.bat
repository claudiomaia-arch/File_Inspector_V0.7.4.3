@echo off
title Instalacao - File Inspector V0.7.4.3
cd /d "%~dp0"
echo ============================================
echo  FILE INSPECTOR - INSTALACAO
echo ============================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo Python nao foi encontrado no PATH.
    echo Instale o Python e marque "Add Python to PATH".
    pause
    exit /b
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo.
echo Instalando/atualizando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERRO: alguma dependencia nao foi instalada.
    pause
    exit /b
)

echo.
echo Testando dependencias principais...
python -c "import fastapi, uvicorn, jinja2, multipart, itsdangerous, pypdf; print('Dependencias OK')"

if errorlevel 1 (
    echo.
    echo ERRO: o teste de dependencias falhou.
    pause
    exit /b
)

echo.
echo Instalacao concluida com sucesso.
echo Execute run.bat para iniciar o sistema.
pause
