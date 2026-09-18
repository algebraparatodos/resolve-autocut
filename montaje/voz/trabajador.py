# -*- coding: utf-8 -*-
"""
Lo que corre DENTRO del entorno del motor de voz, no en el programa.

Este archivo no se importa nunca desde el resto del paquete: se lanza
como un proceso aparte con el Python del entorno virtual, y contesta una
linea de JSON por la salida estandar. Por eso no importa nada de
'montaje' ni usa nada que no este en ese entorno.

Dos modos:

  voz    RUTA UMBRAL PAUSA_MS MINIMO_MS
         En que tramos hay voz humana, en segundos.

  texto  RUTA MODELO IDIOMA
         Que se dice y en que segundo, frase por frase.
"""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile


def buscar_ffmpeg():
    encontrado = shutil.which("ffmpeg")
    if encontrado:
        return encontrado
    patron = (pathlib.Path.home() / "AppData" / "Local" / "Microsoft"
              / "WinGet" / "Packages")
    for ruta in patron.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
        return str(ruta)
    return None


def responder(datos):
    """
    Contesta en JSON, siempre en UTF-8.

    Se escribe a bytes y no con print a proposito. La consola de Windows
    no suele estar en UTF-8, asi que un print con acentos sale en la
    codificacion del sistema y del otro lado llega roto. Y roto no quiere
    decir ilegible: quiere decir que "ecuacion" con tilde se convierte en
    dos palabras al normalizar, y entonces dos tomas identicas dejan de
    parecerse. Un error de codificacion aca se manifiesta como
    repeticiones que no se detectan, que es lo ultimo donde uno lo
    buscaria.
    """
    crudo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(crudo + b"\n")
    sys.stdout.buffer.flush()


def modo_voz(argumentos):
    """
    Los tramos con voz, usando el detector de Silero.

    Medir volumen no alcanza y ese es el punto entero de este modo. Un
    teclado, un golpe en la mesa, una silla o el aire acondicionado pasan
    cualquier umbral de volumen y se cuelan como si fueran habla. Silero
    distingue una voz humana de un ruido aunque el ruido suene mas
    fuerte.
    """
    ruta = argumentos[0]
    umbral = float(argumentos[1])
    pausa_ms = int(argumentos[2])
    minimo_ms = int(argumentos[3])

    ffmpeg = buscar_ffmpeg()
    if ffmpeg is None:
        return responder({"error": "no encuentro ffmpeg"})

    try:
        import numpy
        from faster_whisper.vad import get_speech_timestamps, VadOptions
    except ImportError as fallo:
        return responder({"error": "falta el motor: {}".format(fallo)})

    # El detector trabaja con audio plano a 16 kHz en un solo canal, que
    # es como fue entrenado. Se escribe a un archivo y no se lee por
    # tuberia: una hora de video son 230 MB, y pasarlos por una tuberia
    # mientras nadie los va sacando cuelga a los dos procesos.
    with tempfile.TemporaryDirectory() as carpeta:
        crudo = pathlib.Path(carpeta) / "audio.raw"
        hecho = subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-i", ruta,
             "-map", "0:a:0", "-ac", "1", "-ar", "16000",
             "-f", "f32le", "-y", str(crudo)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if hecho.returncode != 0:
            return responder({"error": "ffmpeg no pudo leer el audio"})
        audio = numpy.fromfile(str(crudo), dtype=numpy.float32)

    if audio.size == 0:
        return responder({"tramos": []})

    # El aire de antes y despues lo pone el programa principal, no el
    # detector: asi hay un solo sitio donde cambiarlo.
    opciones = VadOptions(threshold=umbral,
                          min_speech_duration_ms=minimo_ms,
                          min_silence_duration_ms=pausa_ms,
                          speech_pad_ms=0)

    tramos = get_speech_timestamps(audio, opciones, sampling_rate=16000)
    responder({"tramos": [[t["start"] / 16000.0, t["end"] / 16000.0]
                          for t in tramos]})


def modo_texto(argumentos):
    """
    Que se dice y en que segundo.

    Sirve para una sola cosa: comparar frases entre si y darse cuenta de
    cuando alguien repitio lo mismo dos veces. No es un subtitulado, asi
    que no hace falta el modelo grande: 'small' acierta de sobra para
    comparar y es varias veces mas rapido en un procesador.
    """
    ruta = argumentos[0]
    modelo = argumentos[1] if len(argumentos) > 1 else "small"
    idioma = argumentos[2] if len(argumentos) > 2 else "es"

    try:
        from faster_whisper import WhisperModel
    except ImportError as fallo:
        return responder({"error": "falta el motor: {}".format(fallo)})

    motor = WhisperModel(modelo, device="cpu", compute_type="int8")
    segmentos, _ = motor.transcribe(ruta, language=idioma, vad_filter=True)

    responder({"frases": [{"inicio": round(s.start, 2),
                           "fin": round(s.end, 2),
                           "texto": s.text.strip()}
                          for s in segmentos]})


def main():
    if len(sys.argv) < 3:
        responder({"error": "faltan argumentos"})
        return 1

    modo, argumentos = sys.argv[1], sys.argv[2:]
    try:
        if modo == "voz":
            modo_voz(argumentos)
        elif modo == "texto":
            modo_texto(argumentos)
        else:
            responder({"error": "no conozco el modo '{}'".format(modo)})
            return 1
    except Exception as fallo:            # el proceso de arriba lee JSON
        responder({"error": "{}: {}".format(type(fallo).__name__, fallo)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
