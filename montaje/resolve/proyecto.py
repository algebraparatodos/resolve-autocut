# -*- coding: utf-8 -*-
"""
Los ajustes del proyecto: lienzo, ritmo y cache.

Dos reglas gobiernan este modulo y las dos salieron de perder tiempo:

  1. **Lo que se escribe hay que volver a leerlo.** 'SetSetting' devuelve
     True aunque no haya cambiado nada. El ritmo de la linea de tiempo,
     por ejemplo, solo se puede tocar mientras el proyecto no tenga
     ninguna linea de tiempo; en cuanto hay una, Resolve lo traba y lo
     dice contestando que si.

  2. **Los nombres de los ajustes no se dan por sabidos.** El README del
     SDK documenta cuatro y el resto hay que descubrirlos. Peor: cambian
     entre versiones ('perfProxyMediaOn' paso a ser 'perfProxyMediaMode').
     Asi que se pide la lista entera al proyecto abierto y se busca ahi,
     en vez de escribir un nombre a mano y que falle callado en otra
     version.

Y una consecuencia de orden: los ajustes se dejan como van a quedar
ANTES de generar nada. Cambiar la resolucion despues invalida los
proxies y las copias optimizadas que ya estaban hechas.
"""

from .. import consola


# Para cada cosa que queremos tocar, los nombres con los que Resolve la
# ha llamado en distintas versiones. Se usa el primero que exista.
NOMBRES = {
    "ancho": ["timelineResolutionWidth"],
    "alto": ["timelineResolutionHeight"],
    "ritmo": ["timelineFrameRate"],
    "usar_proxies": ["perfProxyMediaMode", "perfProxyMediaOn"],
    "usar_optimizadas": ["perfOptimisedMediaOn", "perfOptimizedMediaOn"],
    "cache_modo": ["perfCacheMode", "perfRenderCacheMode"],
}


def igual(uno, otro):
    """
    Si dos valores de ajuste son el mismo.

    Se compara como numero cuando los dos lo son, y no como texto, que
    es lo que parece natural viniendo de una API que devuelve cadenas.
    Resolve contesta el ritmo como "30.0" y uno se lo pide como "30":
    comparando el texto, el programa avisaba de que el ritmo no habia
    quedado bien justo cuando habia quedado perfecto.
    """
    if uno is None or otro is None:
        return uno is otro
    try:
        return abs(float(uno) - float(otro)) < 1e-6
    except (TypeError, ValueError):
        return str(uno) == str(otro)


class Ajustes(object):
    """Lee y escribe los ajustes del proyecto, comprobando cada cambio."""

    def __init__(self, proyecto):
        self.proyecto = proyecto
        self.todos = proyecto.GetSetting() or {}

    def nombre_de(self, que):
        """El nombre que tiene ese ajuste en ESTA version de Resolve."""
        for candidato in NOMBRES.get(que, []):
            if candidato in self.todos:
                return candidato
        return None

    def leer(self, que):
        nombre = self.nombre_de(que)
        return self.todos.get(nombre) if nombre else None

    def escribir(self, que, valor):
        """
        Cambia un ajuste y comprueba releyendolo.

        Devuelve (cambio, valor_que_quedo). 'cambio' es False tanto si
        Resolve lo rechazo como si ya estaba en ese valor, y por eso se
        devuelve tambien el valor: quien llama necesita distinguir "no
        hizo falta" de "no me dejo".
        """
        nombre = self.nombre_de(que)
        if nombre is None:
            return False, None

        anterior = self.todos.get(nombre)
        if igual(anterior, valor):
            return False, anterior

        self.proyecto.SetSetting(nombre, str(valor))
        self.todos = self.proyecto.GetSetting() or {}
        quedo = self.todos.get(nombre)
        return igual(quedo, valor), quedo


def hay_lineas_de_tiempo(proyecto):
    """
    Si el proyecto ya tiene alguna linea de tiempo.

    Importa porque con una sola que haya, el ritmo queda trabado para
    siempre en ese proyecto.
    """
    try:
        return int(proyecto.GetTimelineCount() or 0) > 0
    except (TypeError, ValueError):
        return False


def necesita_proyecto_nuevo(proyecto, ritmo):
    """
    Si montar aca dejaria el video reproduciendose a otra velocidad.

    Es la comprobacion mas importante de todas y hay que hacerla ANTES
    de montar nada, porque el resultado de equivocarse no es un error
    sino un montaje entero inservible.

    El ritmo de la linea de tiempo solo se puede cambiar mientras el
    proyecto no tenga ninguna. En cuanto hay una, Resolve lo traba. Si
    encima el ritmo que quedo trabado no es el del material, la linea de
    tiempo entrega cuadros a un ritmo y el reproductor los pide a otro,
    y el video se ve acelerado o arrastrado. Paso de verdad: material a
    50 en un proyecto trabado en 30.

    Como el ritmo no se puede arreglar, lo que se hace es no usar ese
    proyecto.
    """
    if not ritmo or not hay_lineas_de_tiempo(proyecto):
        return False
    ajustes = Ajustes(proyecto)
    return not igual(ajustes.leer("ritmo"), ritmo)


def configurar(proyecto, lienzo, ritmo):
    """
    Deja el proyecto listo: lienzo, ritmo y uso de proxies.

    'lienzo' es (ancho, alto) medido del material, ya girado. 'ritmo' es
    el del material, o None para no tocarlo.

    Devuelve la lista de cosas que no se pudieron cambiar, para que el
    informe las cuente. Ninguna es motivo para frenar el montaje, pero
    todas cambian el resultado y hay que decirlas.
    """
    ajustes = Ajustes(proyecto)
    trabadas = []

    ancho, alto = lienzo
    for que, valor, etiqueta in (("ancho", ancho, "ancho del lienzo"),
                                 ("alto", alto, "alto del lienzo")):
        cambio, quedo = ajustes.escribir(que, valor)
        if cambio:
            consola.hecho("{} en {}".format(etiqueta, valor))
        elif quedo is not None and not igual(quedo, valor):
            trabadas.append("{}: pedi {} y quedo en {}"
                            .format(etiqueta, valor, quedo))

    if ritmo:
        texto = "{:g}".format(round(float(ritmo), 3))
        cambio, quedo = ajustes.escribir("ritmo", texto)
        if cambio:
            consola.hecho("ritmo de la linea de tiempo en {}".format(texto))
        elif quedo is not None and not igual(quedo, texto):
            trabadas.append(
                "el ritmo quedo en {} y el material va a {}. Resolve solo "
                "deja cambiarlo mientras el proyecto no tenga ninguna linea "
                "de tiempo, asi que hace falta un proyecto nuevo"
                .format(quedo, texto))

    # 1 quiere decir "usar el proxy cuando exista". Con 2 Resolve solo lo
    # usaria si faltara el original, que no es el caso: los originales
    # estan y lo que se busca es no decodificarlos al reproducir.
    cambio, quedo = ajustes.escribir("usar_proxies", 1)
    if cambio:
        consola.hecho("Resolve va a usar los proxies cuando existan")
    elif ajustes.nombre_de("usar_proxies") is None:
        trabadas.append("esta version de Resolve no expone el modo de "
                        "proxies; hay que activarlo en Playback > Proxy "
                        "Handling")

    return trabadas


def lienzo_del_material(datos_de_cada_video):
    """
    Que tamano de lienzo pide el material.

    Se toma el del video mas grande, y se avisa si vienen mezclados: un
    vertical montado en un lienzo horizontal obliga a Resolve a rotar y
    escalar cada cuadro en tiempo real encima de decodificar, que es una
    de las cosas que hacen que la reproduccion se arrastre.
    """
    medidas = [(d["ancho"], d["alto"]) for d in datos_de_cada_video
               if d and d.get("ancho") and d.get("alto")]
    if not medidas:
        return None, []

    distintas = sorted(set(medidas))
    elegida = max(medidas, key=lambda m: m[0] * m[1])

    quejas = []
    if len(distintas) > 1:
        quejas.append(
            "el material viene en {} tamanos distintos ({}); armo el lienzo "
            "en {}x{} y el resto va a quedar escalado"
            .format(len(distintas),
                    ", ".join("{}x{}".format(a, b) for a, b in distintas),
                    elegida[0], elegida[1]))

    return elegida, quejas


def ritmo_del_material(datos_de_cada_video):
    """
    A que ritmo va el material, y si hay mas de uno.

    Mezclar ritmos no rompe nada: un tramo de un clip a 60 puesto en una
    linea a 50 conserva su duracion y su audio, Resolve descarta cuadros.
    Pero conviene saberlo y decirlo.
    """
    ritmos = [round(d["ritmo"], 3) for d in datos_de_cada_video
              if d and d.get("ritmo")]
    if not ritmos:
        return None, []

    distintos = sorted(set(ritmos))
    if len(distintos) == 1:
        return distintos[0], []

    # El mas frecuente, que es el que menos conversiones va a provocar.
    elegido = max(distintos, key=ritmos.count)
    return elegido, [
        "el material viene a {} ritmos distintos ({}); armo la linea de "
        "tiempo a {:g}".format(len(distintos),
                               ", ".join("{:g}".format(r) for r in distintos),
                               elegido)]
