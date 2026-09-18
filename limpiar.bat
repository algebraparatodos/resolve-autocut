@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Limpiar lo que ocupa disco

rem ---------------------------------------------------------------
rem  Muestra todo lo que ocupa disco de la edicion de videos, y borra
rem  lo que se le diga.
rem
rem  COMO SE USA
rem    Doble clic: mira todas las carpetas de montaje que encuentre.
rem    Arrastrandole una carpeta de crudos: mira solo la suya.
rem
rem  QUE MIRA, que son tres sitios y dos no se ven desde ningun lado:
rem    1. Lo que genera el programa, en "<lo que sea> - montaje":
rem       los proxies, el audio nivelado y las transcripciones.
rem    2. La cache de Resolve, que son las copias optimizadas y el
rem       render cache de TODOS los proyectos, no solo del ultimo.
rem       Crece sin parar y no la vacia nadie.
rem    3. Nada mas. Los videos originales no se tocan nunca.
rem
rem  Para saber donde tiene Resolve su cache hay que preguntarselo a
rem  el, asi que conviene tenerlo abierto con un proyecto. Sin eso,
rem  igual muestra y borra lo del programa.
rem
rem  NADA se borra sin escribir "borrar" para confirmar.
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
