# -*- coding: utf-8 -*-
"""
Armar la linea de tiempo, medirla y marcarla.

El orden de las cosas importa: primero se arma entera con todos los
tramos de todos los videos, despues se mide lo que quedo, y recien
despues se marcan las repeticiones. Marcar antes de medir es marcar
sobre suposiciones.
"""

from .. import consola


# Los colores de clip que acepta Resolve, en el orden en que se reparten
# entre los grupos de frases repetidas. Se empieza por los que mas se
# distinguen entre si de un vistazo en la linea de tiempo.
#
# Se usan colores de CLIP y no banderas, y la diferencia costo
# encontrarla: 'AddFlag' pertenece al clip de origen y no al tramo de la
# linea de tiempo. Poniendole una bandera a un tramo, aparece en todos
# los que salgan del mismo archivo, que es exactamente el caso de un
# video cortado en pedazos. Medido: se marcaron dos tramos y los cuatro
# quedaron con la bandera puesta. 'SetClipColor' si es de cada tramo, y
# ademas se ve mejor, porque pinta el clip entero.
COLORES = ["Orange", "Teal", "Violet", "Lime", "Pink", "Navy", "Brown",
           "Yellow", "Green", "Blue", "Purple", "Olive", "Tan", "Beige",
           "Chocolate", "Apricot"]


def a_cuadros(tramos, ritmo, total_cuadros):
    """
    Pasa segundos a numeros de cuadro.

    Dos trampas aca y las dos fallan calladas:

    1. El cuadro de salida que espera Resolve queda AFUERA del tramo: es
       el primero que ya no entra, no el ultimo que entra. Resolve acepta
       cualquiera de los dos sin chistar, asi que la unica forma de
       saberlo es medir la linea de tiempo despues de armarla. Pasandole
       el ultimo que entra, cada tramo pierde su cuadro final: son 16
       milesimas por corte, imperceptibles de a una, y con sesenta y
       cinco cortes el video termina un segundo mas corto de lo que dice
       la cuenta propia.

    2. Un tramo que al redondear se queda sin ningun cuadro adentro no
       se puede poner. Se descarta.
    """
    cortes = []
    for inicio, fin in tramos:
        primero = max(0, int(inicio * ritmo))
        afuera = min(int(round(fin * ritmo)), total_cuadros)
        if afuera <= primero:
            continue
        cortes.append((primero, afuera))
    return cortes


def nombre_libre(proyecto, propuesto):
    """
    Un nombre que no choque con una linea de tiempo que ya exista.

    Si ya hay una con el mismo nombre, Resolve no avisa: crea otra igual
    al lado y quedan dos indistinguibles.
    """
    existentes = set()
    for indice in range(1, (proyecto.GetTimelineCount() or 0) + 1):
        linea = proyecto.GetTimelineByIndex(indice)
        if linea is not None:
            existentes.add(linea.GetName())

    final, numero = propuesto, 2
    while final in existentes:
        final = "{} {}".format(propuesto, numero)
        numero += 1
    return final


def armar(proyecto, pool, pedido_video, pedido_audio, nombre):
    """
    Crea la linea de tiempo y le mete todos los tramos.

    El video y el audio van en dos llamadas separadas, porque salen de
    archivos distintos: la imagen del original y el sonido del .wav ya
    nivelado. Se mandan con 'mediaType' 1 y 2, y Resolve los va apilando
    cada uno en su pista en el orden en que llegan. Como los tramos son
    los mismos y en el mismo orden, quedan alineados solos, sin tener que
    calcular posiciones: comprobado midiendo, coinciden al cuadro.

    Dentro de cada llamada, los tramos se mandan todos juntos. De a uno
    tambien funciona, pero cada llamada tiene su ida y vuelta con el
    programa y en un video con cuatrocientos cortes la diferencia es de
    minutos.

    Devuelve (linea, puestos) o (None, []) si no se pudo.
    """
    final = nombre_libre(proyecto, nombre)

    linea = pool.CreateEmptyTimeline(final)
    if linea is None:
        consola.error("no pude crear la linea de tiempo.")
        return None, []
    proyecto.SetCurrentTimeline(linea)

    puestos = pool.AppendToTimeline(pedido_video) or []
    if len(puestos) != len(pedido_video):
        consola.alerta("pedi {} tramos de video y entraron {}"
                       .format(len(pedido_video), len(puestos)))

    if pedido_audio:
        del_audio = pool.AppendToTimeline(pedido_audio) or []
        if len(del_audio) != len(pedido_audio):
            consola.alerta("pedi {} tramos de audio y entraron {}"
                           .format(len(pedido_audio), len(del_audio)))

    consola.hecho('la linea de tiempo se llama "{}"'.format(final))
    return linea, puestos


def medir(linea):
    """
    Lo que quedo de verdad en la linea de tiempo.

    Se mide siempre despues de armar, porque la API acepta cosas que
    despues no hace. Y se cuentan los clips de TODAS las pistas, no solo
    de la que se estaba tocando: una operacion sobre una pista superior
    puede llevarse clips de otra y devolver True igual.
    """
    conteo = {}
    for tipo in ("video", "audio"):
        total = linea.GetTrackCount(tipo) or 0
        for indice in range(1, total + 1):
            items = linea.GetItemListInTrack(tipo, indice) or []
            conteo[(tipo, indice)] = len(items)
    return conteo


def desalineados(linea):
    """
    Cuantos tramos tienen la imagen y el sonido corridos.

    Con el video y el audio saliendo de archivos distintos, esto es lo
    que puede salir mal sin que nadie avise: si Resolve acomodara los
    clips de audio de otra forma, quedaria todo el montaje fuera de
    sincronia y se descubriria reproduciendo, no antes.

    Devuelve la cantidad de tramos donde no coinciden, y -1 si ni
    siquiera hay la misma cantidad de clips en las dos pistas.
    """
    video = linea.GetItemListInTrack("video", 1) or []
    audio = linea.GetItemListInTrack("audio", 1) or []

    if not audio:
        return 0                      # no hay pista aparte, nada que comparar
    if len(video) != len(audio):
        return -1

    return sum(1 for v, a in zip(video, audio)
               if v.GetStart() != a.GetStart() or v.GetEnd() != a.GetEnd())


def duracion_en_cuadros(linea):
    """Cuanto dura la linea de tiempo, en cuadros."""
    try:
        return int(linea.GetEndFrame()) - int(linea.GetStartFrame())
    except (TypeError, ValueError):
        return 0


def marcar_grupos(items, grupos):
    """
    Pinta del mismo color los tramos que dicen lo mismo.

    'grupos' es una lista de listas de indices dentro de 'items'. No se
    descarta ninguno: la idea es justamente que se vean todas las
    versiones de la frase y que el corte lo decida una persona, porque
    la que vale no siempre es la ultima.

    Ademas del color va un marcador que dice de que grupo es y cual de
    las tomas, para distinguirlas sin contar clips. El marcador si es de
    cada tramo, comprobado.
    """
    marcados = 0
    for numero, grupo in enumerate(grupos, start=1):
        color = COLORES[(numero - 1) % len(COLORES)]
        for cual, indice in enumerate(grupo, start=1):
            if indice >= len(items):
                continue
            item = items[indice]
            if item.SetClipColor(color):
                marcados += 1
            nota = "repetida {} - toma {} de {}".format(numero, cual,
                                                        len(grupo))
            # El color de marcador no es el mismo juego que el de clip,
            # asi que va uno fijo: lo que agrupa a la vista es el color
            # del clip, y el marcador solo tiene que ser legible.
            item.AddMarker(0, "Cyan", nota, "", 1, "")
    return marcados


def limpiar_marcas(items):
    """
    Saca los colores y marcadores que puso una corrida anterior.

    Hace falta cuando se vuelve a montar sobre la misma linea de tiempo:
    si no, quedan mezclados los grupos viejos con los nuevos y los
    colores dejan de querer decir algo.
    """
    for item in items:
        item.ClearClipColor()
        item.DeleteMarkersByColor("All")
