@echo off
title Instalador del sistema Wall-E

echo ==========================================
echo        INSTALADOR DEL SISTEMA WALL-E
echo ==========================================
echo.

REM ==========================================
REM  Verificar Python
REM ==========================================
echo Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado.
    echo Instale Python 3.10+ y vuelva a ejecutar este archivo.
    pause
    exit /b
)
echo OK: Python detectado.
echo.


REM ==========================================
REM  Crear entorno virtual
REM ==========================================
if exist venv (
    echo Entorno virtual 'venv' ya existe. Saltando creacion.
) else (
    echo Creando entorno virtual...
    python -m venv venv
)
echo.


REM ==========================================
REM  Activar entorno virtual
REM ==========================================
echo Activando entorno virtual...
call venv\Scripts\activate
echo.


REM ==========================================
REM  Instalar dependencias de Python
REM ==========================================
if exist requirements.txt (
    echo Instalando dependencias de Python...
    pip install --upgrade pip
    pip install -r requirements.txt
) else (
    echo ADVERTENCIA: No se encontro requirements.txt en la raiz del proyecto.
)
echo.


REM ==========================================
REM  Verificar Git
REM ==========================================
echo Verificando Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git no esta instalado.
    echo Instale Git desde https://git-scm.com/ y vuelva a ejecutar.
    pause
    exit /b
)
echo OK: Git detectado.
echo.


REM ==========================================
REM  Verificar Node.js instalado
REM ==========================================
echo Verificando Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js no esta instalado.
    echo Instale Node.js 20.19.5 LTS desde nodejs.org y vuelva a ejecutar.
    pause
    exit /b
)
echo OK: Node detectado.
echo.


REM ==========================================
REM  Verificar version exacta de Node.js (20.19.5 LTS)
REM ==========================================
for /f "tokens=1 delims=v" %%a in ('node -v') do set NODE_VER=%%a

echo Version de Node detectada: %NODE_VER%

if NOT "%NODE_VER%"=="20.19.5" (
    echo ERROR: Esta aplicacion requiere Node.js 20.19.5 (LTS).
    echo Version instalada: %NODE_VER%
    echo Descargue la version correcta desde:
    echo https://nodejs.org/dist/v20.19.5/
    pause
    exit /b
)

echo OK: Version de Node.js correcta.
echo.


REM ==========================================
REM  Instalar dependencias de Node.js
REM ==========================================
if exist package.json (
    echo Instalando dependencias de Node.js...
    npm install
) else (
    echo ADVERTENCIA: No se encontro package.json en la raiz del proyecto.
)
echo.


echo ==========================================
echo     INSTALACION COMPLETA CON EXITO
echo ==========================================
echo.

pause
