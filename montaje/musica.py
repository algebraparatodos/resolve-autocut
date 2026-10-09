# -*- coding: utf-8 -*-
"""
Musica de fondo que no tapa a quien habla.

Lo que se hizo a mano el 02/10/2026, convertido en una orden:

1. Se lee la linea de tiempo como esta AHORA: donde cae cada voz (pista
   de audio 1) y cuanto dura la imagen y la voz. El largo NO sale del
   final de la linea: la musica vieja puede ser mas larga que lo que
   quedo despues de los cortes, y entonces la nueva saldria larga.
2. Se arma una pista guia con esas voces en su sitio.
3. Se encadenan las canciones con fundidos de 3 s, repitiendo desde la
   primera si no alcanzan, se recorta al largo justo con un fundido de
   salida de 6 s, y se agacha bajo la voz con un compresor que escucha
   la guia. Queda unos 17 dB por debajo de la voz, medido.
4. Se pone en la pista de audio 2, reemplazando la musica anterior.

La API de Resolve no deja tocar el volumen de un clip, por eso todo esto
se cocina en un .wav y no con automatizacion dentro de Resolve.

Si Juani corta despues, las bajadas quedan corridas: hay que volver a
pedir la musica. Y Juani bloquea la pista de la musica mientras corta;
se desbloquea para cambiarla y se vuelve a dejar bloqueada.
"""

import datetime
import json
import pathlib
import tempfile

from . import consola, herramientas
from .voz import deteccion

CARPETA = pathlib.Path.home() / "Desktop" / "Edicion" / "3. Musica"
SALIDA = pathlib.Path(__file__).resolve().parent.parent / "musica de fondo"
PISTA = 2
FUNDIDO = 3.0
FINAL = 6.0
EXTENSIONES = (".wav", ".mp3", ".m4a", ".aif", ".aiff", ".flac")


def disponibles():
    """Las canciones de la carpeta de musica, con su ruta, por nombre."""
    if not CARPETA.exists():
        return []
    return sorted((r for r in CARPETA.rglob("*")
                   if r.suffix.lower() in EXTENSIONES),
                  key=lambda r: r.name.lower())


def nombre_corto(ruta):
    """'ES_Painting (Instrumental Version) - Velee.wav' -> legible."""
    nombre = pathlib.Path(ruta).stem
    return nombre[3:] if nombre.startswith("ES_") else nombre


def _duracion(ruta):
    salida = herramientas.correr([herramientas.FFPROBE, "-v", "error",
                                  "-show_entries", "format=duration",
                                  "-of", "csv=p=0", str(ruta)])
    try:
        return float(salida.stdout.strip())
    except ValueError:
        return 0.0


def _leer_linea(linea):
    """Las voces de la pista 1 y el largo de imagen y voz, en segundos."""
    ritmo = float(linea.GetSetting("timelineFrameRate"))
    cero = linea.GetStartFrame()
    piezas, fin = [], cero
    for item in linea.GetItemListInTrack("audio", 1) or []:
        clip = item.GetMediaPoolItem()
        if clip is None:
            continue
        piezas.append({"archivo": clip.GetClipProperty("File Path"),
                       "desde": item.GetLeftOffset() / ritmo,
                       "dura": item.GetDuration() / ritmo,
                       "en": (item.GetStart() - cero) / ritmo})
        fin = max(fin, item.GetEnd())
    for indice in range(1, (linea.GetTrackCount("video") or 0) + 1):
        for item in linea.GetItemListInTrack("video", indice) or []:
            fin = max(fin, item.GetEnd())
    return piezas, (fin - cero) / ritmo


def _mezclar(canciones, guia, largo, destino):
    """El .wav de fondo: encadenado, recortado, nivelado y agachado."""
    orden, total = [], 0.0
    while total < largo + FINAL and canciones:
        for cancion in canciones:
            orden.append(cancion)
            total += _duracion(cancion) - FUNDIDO
            if total >= largo + FINAL:
                break

    entradas, filtros = [], []
    for i, cancion in enumerate(orden):
        entradas += ["-i", str(cancion)]
        filtros.append("[{0}:a]aresample=48000,"
                       "aformat=channel_layouts=stereo[c{0}]".format(i))
    actual = "c0"
    for i in range(1, len(orden)):
        filtros.append("[{}][c{}]acrossfade=d={}[x{}]".format(
            actual, i, FUNDIDO, i))
        actual = "x{}".format(i)
    filtros.append(
        "[{}]atrim=0:{:.3f},afade=t=out:st={:.3f}:d={},"
        "loudnorm=I=-25:TP=-6:LRA=11,aresample=48000[musica]".format(
            actual, largo, max(0.0, largo - FINAL), FINAL))
    filtros.append("[{}:a]aresample=48000,"
                   "aformat=channel_layouts=stereo[voz]".format(len(orden)))
    filtros.append("[musica][voz]sidechaincompress=threshold=0.03:ratio=3:"
                   "attack=30:release=500[fondo]")

    hecho = herramientas.correr(
        [herramientas.FFMPEG, "-nostdin", "-hide_banner", "-loglevel",
         "error", "-y"] + entradas + ["-i", str(guia), "-filter_complex",
                                      ";".join(filtros), "-map", "[fondo]",
                                      "-c:a", "pcm_s16le", "-ar", "48000",
                                      str(destino)])
    return hecho.returncode == 0 and pathlib.Path(destino).exists(), orden


def _contar(linea):
    return {(tipo, i): len(linea.GetItemListInTrack(tipo, i) or [])
            for tipo in ("video", "audio")
            for i in range(1, (linea.GetTrackCount(tipo) or 0) + 1)}


def _es_nuestra(item):
    clip = item.GetMediaPoolItem()
    ruta = (clip.GetClipProperty("File Path") if clip else "") or ""
    return str(SALIDA).lower() in ruta.lower() or \
        "musica\\fondo" in ruta.lower()


def poner(proyecto, canciones):
    """
    Arma la musica con 'canciones' (rutas) y la pone en la pista 2.

    Devuelve True si quedo puesta. Ante cualquier cosa rara frena y lo
    dice, sin dejar la linea de tiempo a medias.
    """
    linea = proyecto.GetCurrentTimeline()
    if linea is None:
        consola.error("no hay ninguna linea de tiempo abierta.")
        return False

    piezas, largo = _leer_linea(linea)
    if not piezas or largo <= 0:
        consola.error("la pista de audio 1 esta vacia: no hay voces bajo "
                      "las que poner musica.")
        return False
    consola.detalle("Linea \"{}\": {} con {} pedazos de voz".format(
        linea.GetName(), consola.duracion(largo), len(piezas)))

    SALIDA.mkdir(parents=True, exist_ok=True)
    destino = SALIDA / "fondo {}.wav".format(
        datetime.datetime.now().strftime("%Y-%m-%d %H%M%S"))
    with tempfile.TemporaryDirectory() as carpeta:
        datos = pathlib.Path(carpeta) / "voces.json"
        guia = pathlib.Path(carpeta) / "guia.wav"
        datos.write_text(json.dumps({"duracion": largo, "piezas": piezas}),
                         encoding="utf-8")
        consola.detalle("Armo la guia de voces...")
        if not deteccion.guia_de_voz(str(datos), str(guia)):
            consola.error("no pude armar la guia de voces.")
            return False
        consola.detalle("Mezclo la musica (unos segundos por minuto)...")
        salio, orden = _mezclar(canciones, guia, largo, destino)
    if not salio:
        consola.error("ffmpeg no pudo armar la musica.")
        return False
    consola.hecho("musica armada: " + " -> ".join(nombre_corto(c)
                                                  for c in orden))

    return _colocar(proyecto, linea, destino)


def _colocar(proyecto, linea, archivo):
    """Saca la musica vieja de la pista 2 y pone la nueva, midiendo."""
    while (linea.GetTrackCount("audio") or 0) < PISTA:
        linea.AddTrack("audio", "stereo")

    viejos = linea.GetItemListInTrack("audio", PISTA) or []
    ajenos = [i for i in viejos if not _es_nuestra(i)]
    if ajenos:
        consola.error("en la pista de audio {} hay clips que no son musica "
                      "de este programa ({}). No los toco: movelos a otra "
                      "pista y volve a pedirlo.".format(
                          PISTA, ", ".join(i.GetName() for i in ajenos[:3])))
        return False

    bloqueada = bool(linea.GetIsTrackLocked("audio", PISTA))
    if bloqueada:
        linea.SetTrackLock("audio", PISTA, False)
    try:
        antes = _contar(linea)
        if viejos and not linea.DeleteClips(viejos, False):
            consola.error("Resolve no quiso sacar la musica anterior.")
            return False
        despues = _contar(linea)
        tocadas = [k for k in antes if k != ("audio", PISTA)
                   and antes[k] != despues.get(k)]
        if tocadas:
            consola.error("al sacar la musica vieja cambiaron otras pistas "
                          "({}). Paro aca: revisalo antes de seguir."
                          .format(tocadas))
            return False

        pool = proyecto.GetMediaPool()
        clip = (pool.ImportMedia([str(archivo)]) or [None])[0]
        if clip is None:
            consola.error("Resolve no importo la musica.")
            return False
        ritmo = float(linea.GetSetting("timelineFrameRate"))
        _, largo = _leer_linea(linea)
        puesto = pool.AppendToTimeline([{
            "mediaPoolItem": clip, "mediaType": 2, "trackIndex": PISTA,
            "startFrame": 0, "endFrame": int(round(largo * ritmo)),
            "recordFrame": linea.GetStartFrame()}]) or []

        final = _contar(linea)
        cambiaron = [k for k in antes if k != ("audio", PISTA)
                     and antes[k] != final.get(k)]
        if not puesto or cambiaron or final.get(("audio", PISTA)) != 1:
            consola.error("la musica no quedo como esperaba (pista {}: {} "
                          "clips; otras pistas cambiadas: {})".format(
                              PISTA, final.get(("audio", PISTA)), cambiaron))
            return False
        consola.hecho("musica en la pista de audio {}, de 0:00 a {}".format(
            PISTA, consola.duracion(largo)))
        return True
    finally:
        if bloqueada:
            linea.SetTrackLock("audio", PISTA, True)
            consola.detalle("La pista {} quedo bloqueada otra vez, como "
                            "estaba.".format(PISTA))
