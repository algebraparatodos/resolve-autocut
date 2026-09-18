# -*- coding: utf-8 -*-
"""
Dejar la voz a un nivel parejo, ni alta ni baja.

Por que se hace aca y no en Resolve: la API no expone el volumen.
'TimelineItem.SetProperty' acepta Pan, Zoom, Crop, Opacity y el resto de
la geometria, pero no hay ninguna clave de audio, y tampoco hay nada
equivalente a 'Normalize Audio Levels' del menu. Comprobado contra el SDK
de Resolve 21. Asi que el nivelado va antes de importar.

**Lo que se escribe es SOLO el audio, no una copia del video.** Parece un
detalle de implementacion y es la diferencia entre 700 MB y 22 GB. La
primera version copiaba el archivo entero con '-c:v copy' para cambiarle
una pista de audio de 90 MB: el video no se recodificaba, pero los bytes
se copiaban igual y el material quedaba duplicado en disco. En una
carpeta de 23 GB eso llena un disco.

Lo que se hace en su lugar es lo que hace cualquier editor: el video sale
del archivo original y el audio de un .wav aparte, montados juntos en la
linea de tiempo. Probado, quedan alineados al cuadro.

Como se nivela: 'loudnorm' de ffmpeg en dos pasadas. La primera mide el
archivo entero y no escribe nada; la segunda aplica la correccion con esa
medida en la mano. En una sola pasada el filtro va adivinando sobre la
marcha, y el arranque del video queda a otro nivel que el final, que es
justo lo que se estaba tratando de evitar.
"""

import json
import pathlib
import re

from . import consola, herramientas


def medir(ruta, ajustes):
    """
    Primera pasada: cuanto suena el archivo, sin tocarlo.

    loudnorm escribe su medida en JSON por la salida de errores, mezclada
    con el resto de los avisos de ffmpeg, asi que hay que recortar el
    ultimo bloque entre llaves.
    """
    filtro = ("loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json"
              .format(I=ajustes["objetivo_lufs"],
                      TP=ajustes["pico_maximo_dbtp"],
                      LRA=ajustes["rango_lu"]))

    salida = herramientas.correr(
        [herramientas.FFMPEG, "-nostdin", "-hide_banner", "-i", str(ruta),
         "-map", "0:a:0", "-af", filtro, "-f", "null", "-"])

    bloques = re.findall(r"\{[^{}]*\}", salida.stderr or "", re.S)
    for bruto in reversed(bloques):
        try:
            medida = json.loads(bruto)
        except ValueError:
            continue
        if "input_i" in medida:
            return medida
    return None


def hace_falta(medida, ajustes, tolerancia=1.0):
    """
    Si el archivo ya esta donde tiene que estar, no se corrige.

    Igual se escribe el .wav, porque el montaje necesita la pista de
    audio como archivo suelto. Lo que se saltea es la correccion.
    """
    try:
        actual = float(medida.get("input_i"))
    except (TypeError, ValueError):
        return True
    return abs(actual - float(ajustes["objetivo_lufs"])) > tolerancia


def _filtro_de_correccion(medida, ajustes):
    """
    El filtro de la segunda pasada, con la medida ya tomada.

    'linear=true' pide que la correccion sea una ganancia pareja para
    todo el archivo en vez de ir comprimiendo dinamicamente. Para una voz
    hablada es lo que se quiere: que suba entera, no que le aplasten los
    picos.
    """
    return ("loudnorm=I={I}:TP={TP}:LRA={LRA}"
            ":measured_I={mi}:measured_TP={mtp}:measured_LRA={mlra}"
            ":measured_thresh={mth}:offset={off}:linear=true"
            ).format(I=ajustes["objetivo_lufs"],
                     TP=ajustes["pico_maximo_dbtp"],
                     LRA=ajustes["rango_lu"],
                     mi=medida["input_i"], mtp=medida["input_tp"],
                     mlra=medida["input_lra"], mth=medida["input_thresh"],
                     off=medida.get("target_offset", "0.0"))


def escribir_pista(origen, destino, filtro=None):
    """
    Saca el audio a un .wav, con o sin correccion.

    Va en PCM y no en un formato comprimido porque el original casi
    siempre ya viene comprimido, y volver a comprimir lo que se acaba de
    descomprimir pierde calidad sin necesidad. Un .wav de una hora son
    unos 350 MB, que al lado de los 22 GB que costaba copiar el video no
    es nada.
    """
    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    orden = [herramientas.FFMPEG, "-nostdin", "-hide_banner", "-y",
             "-i", str(origen), "-map", "0:a:0", "-vn"]
    if filtro:
        orden += ["-af", filtro]
    orden += ["-c:a", "pcm_s16le", "-ar", "48000", str(destino)]

    salida = herramientas.correr(orden)
    if salida.returncode != 0 or not destino.exists():
        ultimo = (salida.stderr or "").strip().splitlines()[-1:]
        return False, ultimo[0] if ultimo else "ffmpeg no pudo"
    return True, ""


def preparar(ruta, carpeta_destino, ajustes):
    """
    Deja la pista de audio nivelada de un video, como archivo aparte.

    Devuelve (ruta_del_wav, nivel_de_entrada). El wav es None si no se
    pudo sacar el audio, y ahi quien llama monta el clip entero como
    viene, que suena peor pero es mejor que no montar nada.
    """
    nombre = pathlib.Path(ruta).stem + ".wav"
    destino = pathlib.Path(carpeta_destino) / nombre

    if destino.exists() and destino.stat().st_size > 0:
        consola.hecho("{}: ya tenia el audio preparado"
                      .format(pathlib.Path(ruta).name))
        return destino, None

    medida = medir(ruta, ajustes)

    if medida is None:
        consola.alerta("no pude medir el audio de {}, lo saco tal cual"
                       .format(pathlib.Path(ruta).name))
        salio, _ = escribir_pista(ruta, destino)
        return (destino if salio else None), None

    entrada = float(medida["input_i"])

    if not hace_falta(medida, ajustes):
        salio, queja = escribir_pista(ruta, destino)
        if salio:
            consola.hecho("{}: ya estaba en {:.1f} LUFS, no lo toco"
                          .format(pathlib.Path(ruta).name, entrada))
        return (destino if salio else None), entrada

    salio, queja = escribir_pista(ruta, destino,
                                  _filtro_de_correccion(medida, ajustes))
    if not salio:
        consola.alerta("no pude nivelar {} ({})"
                       .format(pathlib.Path(ruta).name, queja or "sin detalle"))
        return None, entrada

    consola.hecho("{}: de {:.1f} a {:.1f} LUFS"
                  .format(pathlib.Path(ruta).name, entrada,
                          float(ajustes["objetivo_lufs"])))
    return destino, entrada
