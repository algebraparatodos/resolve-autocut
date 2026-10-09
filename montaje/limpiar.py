# -*- coding: utf-8 -*-
"""
Dejar la carpeta del programa vacia para empezar el video siguiente.

Se usa cuando el video ya esta terminado y exportado. Borra, y solo
dentro de la carpeta del programa:

  1. **Los crudos**: los videos de "crudos" y de cualquier otra carpeta
     que se haya montado aca (la que tiene al lado su "<nombre> -
     montaje"). La carpeta "crudos" queda, vacia, para los siguientes.
  2. **Todo lo que genero el montaje**: las carpetas "<nombre> - montaje"
     enteras (proxies, audio nivelado, transcripciones, musica), la
     "musica de fondo", los "textos generados" y los "registros".

Fuera de la carpeta del programa no se toca nada: ni lo exportado, ni la
biblioteca de musica, ni la cache de Resolve.

Nada se borra sin escribir "borrar" para confirmar.
"""

import os
import pathlib
import shutil
import stat
import sys

from . import consola, herramientas

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Donde se dejan los videos para montar. Se vacia pero no se borra.
CRUDOS = RAIZ / "crudos"

# Lo que va generando el programa fuera de las carpetas de montaje.
GENERADAS = ("musica de fondo", "textos generados", "registros")

SUFIJO = " - montaje"


def _pesa(sitio):
    """Cuanto ocupa un archivo o una carpeta entera, en bytes."""
    sitio = pathlib.Path(sitio)
    if sitio.is_file():
        return sitio.stat().st_size
    total = 0
    for hijo in sitio.rglob("*"):
        try:
            if hijo.is_file():
                total += hijo.stat().st_size
        except OSError:
            continue
    return total


def en_gb(bytes_):
    return bytes_ / (1024.0 ** 3)


def carpetas_de_crudos():
    """
    'crudos' y toda carpeta del programa que se haya montado: la que
    tiene al lado su '<nombre> - montaje'.
    """
    carpetas = {CRUDOS} if CRUDOS.is_dir() else set()
    for montaje in RAIZ.glob("*" + SUFIJO):
        origen = RAIZ / montaje.name[:-len(SUFIJO)]
        if origen.is_dir():
            carpetas.add(origen)
    return sorted(carpetas)


def inventario():
    """Que se va a borrar, con lo que pesa: (sitio, que es, bytes)."""
    filas = []
    for carpeta in carpetas_de_crudos():
        for video in herramientas.videos_de(carpeta):
            filas.append((video, "crudo", _pesa(video)))

    for montaje in sorted(RAIZ.glob("*" + SUFIJO)):
        if montaje.is_dir():
            filas.append((montaje, "lo que genero el montaje", _pesa(montaje)))

    for nombre in GENERADAS:
        carpeta = RAIZ / nombre
        if carpeta.is_dir():
            for hijo in sorted(carpeta.iterdir()):
                filas.append((hijo, nombre, _pesa(hijo)))
    return filas


def _preguntar(texto):
    try:
        return input(texto).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return ""


def _quitar_solo_lectura(funcion, ruta, _):
    """Windows no deja borrar un archivo de solo lectura: se le quita."""
    os.chmod(ruta, stat.S_IWRITE)
    funcion(ruta)


def _borrar(sitio):
    try:
        if sitio.is_dir():
            shutil.rmtree(sitio, onerror=_quitar_solo_lectura)
        else:
            sitio.unlink()
        return True
    except OSError as fallo:
        consola.error("no pude borrar {} ({})".format(
            sitio.relative_to(RAIZ), fallo.strerror or fallo))
        return False


def _quitar_vacias():
    """Las carpetas de crudos que quedaron vacias, salvo 'crudos'."""
    for carpeta in carpetas_de_crudos():
        if carpeta != CRUDOS and not any(carpeta.iterdir()):
            carpeta.rmdir()


def main(argumentos=None):
    consola.titulo("Limpiar para el video siguiente")
    consola.detalle("Solo dentro de " + str(RAIZ))
    consola.detalle()

    filas = inventario()
    if not filas:
        consola.detalle("No hay nada que borrar, esta todo limpio.")
        return 0

    for que in ("crudo", "lo que genero el montaje") + GENERADAS:
        de_esto = [(s, p) for s, q, p in filas if q == que]
        if not de_esto:
            continue
        consola.detalle("{} ({:.2f} GB):".format(
            "Crudos" if que == "crudo" else que.capitalize(),
            en_gb(sum(p for _, p in de_esto))))
        for sitio, peso in de_esto:
            consola.detalle("   {:>8.2f} GB  {}".format(
                en_gb(peso), sitio.relative_to(RAIZ)))
        consola.detalle()

    total = sum(p for _, _, p in filas)
    consola.detalle("En total se liberan {:.1f} GB.".format(en_gb(total)))
    consola.detalle()
    consola.alerta("Los crudos se borran de verdad, no van a la papelera.")
    consola.alerta("Antes, asegurate de haber exportado el video.")

    if _preguntar('      Escribi "borrar" para confirmar: ') != "borrar":
        consola.detalle("No toco nada.")
        return 0

    consola.detalle()
    liberado = 0
    fallidos = 0
    for sitio, _, peso in filas:
        if _borrar(sitio):
            liberado += peso
        else:
            fallidos += 1
    _quitar_vacias()
    CRUDOS.mkdir(exist_ok=True)

    consola.detalle()
    consola.hecho("Liberados {:.1f} GB.".format(en_gb(liberado)))
    if fallidos:
        consola.detalle()
        consola.alerta("{} no se pudieron borrar porque los esta usando otro"
                       .format(fallidos))
        consola.alerta("programa, casi seguro Resolve. Cerra el proyecto en")
        consola.alerta("Resolve y volve a pasar limpiar.bat.")
    else:
        consola.detalle('La carpeta "crudos" quedo vacia para el siguiente.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
