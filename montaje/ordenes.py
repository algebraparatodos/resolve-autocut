# -*- coding: utf-8 -*-
"""
Ordenes en palabras de Juani, despues del montaje.

Pedido del 02/10/2026: que montar.bat no se cierre al terminar y quede
esperando ordenes especiales, como poner la musica, exportar o poner
textos. Lo que escribe se lo pasa a OpenAI (ver 'ia'), que lo traduce a
una lista de ACCIONES de las que este programa sabe hacer. La IA no
ejecuta nada: devuelve que accion y con que datos, y el programa la hace
con sus comprobaciones de siempre, contando cada paso en pantalla.

Si la orden no se entiende, la IA no adivina: contesta con una pregunta
y no se hace nada.
"""

from . import consola, ia, musica

SISTEMA = (
    "Sos el asistente de un programa que edita videos en DaVinci Resolve. "
    "El usuario escribe una orden en castellano y vos la traducis a una "
    "lista de acciones del programa, en el orden en que hay que hacerlas. "
    "Acciones posibles:\n"
    "- musica: pone musica de fondo en toda la linea de tiempo, debajo de "
    "la voz. 'canciones' son los nombres EXACTOS de la lista de canciones "
    "disponibles, en el orden pedido. Si pide un artista o un estilo, "
    "elegi de la lista las que correspondan. Si no dice cuales, usa las "
    "mismas de la ultima vez si te las doy; si no, pregunta.\n"
    "- rearmar_musica: vuelve a armar la musica con las mismas canciones "
    "de la ultima vez, por ejemplo despues de hacer cortes.\n"
    "- exportar: exporta el video entero a MP4.\n"
    "- titulos: propone titulos de seccion leyendo lo que se dice, para "
    "que el usuario elija cuales poner.\n"
    "- texto: pone un texto concreto en pantalla. 'texto' es lo que dice, "
    "'segundo' donde empieza en la linea de tiempo (convertir '2:30' a "
    "150) y 'duracion' cuantos segundos dura (4 si no lo dice).\n"
    "- nada: cuando la orden no es ninguna de estas o falta un dato. En "
    "'respuesta' explica en una frase que no se puede o pregunta lo que "
    "falta.\n"
    "En 'respuesta' pone siempre una frase corta en castellano "
    "rioplatense diciendo lo que vas a hacer. Los campos que no usa una "
    "accion van en null.")

ESQUEMA = {
    "type": "object",
    "properties": {
        "acciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "accion": {"type": "string",
                               "enum": ["musica", "rearmar_musica",
                                        "exportar", "titulos", "texto",
                                        "nada"]},
                    "canciones": {"type": ["array", "null"],
                                  "items": {"type": "string"}},
                    "texto": {"type": ["string", "null"]},
                    "segundo": {"type": ["number", "null"]},
                    "duracion": {"type": ["number", "null"]},
                },
                "required": ["accion", "canciones", "texto", "segundo",
                             "duracion"],
                "additionalProperties": False,
            },
        },
        "respuesta": {"type": "string"},
    },
    "required": ["acciones", "respuesta"],
    "additionalProperties": False,
}

EJEMPLOS = [
    "pone de fondo las de Velee",
    "volve a armar la musica",
    "proponeme titulos",
    "pone 'Molde de sello' en 2:30",
    "exporta",
]


class Sesion(object):
    """Lo que se recuerda entre una orden y la siguiente."""

    def __init__(self):
        self.canciones = []          # rutas de la ultima musica puesta


def _conectar():
    """El proyecto abierto en Resolve, o None diciendo por que."""
    from .resolve import conexion
    try:
        resolve = conexion.conectar(abrirlo_si_hace_falta=False)
        conexion.comprobar_que_deja_trabajar(resolve)
    except conexion.NoHayResolve as fallo:
        consola.error(str(fallo))
        return None, None
    proyecto = resolve.GetProjectManager().GetCurrentProject()
    if proyecto is None or proyecto.GetCurrentTimeline() is None:
        consola.error("no hay ningun proyecto con una linea de tiempo "
                      "abierta en Resolve.")
        return None, None
    return resolve, proyecto


def _soltar(resolve):
    from .resolve import conexion
    conexion.soltar(resolve)


def _buscar_canciones(nombres):
    """De los nombres que eligio la IA a rutas, sin inventar ninguna."""
    todas = musica.disponibles()
    rutas, faltan = [], []
    for nombre in nombres or []:
        exacta = [r for r in todas
                  if musica.nombre_corto(r).lower() == nombre.lower()]
        parecida = [r for r in todas
                    if nombre.lower() in musica.nombre_corto(r).lower()]
        elegida = (exacta or parecida or [None])[0]
        if elegida is None:
            faltan.append(nombre)
        elif elegida not in rutas:
            rutas.append(elegida)
    return rutas, faltan


def _hacer(accion, sesion):
    """Ejecuta una accion. Devuelve False si hay que cortar la lista."""
    tipo = accion["accion"]

    if tipo == "nada":
        return False

    if tipo in ("musica", "rearmar_musica"):
        if tipo == "musica":
            rutas, faltan = _buscar_canciones(accion["canciones"])
            if faltan:
                consola.alerta("no encuentro: " + ", ".join(faltan))
        else:
            rutas = sesion.canciones
        if not rutas:
            consola.error("no se que canciones poner. Decime cuales.")
            return False
        consola.paso_suelto("Musica de fondo: " + ", ".join(
            musica.nombre_corto(r) for r in rutas))
        resolve, proyecto = _conectar()
        if proyecto is None:
            return False
        try:
            if musica.poner(proyecto, rutas):
                sesion.canciones = rutas
                return True
            return False
        finally:
            _soltar(resolve)

    if tipo == "exportar":
        from . import exportar
        resolve, proyecto = _conectar()
        if proyecto is None:
            return False
        try:
            return exportar.exportar(proyecto)
        finally:
            _soltar(resolve)

    if tipo == "titulos":
        from . import textos, titulos
        resolve, proyecto = _conectar()
        if proyecto is None:
            return False
        try:
            consola.paso_suelto("Titulos de seccion")
            propuestos = titulos.proponer(proyecto.GetCurrentTimeline())
            elegidos = titulos.elegir(propuestos)
            if not elegidos:
                consola.detalle("No pongo ninguno.")
                return True
            puestos = 0
            for s in elegidos:
                if textos.poner(proyecto, s["titulo"], s["segundo"]):
                    puestos += 1
            consola.hecho("{} de {} titulos puestos".format(
                puestos, len(elegidos)))
            return puestos == len(elegidos)
        finally:
            _soltar(resolve)

    if tipo == "texto":
        from . import textos
        if not accion["texto"] or accion["segundo"] is None:
            consola.error("me falta el texto o el momento.")
            return False
        resolve, proyecto = _conectar()
        if proyecto is None:
            return False
        try:
            consola.paso_suelto('Texto "{}" en {}'.format(
                accion["texto"], consola.duracion(accion["segundo"])))
            return textos.poner(proyecto, accion["texto"], accion["segundo"],
                                accion["duracion"] or textos.DURACION)
        finally:
            _soltar(resolve)

    consola.alerta("no se hacer '{}'".format(tipo))
    return False


def _contexto(sesion):
    """Lo que la IA necesita saber para elegir: canciones y la ultima."""
    lineas = ["Canciones disponibles:"]
    lineas += ["- " + musica.nombre_corto(r) for r in musica.disponibles()]
    if sesion.canciones:
        lineas.append("Ultima musica puesta: " + ", ".join(
            musica.nombre_corto(r) for r in sesion.canciones))
    return "\n".join(lineas)


def atender():
    """
    Pide ordenes hasta que el usuario aprieta Enter sin escribir nada.

    Nunca se cae por una orden: cualquier error se cuenta y se vuelve a
    pedir. Es lo que hace que la ventana quede abierta y util.
    """
    sesion = Sesion()
    consola.titulo("Ordenes")
    consola.detalle("Escribi lo que quieras que haga, por ejemplo:")
    for ejemplo in EJEMPLOS:
        consola.detalle("   " + ejemplo)
    consola.detalle("Enter sin escribir nada para terminar.")

    while True:
        consola.detalle()
        orden = consola.preguntar("  Orden: ")
        if not orden:
            consola.detalle("Listo, termino.")
            return
        try:
            plan = ia.preguntar(SISTEMA, _contexto(sesion) + "\n\nOrden: "
                                + orden, ESQUEMA, "acciones")
        except ia.SinIA as fallo:
            consola.error("no pude entender la orden: {}".format(fallo))
            continue
        consola.detalle("-> " + plan.get("respuesta", ""))
        for accion in plan.get("acciones") or []:
            try:
                if not _hacer(accion, sesion):
                    break
            except ia.SinIA as fallo:
                consola.error(str(fallo))
                break
            except Exception as fallo:          # que no se cierre nunca
                consola.error("fallo haciendo '{}': {}: {}".format(
                    accion["accion"], type(fallo).__name__, fallo))
                break
        consola.cerrar_paso()
