# -*- coding: utf-8 -*-
"""
El media pool: meter los clips adentro y engancharles su proxy.
"""

import pathlib

from .. import consola


def _normalizar(ruta):
    """
    Una ruta comparable con otra.

    Windows no distingue mayusculas y la misma carpeta puede venir
    escrita de varias formas segun quien la haya puesto, asi que se
    resuelve y se pasa a minusculas antes de comparar.
    """
    try:
        return str(pathlib.Path(ruta).resolve()).lower()
    except OSError:
        return str(ruta).lower()


def buscar_en_el_pool(pool, ruta):
    """
    Busca un video entre los que ya estan adentro.

    Hace falta porque pedirle a Resolve que importe un archivo que ya
    tiene no da error: devuelve vacio, igual que si el archivo no
    existiera. Y ese es el caso normal, porque los clips se suelen subir
    a mano antes de empezar.

    Se recorren tambien las subcarpetas, no solo la raiz.
    """
    buscada = _normalizar(ruta)

    pendientes = [pool.GetRootFolder()]
    while pendientes:
        carpeta = pendientes.pop()
        if carpeta is None:
            continue
        for clip in (carpeta.GetClipList() or []):
            suya = clip.GetClipProperty("File Path") or ""
            if suya and _normalizar(suya) == buscada:
                return clip
        pendientes.extend(carpeta.GetSubFolderList() or [])

    return None


def importar(pool, ruta):
    """Mete el video en el media pool, o devuelve el que ya estaba."""
    clip = buscar_en_el_pool(pool, ruta)
    if clip is not None:
        return clip, False

    importados = pool.ImportMedia([str(ruta)])
    if not importados:
        return None, False
    return importados[0], True


def medidas_segun_resolve(clip):
    """
    Ritmo y cantidad de cuadros TAL COMO LOS VE RESOLVE.

    Parece un detalle y no lo es: ffmpeg lee el archivo y Resolve lo
    interpreta, y no siempre coinciden. Un .MOV de camara puede venir
    marcado como 59,94 y Resolve tratarlo como 60 exacto. Como los
    numeros de cuadro se los damos nosotros a Resolve, el ritmo que
    manda es el suyo; con el del archivo los cortes se van corriendo y al
    final de cinco minutos llegan un tercio de segundo tarde.

    De ahi el orden correcto de trabajo: los tramos se detectan en
    segundos, que es lo unico que no depende de quien lea el archivo, y
    se pasan a cuadros recien cuando Resolve ya dijo a que ritmo ve el
    clip.
    """
    try:
        ritmo = float(clip.GetClipProperty("FPS"))
        cuadros = int(clip.GetClipProperty("Frames"))
    except (TypeError, ValueError):
        return None

    if ritmo <= 0 or cuadros <= 0:
        return None
    return ritmo, cuadros


def enganchar_proxy(clip, ruta_proxy):
    """
    Le dice a Resolve que ese archivo liviano es el proxy de este clip.

    Resolve rechaza un proxy que no coincida con su original y, fiel a
    su costumbre, lo hace devolviendo False y nada mas. Se comprueba
    releyendo la propiedad, porque un False no distingue "no me gusta el
    archivo" de "ya lo tenia".
    """
    if not clip.LinkProxyMedia(str(ruta_proxy)):
        actual = clip.GetClipProperty("Proxy Media Path") or ""
        if actual and _normalizar(actual) == _normalizar(ruta_proxy):
            return True
        return False
    return True


def preparar(resolve, material):
    """
    Deja todos los clips adentro, con su proxy y su pista de audio.

    'material' es una lista de diccionarios con 'video' (el archivo
    original, que no se toca nunca), 'audio' (el .wav nivelado, que puede
    ser None) y 'proxy' (la copia liviana, que puede ser None).

    El video y el audio entran como dos clips distintos del media pool y
    se juntan recien en la linea de tiempo. Asi el material original
    queda intacto en disco y no hace falta duplicarlo para cambiarle el
    nivel.

    Hay que pararse en la pagina Media antes de importar: segun en que
    pantalla haya quedado Resolve, 'ImportMedia' devuelve un 'no' sin
    explicacion. Pasa estando en Cut.
    """
    resolve.OpenPage("media")

    proyecto = resolve.GetProjectManager().GetCurrentProject()
    if proyecto is None:
        return None

    pool = proyecto.GetMediaPool()
    preparados = []

    for pieza in material:
        ruta = pieza["video"]
        clip, era_nuevo = importar(pool, ruta)
        if clip is None:
            consola.alerta("Resolve no pudo importar {}"
                           .format(pathlib.Path(ruta).name))
            continue

        medidas = medidas_segun_resolve(clip)
        if medidas is None:
            consola.alerta("Resolve no me dice el ritmo de {}, lo salteo"
                           .format(pathlib.Path(ruta).name))
            continue

        if pieza.get("proxy") and not enganchar_proxy(clip, pieza["proxy"]):
            consola.alerta("Resolve rechazo el proxy de {}"
                           .format(pathlib.Path(ruta).name))

        pista = None
        if pieza.get("audio"):
            pista, _ = importar(pool, pieza["audio"])
            if pista is None:
                consola.alerta("Resolve no pudo importar el audio de {}"
                               .format(pathlib.Path(ruta).name))

        ritmo, cuadros = medidas
        preparados.append({"ruta": ruta, "clip": clip, "pista": pista,
                           "ritmo": ritmo, "cuadros": cuadros,
                           "importado": era_nuevo})

    return proyecto, pool, preparados
