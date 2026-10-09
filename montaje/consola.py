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

Ademas, todo lo que sale por pantalla se copia con la hora a un archivo
de registro (ver 'registrar'). El 02/10/2026 la ventana se cerro sola a
mitad del montaje y no quedo ni una linea de lo que habia pasado.
"""

import datetime
import sys
import time

# El archivo de registro, abierto con 'registrar' al arrancar.
_registro = None

# Cuando empezo el paso que esta corriendo, para decir cuanto tardo.
_paso_actual = None


def registrar(ruta):
    """Copia todo lo que sale por pantalla a un archivo, con la hora."""
    global _registro
    try:
        _registro = open(str(ruta), "a", encoding="utf-8")
        _registro.write("\n===== {} =====\n".format(
            datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
        _registro.flush()
    except OSError:
        _registro = None


def _escribir(texto):
    try:
        sys.stdout.write(texto + "\n")
    except UnicodeEncodeError:
        codificacion = sys.stdout.encoding or "ascii"
        sys.stdout.write(
            texto.encode(codificacion, "replace").decode(codificacion) + "\n")
    sys.stdout.flush()
    if _registro is not None:
        try:
            _registro.write("{}  {}\n".format(
                datetime.datetime.now().strftime("%H:%M:%S"), texto))
            _registro.flush()
        except OSError:
            pass


def titulo(texto):
    """Encabeza una etapa del montaje."""
    cerrar_paso()
    _escribir("")
    _escribir("=" * 63)
    _escribir("  " + texto.upper())
    _escribir("=" * 63)


def paso(numero, total, texto):
    """Anuncia uno de los pasos de la cadena, con la hora en que empieza."""
    global _paso_actual
    cerrar_paso()
    _escribir("")
    _escribir("[{}/{}] {}   ({})".format(
        numero, total, texto, datetime.datetime.now().strftime("%H:%M")))
    _paso_actual = time.time()


def paso_suelto(texto):
    """Como 'paso', para lo que no es parte de la cadena numerada."""
    global _paso_actual
    cerrar_paso()
    _escribir("")
    _escribir("[*] {}   ({})".format(
        texto, datetime.datetime.now().strftime("%H:%M")))
    _paso_actual = time.time()


def cerrar_paso():
    """Dice cuanto tardo el paso que estaba corriendo, si habia uno."""
    global _paso_actual
    if _paso_actual is not None:
        _escribir("      (tardo {})".format(
            duracion(time.time() - _paso_actual)))
        _paso_actual = None


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


def preguntar(texto):
    """
    Pide algo por teclado. Devuelve '' si no hay teclado (EOF o Ctrl+C).

    Lo que contesta el usuario tambien queda en el registro: sin eso, el
    registro de una sesion de ordenes no se entiende.
    """
    try:
        respuesta = input(texto)
    except (EOFError, KeyboardInterrupt):
        return ""
    if _registro is not None:
        try:
            _registro.write("{}  {}{}\n".format(
                datetime.datetime.now().strftime("%H:%M:%S"), texto,
                respuesta))
            _registro.flush()
        except OSError:
            pass
    return respuesta.strip()


def duracion(segundos):
    """Segundos a 'm:ss', que es como se lee una duracion de video."""
    segundos = max(0.0, float(segundos))
    minutos = int(segundos // 60)
    resto = segundos - minutos * 60
    return "{}:{:04.1f}".format(minutos, resto)
