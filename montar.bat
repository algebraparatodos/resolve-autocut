@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
title Montaje automatico

rem ---------------------------------------------------------------
rem  Deja en DaVinci Resolve una linea de tiempo lista para editar,
rem  a partir de una carpeta de grabaciones crudas.
rem
rem  COMO SE USA
rem    Se arrastra la carpeta con los videos encima de este archivo.
rem    Sin arrastrar nada, procesa lo que haya en la carpeta "crudos".
rem
rem    No hace falta abrir Resolve: si no esta corriendo lo abre el
rem    programa, y si no hay ningun proyecto lo crea. Si ya tenias uno
rem    abierto, trabaja ahi.
rem
rem  QUE HACE, SIEMPRE LO MISMO Y EN ESTE ORDEN
rem    1. Configura el proyecto: lienzo, ritmo y uso de proxies.
rem    2. Nivela el audio a -14 LUFS, sin recodificar el video.
rem    3. Genera copias livianas y se las engancha a Resolve.
rem    4. Corta todo lo que no sea alguien hablando, y corta aparte
rem       donde se oye a Juani detras de Natalia.
rem    5. Pinta del mismo color las frases repetidas, y en naranja los
rem       clips con la voz de Juani.
rem
rem  DESPUES NO SE CIERRA: queda esperando ordenes en palabras, como
rem  "pone de fondo las de Velee", "proponeme titulos" o "exporta". Las
rem  entiende con OpenAI (la clave de J-DEV). Enter vacio para salir.
rem  Para dar ordenes sin volver a montar: ordenes.bat.
rem
rem  Todo lo que muestra queda tambien en registros\montaje AAAA-MM-DD.txt
rem
rem  QUE NO HACE
rem    No descarta tomas ni pone zooms. Eso es trabajo de quien edita.
rem
rem  ANTES DE LA PRIMERA VEZ, en Resolve:
rem     Preferences > System > General
rem     External scripting using: Local
rem  Es una casilla y se hace una sola vez en la computadora. Es lo
rem  unico que queda a mano: mientras este apagada, la API de Resolve
rem  no responde, asi que no se puede encender desde la API.
rem
rem  Lo que se puede cambiar esta en ajustes.ini, al lado de este
rem  archivo. No hace falta tocarlo para usarlo.
rem ---------------------------------------------------------------

rem Arrastrando una carpeta encima, Windows no garantiza desde donde se
rem abre esto, y "python -m montaje" necesita estar parado en la carpeta
rem del programa. Las rutas que llegan son absolutas, asi que moverse
rem aca no rompe nada.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo   [ERROR] No hay Python instalado en esta computadora.
    echo           Instalarlo desde https://www.python.org/downloads/
    echo           y volver a abrir este archivo.
    echo.
    pause
    exit /b 1
)

python -m montaje %*

echo.
pause
