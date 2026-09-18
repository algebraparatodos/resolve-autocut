# -*- coding: utf-8 -*-
"""
Engancharse con DaVinci Resolve, abriendolo si hace falta.

Conviene entender por que Resolve tiene que estar corriendo, porque
define lo que se puede automatizar y lo que no. La libreria de Blackmagic
no lee ni escribe archivos de proyecto: es un control remoto. Se conecta
por comunicacion entre procesos al Resolve que esta abierto y le da
ordenes, igual que si alguien hiciera clic. Sin proceso al que hablarle,
'scriptapp' devuelve None y no hay nada que hacer, porque tampoco hay un
formato de proyecto documentado que se pueda escribir desde afuera.

Lo que si se puede es abrirlo. Asi que en vez de devolverle al usuario
el paso de arrancar Resolve y crear un proyecto, el programa hace las
dos cosas y espera.

Lo unico que queda a mano, una sola vez por computadora, es la casilla
'External scripting using: Local' de las preferencias, y es por un
problema de huevo y gallina: mientras este apagada la API no responde,
asi que no hay forma de encenderla desde la API.
"""

import os
import pathlib
import subprocess
import time

from .. import consola, interprete

# Cuanto se espera a que Resolve arranque y conteste. Un arranque en
# frio con proyectos grandes se toma su tiempo, y cortar antes deja al
# usuario con Resolve abriendose y un programa que ya dijo que fallo.
ESPERA_MAXIMA = 180
ENTRE_INTENTOS = 2


class NoHayResolve(Exception):
    """Resolve no esta, no responde, o no deja trabajar todavia."""


def _ejecutable():
    """Donde esta instalado Resolve, o None."""
    for base in (r"C:\Program Files\Blackmagic Design\DaVinci Resolve",
                 r"C:\Program Files\Blackmagic Design\DaVinci Resolve Studio"):
        ruta = pathlib.Path(base) / "Resolve.exe"
        if ruta.exists():
            return ruta
    return None


def _enganchar():
    """
    Un intento de conexion. Devuelve el objeto Resolve o None.

    No distingue entre "no esta instalado" y "no esta abierto": eso lo
    decide quien llama, que es el que sabe si ya lo intento abrir.
    """
    if interprete.preparar_entorno() is None:
        return None
    try:
        import DaVinciResolveScript as motor
    except Exception:
        return None
    return motor.scriptapp("Resolve")


def esta_corriendo():
    return _enganchar() is not None


def abrir():
    """
    Lanza Resolve y espera a que conteste.

    Se lanza y se suelta: Resolve tarda en levantar y no tiene sentido
    bloquear el proceso esperandolo. Lo que se espera es a que la API
    responda, que es lo unico que importa aca.
    """
    ruta = _ejecutable()
    if ruta is None:
        raise NoHayResolve(
            "No encuentro DaVinci Resolve instalado en esta computadora.")

    consola.detalle("Resolve no esta abierto: lo abro yo. Tarda un rato.")
    try:
        subprocess.Popen([str(ruta)], cwd=str(ruta.parent),
                         close_fds=True)
    except OSError as fallo:
        raise NoHayResolve("No pude abrir Resolve: {}".format(fallo))

    esperado = 0
    while esperado < ESPERA_MAXIMA:
        time.sleep(ENTRE_INTENTOS)
        esperado += ENTRE_INTENTOS
        resolve = _enganchar()
        if resolve is not None:
            consola.hecho("Resolve respondio a los {} segundos"
                          .format(esperado))
            return resolve

    raise NoHayResolve(
        "Abri Resolve pero no contesto en {} segundos. Puede ser que el "
        "scripting este apagado: Preferences > System > General > "
        "External scripting using: Local.".format(ESPERA_MAXIMA))


def conectar(abrirlo_si_hace_falta=True):
    """
    Devuelve el objeto Resolve, o levanta NoHayResolve explicando que
    pasa en castellano.

    Ojo con el orden de las comprobaciones: la de la pagina actual NO va
    aca. Recien abierto, Resolve muestra la ventana de proyectos, que
    cuenta como ventana encima y deja la pagina en vacio; pero desde ahi
    si se puede crear o cargar un proyecto, que es justo lo que la cierra.
    Comprobar la pagina antes de eso frenaria el programa en el unico
    momento en que el estado es normal y esperado.
    """
    if interprete.preparar_entorno() is None:
        raise NoHayResolve(
            "No encuentro DaVinci Resolve instalado en esta computadora.")

    resolve = _enganchar()
    if resolve is None and abrirlo_si_hace_falta:
        resolve = abrir()

    if resolve is None:
        raise NoHayResolve(
            "Resolve no responde. Una sola vez por computadora hay que "
            "activar en Resolve:\n"
            "        Preferences > System > General\n"
            "        External scripting using: Local")

    return resolve


def comprobar_que_deja_trabajar(resolve):
    """
    Que no haya ninguna ventana abierta encima.

    Con Preferences, Project Settings o cualquier cartel en pantalla,
    Resolve contesta, pero importar un clip o crear una linea de tiempo
    devuelve un 'no' pelado. Se nota porque se queda sin pagina actual.
    Frenar aca ahorra media hora de buscar el problema en el codigo
    propio.
    """
    if resolve.GetCurrentPage() is None:
        raise NoHayResolve(
            "Resolve tiene una ventana abierta encima (Preferences, "
            "Project Settings o algun cartel). Mientras este ahi no me "
            "deja trabajar: cerrarla y volver a pasar la carpeta.")


def _esta_en_blanco(proyecto):
    """
    Si lo que figura como abierto no es trabajo de nadie.

    Son los proyectos que Resolve fabrica solo: se llaman 'Untitled
    Project', a veces con la fecha pegada atras, y no tienen ninguna
    linea de tiempo. Pisarlos no le quita nada a nadie, y montar ahi
    dejaria el trabajo en un proyecto con un nombre que no dice nada y
    que despues cuesta encontrar.

    Esto aparece en dos momentos distintos que conviene no confundir:

    * **Al arrancar Resolve**, donde ademas 'GetCurrentPage()' devuelve
      vacio porque el gestor de proyectos esta delante. Visto desde la
      API, ese vacio es indistinguible de tener Preferences abierto, y
      por eso hace falta mirar tambien el proyecto: del gestor se sale
      por script, de Preferences no.
    * **Con Resolve ya abierto**, despues de cerrar un proyecto, donde la
      pagina contesta normalmente.
    """
    if proyecto is None:
        return True
    try:
        sin_nada = int(proyecto.GetTimelineCount() or 0) == 0
    except (TypeError, ValueError):
        sin_nada = False
    return sin_nada and (proyecto.GetName() or "").startswith("Untitled Project")


def asegurar_proyecto(resolve, nombre):
    """
    Deja un proyecto abierto y a Resolve en condiciones de trabajar.

    Se respeta el proyecto que ya este abierto aunque se llame de otra
    forma: quien tiene Resolve en pantalla con lo suyo espera que el
    montaje caiga ahi, no en otro que aparecio de la nada.

    La excepcion son los 'Untitled Project' vacios que Resolve fabrica
    solo, que no son trabajo de nadie. Ahi se crea o se carga uno con el
    nombre de la carpeta, que ademas es como se lo va a buscar despues.

    Ojo con una cosa que cuesta descubrir: cuando ese Untitled viene del
    arranque, el gestor de proyectos sigue delante y Resolve no deja
    hacer nada, y **no sirve recargar ese mismo proyecto**. Probado:
    tanto 'OpenPage' como 'LoadProject' del que ya estaba devuelven que
    si y dejan el gestor donde estaba. Lo unico que lo cierra es entrar a
    un proyecto DISTINTO, sea cargando uno que exista o creando uno.
    """
    gestor = resolve.GetProjectManager()
    if gestor is None:
        raise NoHayResolve("Resolve no me da el gestor de proyectos.")

    abierto = gestor.GetCurrentProject()

    if not _esta_en_blanco(abierto) and resolve.GetCurrentPage() is not None:
        return abierto, False

    existentes = gestor.GetProjectListInCurrentFolder() or []
    if nombre in existentes:
        proyecto = gestor.LoadProject(nombre)
        if proyecto is not None:
            consola.hecho('abri el proyecto "{}", que ya existia'
                          .format(nombre))
            return proyecto, False

    proyecto = gestor.CreateProject(nombre)
    if proyecto is None:
        raise NoHayResolve(
            'No pude crear el proyecto "{}" en Resolve. Puede que ya '
            'exista uno con ese nombre en otra carpeta del gestor.'
            .format(nombre))

    consola.hecho('cree el proyecto "{}"'.format(nombre))
    return proyecto, True


def crear_aparte(resolve, base):
    """
    Un proyecto nuevo con nombre libre, partiendo de uno propuesto.

    Se usa cuando el proyecto donde se iba a montar no sirve, tipicamente
    porque tiene el ritmo trabado en otro que el del material. Se numera
    en vez de pisar, porque lo que hay en el otro proyecto puede ser
    trabajo de alguien.
    """
    gestor = resolve.GetProjectManager()
    existentes = set(gestor.GetProjectListInCurrentFolder() or [])

    nombre, numero = base, 2
    while nombre in existentes:
        nombre = "{} {}".format(base, numero)
        numero += 1

    proyecto = gestor.CreateProject(nombre)
    if proyecto is None:
        raise NoHayResolve(
            'No pude crear el proyecto "{}" en Resolve.'.format(nombre))
    return proyecto


def en_pagina(resolve, pagina):
    """
    Lleva Resolve a una pagina concreta.

    No es cosmetico: 'ImportMedia' devuelve None si Resolve quedo parado
    en la pagina Cut, aunque no haya ninguna ventana encima.
    """
    actual = resolve.GetCurrentPage()
    if actual != pagina:
        resolve.OpenPage(pagina)
    return actual


def soltar(resolve):
    """
    Deja Resolve donde el usuario va a seguir trabajando.

    Se termina siempre en la pagina de edicion, que es donde sigue el
    trabajo a mano, y se dice con todas las letras que el programa ya no
    esta tocando nada. Quien mira la pantalla no tiene otra forma de
    saber si lo que ve es el resultado o un paso intermedio.
    """
    try:
        resolve.OpenPage("edit")
    except Exception:
        pass
    consola.detalle()
    consola.detalle("Solte Resolve: ya no estoy tocando nada. "
                    "Lo que ves en pantalla es el resultado.")
