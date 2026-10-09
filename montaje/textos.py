# -*- coding: utf-8 -*-
"""
Poner un texto en pantalla, con el criterio de Juani.

El criterio (02/10/2026): Recoleta Alt, letra blanca, borde negro y un
poco de sombra. Va arriba y centrado, como el resto de los textos de sus
videos, y entra y sale con un fundido corto, porque acompana una
explicacion (los ganchos de arranque van en seco, pero esos no los pone
este programa).

**Por que el texto es un video y no un Text+ de Resolve.** Se probo y no
se puede: 'InsertFusionTitleIntoTimeline' mete el titulo SIEMPRE en la
pista de video 1, en el cursor, como una edicion de insercion: parte el
clip de abajo y empuja todo lo que viene despues, descuadrando la imagen
del sonido. Con la pista 1 bloqueada no inserta en ninguna otra, y la API
no deja elegir la pista. Asi que el texto se dibuja con ffmpeg en un .mov
con fondo transparente (ProRes 4444) y se coloca en una pista propia,
"Textos", encima de todo. Es como ya se hacian las formulas de los videos
de matematica. La contra: para cambiar una palabra no se edita en
Resolve, se le vuelve a pedir el texto al programa.
"""

import datetime
import os
import pathlib
import re
import shutil
import tempfile

from . import consola, herramientas

DURACION = 4.0                 # segundos, si no se pide otra cosa
FUNDIDO = 0.3
NOMBRE_PISTA = "Textos"
SALIDA = pathlib.Path(__file__).resolve().parent.parent / "textos generados"

# Proporciones medidas sobre 1080 de alto: letra de 96, borde de 6,
# sombra corrida 5. Asi en un video vertical o en 4K queda igual.
LETRA, BORDE, SOMBRA, ARRIBA = 96 / 1080.0, 6 / 1080.0, 5 / 1080.0, 0.08

FUENTES = ["Recoleta Alt Bold", "RecoletaAlt-Bold", "Recoleta Alt Medium",
           "RecoletaAlt-Medium", "Recoleta Alt Regular", "Recoleta"]


def buscar_fuente():
    """El archivo de Recoleta Alt instalado, la Bold primero, o None."""
    carpetas = [pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
                pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft"
                / "Windows" / "Fonts"]
    archivos = [r for c in carpetas if c.exists() for r in c.iterdir()
                if r.suffix.lower() in (".otf", ".ttf")]
    for nombre in FUENTES:
        for archivo in archivos:
            if archivo.stem.lower() == nombre.lower():
                return archivo
    return None


def _tamano_de_letra(texto, ancho, alto):
    """
    La letra, achicada si el texto no entra en el 90 % del ancho.

    ffmpeg no ajusta solo. Se estima con lo que mide de ancho cada letra
    de Recoleta en promedio (0,55 del tamano), que da de sobra.
    """
    letra = alto * LETRA
    estimado = len(texto) * letra * 0.55
    if estimado > ancho * 0.9:
        letra *= ancho * 0.9 / estimado
    return int(letra)


def dibujar(texto, ancho, alto, ritmo, segundos, destino):
    """Escribe el .mov transparente con el texto. True si salio."""
    fuente = buscar_fuente()
    if fuente is None:
        consola.error("no encuentro la fuente Recoleta Alt instalada.")
        return False
    letra = _tamano_de_letra(texto, ancho, alto)
    filtro = (
        "drawtext=fontfile=fuente{ext}:textfile=texto.txt:fontcolor=white:"
        "fontsize={letra}:borderw={borde}:bordercolor=black:"
        "shadowx={sombra}:shadowy={sombra}:shadowcolor=black@0.45:"
        "x=(w-text_w)/2:y=h*{arriba},"
        "fade=t=in:st=0:d={f}:alpha=1,"
        "fade=t=out:st={salida:.3f}:d={f}:alpha=1").format(
            ext=fuente.suffix, letra=letra,
            borde=max(1, int(alto * BORDE)), sombra=max(1, int(alto * SOMBRA)),
            arriba=ARRIBA, f=FUNDIDO, salida=max(0.0, segundos - FUNDIDO))

    # Se trabaja en una carpeta aparte con la fuente y el texto copiados
    # alli: asi ni la ruta de la fuente (con espacios) ni el texto (con
    # comillas o dos puntos) pasan por el escapado de ffmpeg, que es
    # donde estas cosas se rompen.
    with tempfile.TemporaryDirectory() as carpeta:
        carpeta = pathlib.Path(carpeta)
        shutil.copyfile(str(fuente), str(carpeta / ("fuente" + fuente.suffix)))
        (carpeta / "texto.txt").write_text(texto, encoding="utf-8")
        hecho = herramientas.correr_en(carpeta, [
            herramientas.FFMPEG, "-nostdin", "-hide_banner", "-loglevel",
            "error", "-y", "-f", "lavfi", "-i",
            "color=c=black@0.0:s={}x{}:r={}:d={:.3f},format=rgba".format(
                ancho, alto, ritmo, segundos),
            "-vf", filtro, "-c:v", "prores_ks", "-profile:v", "4444",
            "-pix_fmt", "yuva444p10le", str(destino)])
    return hecho.returncode == 0 and pathlib.Path(destino).exists()


def _pista_de_textos(linea):
    """El numero de la pista 'Textos', creandola arriba de todo si falta."""
    for n in range(1, (linea.GetTrackCount("video") or 0) + 1):
        if (linea.GetTrackName("video", n) or "") == NOMBRE_PISTA:
            return n
    linea.AddTrack("video")
    n = linea.GetTrackCount("video")
    linea.SetTrackName("video", n, NOMBRE_PISTA)
    return n


def _contar(linea):
    return {(t, i): len(linea.GetItemListInTrack(t, i) or [])
            for t in ("video", "audio")
            for i in range(1, (linea.GetTrackCount(t) or 0) + 1)}


def poner(proyecto, texto, segundo, segundos=DURACION):
    """
    Pone 'texto' en el segundo 'segundo' de la linea de tiempo abierta.

    No pisa nada: si en la pista de textos ya hay otro texto en ese
    momento, avisa y no lo pone.
    """
    linea = proyecto.GetCurrentTimeline()
    ritmo = float(linea.GetSetting("timelineFrameRate"))
    ancho = int(linea.GetSetting("timelineResolutionWidth"))
    alto = int(linea.GetSetting("timelineResolutionHeight"))
    desde = linea.GetStartFrame() + int(round(float(segundo) * ritmo))
    cuadros = int(round(float(segundos) * ritmo))

    pista = _pista_de_textos(linea)
    for item in linea.GetItemListInTrack("video", pista) or []:
        if item.GetStart() < desde + cuadros and desde < item.GetEnd():
            consola.alerta('"{}" en {} se pisa con "{}", que ya esta ahi. '
                           'No lo pongo.'.format(texto, consola.duracion(
                               segundo), item.GetName()))
            return False

    # En las otras pistas de arriba puede haber textos o apoyos puestos a
    # mano: dos textos a la vez salen encimados, ilegibles (paso en la
    # prueba del 02/10/2026). No se decide por Juani: se le pregunta.
    encima = [(n, item.GetName())
              for n in range(2, (linea.GetTrackCount("video") or 0) + 1)
              if n != pista
              for item in linea.GetItemListInTrack("video", n) or []
              if item.GetStart() < desde + cuadros and desde < item.GetEnd()]
    if encima:
        consola.alerta('en {} ya hay algo arriba del video: {}'.format(
            consola.duracion(segundo), ", ".join(
                '"{}" (V{})'.format(nombre, n) for n, nombre in encima)))
        respuesta = consola.preguntar('      Pongo "{}" igual? (s/n) '
                                      .format(texto))
        if respuesta.lower() not in ("s", "si", "sí", "dale"):
            consola.detalle("No lo pongo.")
            return False

    SALIDA.mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r'[\\/:*?"<>|]', "", texto)[:40].strip() or "texto"
    destino = SALIDA / "{} {}.mov".format(
        nombre, datetime.datetime.now().strftime("%Y%m%d %H%M%S"))
    if not dibujar(texto, ancho, alto, ritmo, segundos, destino):
        consola.error('no pude dibujar "{}".'.format(texto))
        return False

    bloqueada = bool(linea.GetIsTrackLocked("video", pista))
    if bloqueada:
        linea.SetTrackLock("video", pista, False)
    try:
        antes = _contar(linea)
        pool = proyecto.GetMediaPool()
        clip = (pool.ImportMedia([str(destino)]) or [None])[0]
        if clip is None:
            consola.error("Resolve no importo el texto.")
            return False
        puesto = pool.AppendToTimeline([{
            "mediaPoolItem": clip, "mediaType": 1, "trackIndex": pista,
            "startFrame": 0, "endFrame": cuadros,
            "recordFrame": desde}]) or []
        despues = _contar(linea)
        otras = [k for k in antes if k != ("video", pista)
                 and antes[k] != despues.get(k)]
        if not puesto or puesto[0] is None or otras or \
                despues[("video", pista)] != antes[("video", pista)] + 1:
            consola.error('"{}" no quedo como esperaba (otras pistas '
                          'cambiadas: {}).'.format(texto, otras))
            return False
        consola.hecho('"{}" en {}, {:g} s, pista {}'.format(
            texto, consola.duracion(segundo), float(segundos), NOMBRE_PISTA))
        return True
    finally:
        if bloqueada:
            linea.SetTrackLock("video", pista, True)
