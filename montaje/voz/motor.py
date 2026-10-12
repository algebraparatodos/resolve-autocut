# -*- coding: utf-8 -*-
"""
Encontrar (o instalar) el Python que tiene el motor de voz.

Se busca en varios sitios en vez de apuntar a uno fijo: una ruta escrita
a mano se rompe callada en la proxima mudanza de carpetas, y el programa
seguiria andando pero sin detectar voz, que es lo peor que puede pasar
aca.

Si no aparece en ningun lado, se crea uno propio dentro del programa. Son
unos 300 MB la primera vez y despues no se vuelve a tocar.
"""

import pathlib
import subprocess
import sys

from .. import consola

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent

# Lo que hace falta: faster-whisper trae el detector de voz de Silero y
# el reconocedor de habla, que son las dos cosas que se usan.
PAQUETES = ["faster-whisper"]


def _candidatos():
    """
    Donde puede estar ya instalado, del mas propio al mas prestado.

    El primero es el entorno del propio programa. Los siguientes existen
    para no duplicar 300 MB en una maquina donde ya hay un motor puesto
    por otra herramienta.
    """
    return [
        RAIZ / ".venv",
        # desde que la herramienta vive en Desarrollos\herramientas\
        RAIZ.parent.parent / "_comunes" / "transcribir" / ".venv",
        RAIZ.parent / "_comunes" / "transcribir" / ".venv",
        RAIZ.parent / "transcribir" / ".venv",
    ]


def _python_de(entorno):
    return pathlib.Path(entorno) / "Scripts" / "python.exe"


def buscar():
    """El primer Python con el motor puesto, o None."""
    for entorno in _candidatos():
        python = _python_de(entorno)
        if python.exists() and _lo_tiene(python):
            return python
    return None


def _lo_tiene(python):
    prueba = subprocess.run(
        [str(python), "-c", "import faster_whisper"],
        capture_output=True, text=True)
    return prueba.returncode == 0


def instalar():
    """
    Crea el entorno propio del programa y le mete el motor.

    Tarda un rato largo la primera vez. Se avisa antes, porque si no
    parece que el programa se colgo.
    """
    entorno = RAIZ / ".venv"
    python = _python_de(entorno)

    if not python.exists():
        consola.detalle("Creo el entorno del motor de voz (una sola vez).")
        hecho = subprocess.run([sys.executable, "-m", "venv", str(entorno)],
                               capture_output=True, text=True)
        if hecho.returncode != 0 or not python.exists():
            consola.error("no pude crear el entorno del motor de voz.")
            return None

    consola.detalle("Instalo el motor de voz. Son unos 300 MB y tarda un")
    consola.detalle("rato la primera vez; no se vuelve a hacer.")
    hecho = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet"] + PAQUETES,
        capture_output=True, text=True)

    if hecho.returncode != 0:
        consola.error("no pude instalar el motor de voz.")
        ultimo = (hecho.stderr or "").strip().splitlines()[-1:]
        if ultimo:
            consola.detalle(ultimo[0])
        return None

    consola.hecho("motor de voz instalado.")
    return python


def asegurar():
    """Devuelve el Python del motor, instalandolo si hace falta."""
    python = buscar()
    if python is not None:
        return python
    return instalar()
