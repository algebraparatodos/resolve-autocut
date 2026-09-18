# -*- coding: utf-8 -*-
"""
Lo que se le dice al usuario por pantalla.

Vive aparte porque el resto del programa no deberia saber si hay una
consola, un archivo de registro o nada. Cada paso cuenta lo que hace
llamando a estas funciones, y aca se decide como se ve.

La consola de Windows no siempre habla UTF-8, asi que todo lo que sale
pasa por un filtro que reemplaza lo que no se puede escribir en vez de
tirar el programa abajo. Un acento mal puesto es molesto; un
UnicodeEncodeError a mitad del montaje es perder el trabajo.
"""

import sys


def _escribir(texto):
    try:
        sys.stdout.write(texto + "\n")
    except UnicodeEncodeError:
        codificacion = sys.stdout.encoding or "ascii"
        sys.stdout.write(
            texto.encode(codificacion, "replace").decode(codificacion) + "\n")
    sys.stdout.flush()


def titulo(texto):
    """Encabeza una etapa del montaje."""
    _escribir("")
    _escribir("=" * 63)
    _escribir("  " + texto.upper())
    _escribir("=" * 63)


def paso(numero, total, texto):
    """Anuncia uno de los pasos de la cadena."""
    _escribir("")
    _escribir("[{}/{}] {}".format(numero, total, texto))


def detalle(texto=""):
    """Una linea de detalle, sangrada debajo del paso."""
    _escribir("      " + texto if texto else "")


def hecho(texto):
    _escribir("      OK  " + texto)


def alerta(texto):
    """Algo que no impide seguir pero que hay que saber."""
    _escribir("      !   " + texto)


def error(texto):
    _escribir("      ERROR  " + texto)


def duracion(segundos):
    """Segundos a 'm:ss', que es como se lee una duracion de video."""
    segundos = max(0.0, float(segundos))
    minutos = int(segundos // 60)
    resto = segundos - minutos * 60
    return "{}:{:04.1f}".format(minutos, resto)
