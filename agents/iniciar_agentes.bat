@echo off
title Sistema Multi-Agente IA
echo ==========================================
echo    INICIANDO SISTEMA MULTI-AGENTE
echo ==========================================
echo.

cd /d "%~dp0"

if not exist "venv" (
    echo [1/3] Creando entorno virtual...
    python -m venv venv
)

echo [2/3] Activando entorno virtual...
call venv\Scripts\activate.bat

echo [3/3] Verificando dependencias...
pip install -r requirements_agents.txt --quiet

echo.
echo ==========================================
echo   Dashboard: http://127.0.0.1:5051
echo   Chatbot:   http://127.0.0.1:5050
echo   Ctrl+C para detener
echo ==========================================
echo.

set ANTHROPIC_API_KEY=TU_API_KEY_AQUI
python run_agents.py

pause
