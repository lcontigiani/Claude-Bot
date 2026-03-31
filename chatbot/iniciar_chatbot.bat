@echo off
title Chatbot - Servidor
echo ==========================================
echo    INICIANDO SERVIDOR DEL CHATBOT
echo ==========================================
echo.

cd /d "%~dp0"

:: Verificar si existe el entorno virtual
if not exist "venv" (
    echo [1/3] Creando entorno virtual...
    python -m venv venv
    echo.
)

:: Activar entorno virtual
echo [2/3] Activando entorno virtual...
call venv\Scripts\activate.bat

:: Instalar dependencias
echo [3/3] Verificando dependencias...
pip install -r requirements.txt --quiet

echo.
echo ==========================================
echo    Servidor listo en http://127.0.0.1:5050
echo    Presiona Ctrl+C para detener
echo ==========================================
echo.

python server.py

pause
