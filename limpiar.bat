@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Limpiar para el video siguiente

rem ---------------------------------------------------------------
rem  Cuando el video ya esta terminado y exportado, deja esta carpeta
rem  vacia para empezar el siguiente.
rem
rem  COMO SE USA
rem    Doble clic. Muestra lo que va a borrar y cuanto pesa.
rem
rem  QUE BORRA, y solo dentro de esta carpeta:
rem    1. Los crudos: los videos de "crudos" y de cualquier otra
rem       carpeta que se haya montado aca. "crudos" queda vacia.
rem    2. Lo que genero el montaje: las carpetas "<lo que sea> -
rem       montaje" enteras, "musica de fondo", "textos generados" y
rem       "registros".
rem
rem  Fuera de esta carpeta no toca nada: ni lo exportado, ni la
rem  musica de Escritorio\Edicion, ni la cache de Resolve.
rem
rem  NADA se borra sin escribir "borrar" para confirmar. Si Resolve
rem  tiene abierto el proyecto, algunos archivos no se dejan borrar:
rem  cerrarlo y volver a pasar esto.
rem ---------------------------------------------------------------

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo   [ERROR] No hay Python instalado en esta computadora.
    echo.
    pause
    exit /b 1
)

python -m montaje.limpiar %*

echo.
pause
