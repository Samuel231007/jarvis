@echo off
chcp 65001 >nul
title JARVIS - Asistente de Samuel
echo ==============================================
echo       Iniciando JARVIS Asistente Personal
echo ==============================================
echo.

cd /d "%~dp0"

if not exist venv (
    echo [ERROR] No se encontro el entorno virtual venv.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python main.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo Ocurrio un error al ejecutar JARVIS.
    pause
)
