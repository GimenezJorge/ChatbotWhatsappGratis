@echo off
title Sistema Wall-E - Inicio

REM --- Asegurar que el script se ejecute desde su propia carpeta ---
cd /d "%~dp0"

echo ==========================================
echo         INICIANDO SISTEMA WALL-E
echo ==========================================
echo.

REM --- Activar entorno virtual ---
echo Activando entorno virtual Python...
call venv\Scripts\activate
echo Entorno virtual activado.
echo.

REM --- Iniciar Backend (FastAPI) ---
echo Iniciando backend FastAPI...
start cmd /k "uvicorn app.main:app --reload"
echo Backend iniciado.
echo.

REM --- Iniciar Bot de WhatsApp ---
echo Iniciando bot de WhatsApp...
start cmd /k "node bot.js"
echo Bot iniciado.
echo.

echo ==========================================
echo     Todo listo! El sistema esta corriendo.
echo ==========================================
echo.

pause
