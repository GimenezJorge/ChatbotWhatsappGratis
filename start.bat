@echo off

:: === 1. Cambiando al directorio del script ===
cd /d "%~dp0"

echo ===========================================
echo === INICIANDO SERVICIOS DEL PROYECTO MULTI-LENGUAJE ===
echo ===========================================

:: === 1.5 Crear y activar entorno virtual (Python) ===
if not exist venv (
    echo [Python] Creando entorno virtual...
    python -m venv venv
)
call venv\Scripts\activate

:: === 1.7 Actualizar PIP (Recomendado) ===
echo [Python] Actualizando PIP...
python -m pip install --upgrade pip

:: === 2. Instalar dependencias de Python ===
echo [Python] Instalando/Actualizando dependencias (requirements.txt)...
pip install -r requirements.txt || (
    echo.
    echo ERROR CRITICO: La instalacion de dependencias de Python falló.
    echo Por favor, revisa el mensaje de error de 'pip' arriba.
    pause
    exit /b 1
)

:: === 2,5. Instalar dependencias de Node ===
echo [Node.js] Instalando/Actualizando dependencias (package.json)...
call npm install 

:: === 3. Verificar instalacion de Uvicorn (Opcional, pero bueno para el debugging) ===
where uvicorn >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: uvicorn no está instalado. Intenta instalarlo con: pip install uvicorn
    pause
    exit /b 1
) 

:: ===========================================
:: === INICIO DE SERVICIOS ===
:: ===========================================

:: === 4. Iniciar Ollama Backend ===
echo Iniciando Ollama en segundo plano...
start "Ollama Backend" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
timeout /t 5 >nul

:: === 5. Iniciar WhatsApp (Node.js) ===
echo Iniciando servicio de WhatsApp (Puerto 3000)...
start "WhatsApp Service" cmd /k "node bot.js"
timeout /t 3 >nul

:: === 6. Iniciar aplicacion Python (FastAPI) ===
echo Iniciando FastAPI (Puerto 8000) en una ventana separada...
start "FastAPI Server" cmd /k "uvicorn app.main:app --reload --port 8000"

:: === 7. MANTENER CONSOLA ABIERTA ===
echo ===========================================
echo === TODOS LOS SERVICIOS INICIADOS. ===
echo === Presiona cualquier tecla para cerrar. ===
echo ===========================================
pause