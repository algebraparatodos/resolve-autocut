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

  guia   PIEZAS_JSON SALIDA_WAV
         Arma una pista con las voces tal como quedaron en la linea de
         tiempo, para que la musica sepa cuando agacharse.

  graves RUTA TONO_MAXIMO_HZ SEGUNDOS_MINIMOS
         En que tramos se oye una voz mas grave que TONO_MAXIMO_HZ, y
         el tono tipico de todo el audio.
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


def _leer_audio(ruta, numpy):
    """El audio en un solo canal a 16 kHz, o None si ffmpeg no pudo."""
    ffmpeg = buscar_ffmpeg()
    if ffmpeg is None:
        return None
    with tempfile.TemporaryDirectory() as carpeta:
        crudo = pathlib.Path(carpeta) / "audio.raw"
        hecho = subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-i", ruta,
             "-map", "0:a:0", "-ac", "1", "-ar", "16000",
             "-f", "f32le", "-y", str(crudo)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if hecho.returncode != 0:
            return None
        return numpy.fromfile(str(crudo), dtype=numpy.float32)


def tono_por_cuadro(audio, numpy, muestreo=16000, minimo=60, maximo=400,
                    marco=0.04, paso=0.01, umbral=0.25):
    """
    El tono de la voz cada 10 ms, por el metodo YIN. 0 donde no hay tono.

    YIN y no una autocorrelacion a secas porque la autocorrelacion se
    equivoca de octava muy seguido: da la mitad del tono real, y una voz
    de 220 Hz pasa por una de 110, que es justo la confusion que este
    modo no se puede permitir. YIN normaliza la diferencia y se queda con
    el primer valle, que es el periodo de verdad.

    Va por bloques para no armar de una vez una matriz de una hora de
    audio, que no entra en memoria.
    """
    largo = int(marco * muestreo)
    salto = int(paso * muestreo)
    tmin = int(muestreo / maximo)
    tmax = int(muestreo / minimo)
    cuantos = max(0, 1 + (len(audio) - largo - tmax) // salto)
    tonos = numpy.zeros(cuantos)
    fft = 1 << int(numpy.ceil(numpy.log2(2 * (largo + tmax))))
    retardos = numpy.arange(1, tmax + 1)

    for desde in range(0, cuantos, 2000):
        n = min(2000, cuantos - desde)
        indices = (numpy.arange(largo + tmax)[None, :]
                   + salto * (desde + numpy.arange(n))[:, None])
        marcos = audio[indices]
        marcos = marcos - marcos.mean(1, keepdims=True)

        cruzada = numpy.fft.irfft(
            numpy.fft.rfft(marcos, fft)
            * numpy.conj(numpy.fft.rfft(marcos[:, :largo], fft)),
            fft)[:, :tmax + 1]
        energia = numpy.cumsum(marcos ** 2, 1)
        propia = energia[:, largo - 1][:, None]
        corrida = numpy.concatenate(
            [propia, energia[:, largo:largo + tmax] - energia[:, :tmax]], 1)
        diferencia = propia + corrida - 2 * cruzada

        normal = (diferencia[:, 1:] * retardos
                  / numpy.maximum(numpy.cumsum(diferencia[:, 1:], 1), 1e-12))
        normal[:, :tmin - 1] = 2.0

        for k in range(n):
            bajo = numpy.flatnonzero(normal[k] < umbral)
            if bajo.size:
                t = bajo[0]
                while t + 1 < tmax and normal[k, t + 1] < normal[k, t]:
                    t += 1
                tonos[desde + k] = muestreo / float(t + 1)
    return tonos


def _quitar_zumbidos(tonos, tono_maximo, numpy, ancho=4.0):
    """
    Borra los cuadros que caen en un zumbido de fondo grave.

    Una maquina, un ventilador o la red electrica suenan siempre en la
    MISMA frecuencia, y fuerte: en "video 5 molderia" habia uno en
    148 Hz que el detector media como voz grave durante cinco minutos de
    un clip donde solo hablaba Natalia. Una voz, en cambio, sube y baja.
    Asi que el zumbido se reconoce como un pico finisimo en la cuenta de
    cuadros por frecuencia, mucho mas alto que lo que tiene alrededor, y
    se borra esa franja estrecha. Bajar el tono maximo hasta dejarlo
    afuera tambien andaba, pero se llevaba frases de Juani que tienen el
    tono justo por encima.
    """
    graves = tonos[(tonos > 0) & (tonos < tono_maximo + 20)]
    if graves.size < 200:
        return
    bordes = numpy.arange(60.0, tono_maximo + 22, 2.0)
    cuenta, _ = numpy.histogram(graves, bins=bordes)
    centros = (bordes[:-1] + bordes[1:]) / 2.0
    for i, cuantos in enumerate(cuenta):
        cerca = numpy.abs(centros - centros[i])
        alrededor = cuenta[(cerca > ancho) & (cerca <= 24)]
        if alrededor.size and cuantos > 200 and cuantos > 5 * numpy.median(
                alrededor) + 20:
            tonos[numpy.abs(tonos - centros[i]) <= ancho] = 0


def modo_graves(argumentos):
    """
    Donde se oye una voz mas grave que la de quien habla.

    Sirve para los videos de Natalia, donde de fondo se oye a Juani
    dando indicaciones. Ella anda por los 200-220 Hz y el por los 105;
    medido el 02/10/2026 sobre "para que vean que soy responsable".

    Un cuadro grave suelto no dice nada: el detector de tono se equivoca
    de vez en cuando aun con YIN, y una voz aguda que baja al final de la
    frase tambien da algun cuadro grave. Lo que delata a la otra persona
    es voz grave SOSTENIDA, por eso se pide una cantidad de cuadros
    graves dentro de cada medio segundo.
    """
    ruta = argumentos[0]
    tono_maximo = float(argumentos[1])
    minimos = int(round(float(argumentos[2]) * 100))     # cuadros de 10 ms

    try:
        import numpy
    except ImportError as fallo:
        return responder({"error": "falta el motor: {}".format(fallo)})

    audio = _leer_audio(ruta, numpy)
    if audio is None:
        return responder({"error": "ffmpeg no pudo leer el audio"})

    tonos = tono_por_cuadro(audio, numpy)

    # Lo que suena bajito no cuenta: en las pausas, un zumbido de fondo
    # tiene tono y el detector lo mide igual que una voz. El audio ya
    # viene nivelado a -14 LUFS, asi que la voz anda por 0,1-0,3 de
    # volumen eficaz y 0,02 deja afuera el fondo sin perder a nadie.
    cuadrado = numpy.concatenate([[0.0], numpy.cumsum(
        audio.astype(numpy.float64) ** 2)])
    desde = numpy.arange(len(tonos)) * 160
    eficaz = numpy.sqrt((cuadrado[desde + 640] - cuadrado[desde]) / 640.0)
    tonos[eficaz < 0.02] = 0
    _quitar_zumbidos(tonos, tono_maximo, numpy)

    con_tono = tonos[tonos > 0]
    if con_tono.size == 0:
        return responder({"mediana": 0, "tramos": []})

    grave = (tonos > 0) & (tonos < tono_maximo)
    aguda = tonos >= tono_maximo
    callado = eficaz < 0.02
    responder({"mediana": round(float(numpy.median(con_tono)), 1),
               "tramos": _tramos_graves(grave, aguda, callado, minimos,
                                        numpy)})


def _tramos_graves(grave, aguda, callado, minimos, numpy):
    """
    Los tramos de la voz grave, con bordes justos, en segundos.

    Juani quiere que el clip donde habla el tenga SOLO su voz, asi que
    los bordes no pueden llevar margen de regalo: un margen fijo se mete
    en la frase de Natalia si ella habla justo antes o despues.

    Se hace en tres pasos:

    1. El nucleo: donde hay voz grave sostenida (al menos 'minimos'
       cuadros graves dentro de cada medio segundo), del primer cuadro
       grave al ultimo.
    2. Se estira hacia los dos lados mientras no aparezca la voz aguda
       ni un silencio de mas de 0,3 s. Asi entran el arranque y el final
       de la frase, que se dicen mas suave y casi sin tono, y la frase
       termina donde de verdad termina.
    3. Dos tramos graves separados por menos de 0,6 s con poca voz aguda
       en el medio se juntan: eso es Juani hablando encima de Natalia, y
       una superposicion cuenta como suya.
    """
    # Un cuadro agudo suelto dentro de la frase de Juani es un error de
    # octava del medidor (paso: 314 Hz en medio de "responsable", que
    # cortaba la frase antes de terminar). La voz de Natalia de verdad
    # da varios cuadros agudos seguidos.
    # Por eso se mira cada quinto de segundo: es voz de ella donde hay
    # varios cuadros agudos Y le ganan con holgura a los graves.
    def en_20(cuadros):
        return numpy.convolve(cuadros.astype(numpy.int32),
                              numpy.ones(20, dtype=numpy.int32), mode="same")
    agudos, graves_cerca = en_20(aguda), en_20(grave)
    aguda = (agudos >= 5) & (agudos > 2 * graves_cerca)

    ventana = 50                                          # medio segundo
    suma = numpy.convolve(grave.astype(numpy.int32),
                          numpy.ones(ventana, dtype=numpy.int32),
                          mode="valid")
    total = len(grave)

    nucleos = []
    for inicio in numpy.flatnonzero(suma >= minimos):
        dentro = numpy.flatnonzero(grave[inicio:inicio + ventana])
        a, b = inicio + dentro[0], inicio + dentro[-1] + 1
        if nucleos and a <= nucleos[-1][1]:
            nucleos[-1][1] = max(nucleos[-1][1], b)
        else:
            nucleos.append([a, b])

    def estirar(desde, paso):
        ultimo_con_voz, quieto, i = desde, 0, desde
        while 0 <= i + paso < total:
            i += paso
            if aguda[i]:
                break
            if callado[i]:
                quieto += 1
                if quieto > 30:
                    break
            else:
                quieto = 0
                ultimo_con_voz = i
        return ultimo_con_voz

    estirados = [[estirar(a, -1), estirar(b - 1, +1) + 1]
                 for a, b in nucleos]

    unidos = []
    for a, b in estirados:
        if unidos and a - unidos[-1][1] < 60 and                 aguda[unidos[-1][1]:max(a, unidos[-1][1])].sum() < 20:
            unidos[-1][1] = max(unidos[-1][1], b)
        else:
            unidos.append([a, b])

    return [[a / 100.0, b / 100.0] for a, b in unidos]


def modo_guia(argumentos):
    """
    Las voces de la linea de tiempo, pegadas donde caen, en un .wav mono.

    La musica de fondo se agacha cuando alguien habla, y para eso ffmpeg
    necesita una pista con la voz en su sitio. Se arma leyendo cada
    pedazo de su .wav nivelado: es lo que suena en la linea de tiempo.
    """
    import wave
    try:
        import numpy
    except ImportError as fallo:
        return responder({"error": "falta el motor: {}".format(fallo)})

    datos = json.loads(pathlib.Path(argumentos[0]).read_text(
        encoding="utf-8"))
    muestreo = 48000
    salida = numpy.zeros(int(datos["duracion"] * muestreo) + muestreo,
                         dtype=numpy.float32)
    abiertos = {}
    temporal = tempfile.TemporaryDirectory()
    ffmpeg = buscar_ffmpeg()
    for pieza in datos["piezas"]:
        archivo = pieza["archivo"]
        if archivo not in abiertos:
            # Despues del montaje la pista 1 son los .wav nivelados, pero
            # en una linea armada a mano puede haber audio de un video:
            # eso se pasa a .wav antes, porque 'wave' solo lee .wav.
            legible = archivo
            if not archivo.lower().endswith(".wav"):
                legible = str(pathlib.Path(temporal.name)
                              / "{}.wav".format(len(abiertos)))
                subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y",
                                "-i", archivo, "-map", "0:a:0", "-ac", "1",
                                "-ar", "48000", "-c:a", "pcm_s16le",
                                legible], capture_output=True)
            abiertos[archivo] = wave.open(legible)
        w = abiertos[archivo]
        propio = w.getframerate()
        w.setpos(min(w.getnframes(), int(round(pieza["desde"] * propio))))
        crudo = w.readframes(int(round(pieza["dura"] * propio)))
        x = (numpy.frombuffer(crudo, dtype=numpy.int16).astype(numpy.float32)
             / 32768.0).reshape(-1, w.getnchannels()).mean(1)
        if propio != muestreo and x.size:
            x = numpy.interp(numpy.arange(int(x.size * muestreo / propio))
                             * propio / muestreo, numpy.arange(x.size), x)
        desde = int(round(pieza["en"] * muestreo))
        hasta = min(salida.size, desde + x.size)
        salida[desde:hasta] += x[:hasta - desde]

    out = wave.open(argumentos[1], "wb")
    out.setnchannels(1)
    out.setsampwidth(2)
    out.setframerate(muestreo)
    out.writeframes((numpy.clip(salida, -1, 1) * 32767)
                    .astype(numpy.int16).tobytes())
    out.close()
    for w in abiertos.values():
        w.close()
    temporal.cleanup()
    responder({"piezas": len(datos["piezas"])})


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
        elif modo == "graves":
            modo_graves(argumentos)
        elif modo == "guia":
            modo_guia(argumentos)
        else:
            responder({"error": "no conozco el modo '{}'".format(modo)})
            return 1
    except Exception as fallo:            # el proceso de arriba lee JSON
        responder({"error": "{}: {}".format(type(fallo).__name__, fallo)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
