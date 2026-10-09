# -*- coding: utf-8 -*-
"""
La puerta de entrada: se le arrastra una carpeta y hace todo lo demas.

No lleva opciones de linea de comandos a proposito, salvo la que usa
ordenes.bat para saltar el montaje. El programa existe para hacer siempre
lo mismo sin tener que acordarse de nada, y lo que se puede cambiar vive
en 'ajustes.ini'. Despues del montaje queda esperando ordenes (ver
'ordenes'), asi que la ventana no se cierra hasta que se lo piden.
"""

import datetime
import pathlib
import sys

from . import ajustes as config
from . import consola, herramientas, interprete, ordenes, pipeline

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Si se abre sin arrastrar nada, se trabaja con lo que haya aca.
CRUDOS = RAIZ / "crudos"

# El argumento con el que ordenes.bat pide saltar el montaje.
SOLO_ORDENES = "--solo-ordenes"


def informe(resultado):
    """Lo que quedo, en cuatro lineas."""
    consola.titulo("Listo")

    consola.detalle('Linea de tiempo: "{}"'.format(resultado.nombre_timeline))
    consola.detalle("{} tramos, {} de {} grabados ({:.0f}% del material)"
                    .format(resultado.tramos,
                            consola.duracion(resultado.segundos_montados),
                            consola.duracion(resultado.segundos_crudos),
                            resultado.porcentaje_conservado))

    if resultado.grupos:
        consola.detalle("{} frases dichas mas de una vez; cada grupo quedo "
                        "pintado de un color".format(resultado.grupos))

    if resultado.otra_voz:
        consola.detalle("{} clips donde se te oye: naranja, con marcador "
                        "rojo".format(resultado.otra_voz))

    if resultado.avisos:
        consola.detalle()
        consola.detalle("Lo que no salio como esperaba:")
        for aviso in resultado.avisos:
            consola.detalle("  - " + aviso)

    consola.detalle()
    consola.detalle("Los zooms, los textos y que toma se queda son tuyos.")


def hay_videos_en(carpeta):
    try:
        return bool(herramientas.videos_de(carpeta))
    except OSError:
        return False


def preguntar_la_carpeta():
    """
    Pide la ruta por teclado, para cuando se abrio el programa a secas.

    Windows pega las rutas entre comillas cuando uno arrastra una carpeta
    a una consola, y deja un espacio al final. Se limpian las dos cosas,
    porque si no la ruta no existe y el programa dice que no encuentra
    una carpeta que el usuario esta viendo en pantalla.
    """
    consola.detalle("Arrastra aca la carpeta con los videos y apreta Enter.")
    consola.detalle("(o pega la ruta; para salir, Enter a secas)")
    consola.detalle()

    try:
        escrito = input("      Carpeta: ").strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        return None

    if not escrito:
        return None

    carpeta = pathlib.Path(escrito)
    if not carpeta.exists():
        consola.error("no existe: {}".format(carpeta))
        return None
    if not hay_videos_en(carpeta):
        consola.error("no hay ningun video en: {}".format(carpeta))
        return None
    return carpeta


def elegir_carpetas(argumentos):
    """
    De donde sale el material: de lo que se arrastro, de 'crudos', o
    preguntando.

    El orden es el de menos a mas intromision. Si el usuario ya dijo que
    quiere procesar, no hay que hacerle escribir nada de nuevo.
    """
    arrastradas = [pathlib.Path(a) for a in argumentos
                   if pathlib.Path(a).exists()]
    if arrastradas:
        return arrastradas

    if hay_videos_en(CRUDOS):
        consola.detalle("Uso los videos que hay en {}".format(CRUDOS))
        return [CRUDOS]

    elegida = preguntar_la_carpeta()
    return [elegida] if elegida else []


def main(argumentos=None):
    argumentos = list(sys.argv[1:] if argumentos is None else argumentos)

    # Todo lo que sale por pantalla queda tambien en un archivo, por si la
    # ventana se cierra. Uno por dia; cada corrida se agrega abajo.
    registros = RAIZ / "registros"
    registros.mkdir(exist_ok=True)
    consola.registrar(registros / "montaje {}.txt".format(
        datetime.date.today().isoformat()))

    # Antes que nada: si este Python no puede hablar con Resolve, el
    # programa se vuelve a lanzar solo con uno que si pueda.
    interprete.asegurar_capaz(argumentos)

    # 'ordenes' (lo pasa ordenes.bat) salta el montaje y va directo a
    # las ordenes, sobre lo que este abierto en Resolve.
    solo_ordenes = SOLO_ORDENES in argumentos
    argumentos = [a for a in argumentos if a != SOLO_ORDENES]

    salio_todo = True
    if not solo_ordenes:
        try:
            salio_todo = montar(argumentos)
        except Exception as fallo:
            # Nunca se cierra a mitad: se cuenta que paso y se sigue con
            # las ordenes, que igual pueden servir sobre lo que haya.
            consola.error("el montaje se corto: {}: {}".format(
                type(fallo).__name__, fallo))
            salio_todo = False

    ordenes.atender()
    return 0 if salio_todo else 1


def montar(argumentos):
    """El montaje de siempre. True si salio todo."""
    consola.titulo("Montaje automatico")

    valores, quejas = config.cargar(RAIZ)
    for queja in quejas:
        consola.alerta(queja)

    carpetas = elegir_carpetas(argumentos)
    if not carpetas:
        return False

    salio_todo = True
    for carpeta in carpetas:
        resultado = pipeline.montar(carpeta, valores)
        if resultado is None:
            salio_todo = False
            continue
        informe(resultado)
    consola.cerrar_paso()
    return salio_todo


if __name__ == "__main__":
    sys.exit(main())
