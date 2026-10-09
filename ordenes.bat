@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Ordenes de edicion

rem ---------------------------------------------------------------
rem  Ordenes en palabras sobre lo que este abierto en Resolve, sin
rem  volver a montar. Por ejemplo:
rem     pone de fondo las de Velee
rem     volve a armar la musica       (despues de hacer cortes)
rem     proponeme titulos
rem     pone 'Molde de sello' en 2:30
rem     exporta
rem  Enter sin escribir nada para salir.
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

python -m montaje --solo-ordenes

echo.
pause
