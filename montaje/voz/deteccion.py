# -*- coding: utf-8 -*-
"""
El puente con el motor de voz: se le pide trabajo y se le lee la
respuesta en JSON.
"""

import json
import os
import pathlib
import subprocess

from .. import consola
from . import motor

TRABAJADOR = pathlib.Path(__file__).resolve().parent / "trabajador.py"


def _preguntar(python, modo, argumentos, cuanto_tarda=None):
    """
    Lanza el trabajador y devuelve su respuesta, o None.

    Nunca levanta una excepcion: si el motor falla, el programa tiene que
    poder decirlo y seguir con lo que si puede hacer, no plantarse a
    mitad del montaje.
    """
    if cuanto_tarda:
        consola.detalle(cuanto_tarda)

    # PYTHONIOENCODING para que el trabajador no herede la codificacion
    # de la consola de Windows, que no es UTF-8 y rompe los acentos.
    entorno = dict(os.environ)
    entorno["PYTHONIOENCODING"] = "utf-8"

    hecho = subprocess.run(
        [str(python), str(TRABAJADOR), modo] + [str(a) for a in argumentos],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=entorno)

    if hecho.returncode != 0 or not (hecho.stdout or "").strip():
        consola.alerta("el motor de voz fallo.")
        ultimo = (hecho.stderr or "").strip().splitlines()[-1:]
        if ultimo:
            consola.detalle(ultimo[0])
        return None

    try:
        respuesta = json.loads(hecho.stdout.strip().splitlines()[-1])
    except ValueError:
        consola.alerta("no entendi la respuesta del motor de voz.")
        return None

    if "error" in respuesta:
        consola.alerta("motor de voz: {}".format(respuesta["error"]))
        return None

    return respuesta


def tramos_con_voz(ruta, ajustes, largo):
    """
    Los tramos en los que hay alguien hablando, en segundos.

    Aca esta la definicion que hace o rompe la herramienta: **silencio
    es donde nadie habla, no donde no suena nada**. Son dos cosas
    distintas y confundirlas arruina el resultado aunque todo lo demas
    este bien. Por eso se usa un detector de voz y no un medidor de
    nivel.

    Devuelve None si el motor no esta disponible, para que quien llama
    decida si sigue sin cortar o se planta.
    """
    python = motor.asegurar()
    if python is None:
        return None

    respuesta = _preguntar(
        python, "voz",
        [ruta, ajustes["confianza_voz"],
         int(ajustes["pausa_minima"] * 1000),
         int(ajustes["tramo_minimo"] * 1000)])

    if respuesta is None:
        return None

    return afinar(respuesta.get("tramos", []), largo, ajustes)


def afinar(tramos, largo, ajustes):
    """
    Ensancha cada tramo con su aire, tira los cachitos sueltos y junta
    los que quedaron pisandose.

    El aire importa porque el detector marca la voz justa: sin el, cada
    corte se come el ataque de la primera palabra y el final de la
    ultima, y se nota muchisimo.

    Juntar los que se pisan tambien: dos tramos pegados producen un corte
    que no saca nada y ensucia la linea de tiempo con un clip de mas.
    """
    con_margen = []
    for inicio, fin in tramos:
        inicio = max(0.0, inicio - ajustes["margen_antes"])
        fin = min(largo, fin + ajustes["margen_despues"])
        if fin - inicio >= ajustes["tramo_minimo"]:
            con_margen.append([inicio, fin])

    unidos = []
    for tramo in con_margen:
        if unidos and tramo[0] <= unidos[-1][1]:
            unidos[-1][1] = max(unidos[-1][1], tramo[1])
        else:
            unidos.append(tramo)

    return unidos


def _archivo_de_cache(carpeta, ruta):
    """
    Donde se guarda lo que ya se escucho de un video.

    El nombre lleva el tamano del archivo pegado atras. Asi, si alguien
    reemplaza un video por otro con el mismo nombre, el texto viejo no se
    da por bueno: cambia el tamano y cambia el archivo de cache.
    """
    ruta = pathlib.Path(ruta)
    try:
        peso = ruta.stat().st_size
    except OSError:
        peso = 0
    return pathlib.Path(carpeta) / "{}.{}.json".format(ruta.stem, peso)


def frases(ruta, carpeta_cache=None, clave=None, modelo="small", idioma="es"):
    """
    Que se dice y en que segundo, para poder comparar.

    Es con diferencia el paso mas lento del montaje: escuchar una hora de
    video se toma su rato largo. Por eso se guarda el resultado, y volver
    a montar la misma carpeta no lo repite. Vale la pena porque el motivo
    normal para volver a montar es que algo salio mal en Resolve, y ahi
    el texto no cambio.

    'clave' es con que archivo se guarda lo escuchado, y existe porque
    NO es lo mismo que 'ruta'. Se escucha el .wav nivelado, que se lee
    mucho mas rapido que el video, pero se guarda a nombre del original,
    que es lo unico que no cambia. Guardandolo a nombre del .wav, el dia
    que se regenere el audio, o que se cambie el nivel al que se nivela,
    todo el trabajo de escuchar se tira y hay que rehacerlo aunque lo que
    se dice sea exactamente lo mismo.

    Devuelve [] si el motor no esta: sin texto no se pueden detectar
    repeticiones, pero el resto del montaje sigue teniendo sentido.
    """
    guardado = (_archivo_de_cache(carpeta_cache, clave or ruta)
                if carpeta_cache else None)

    if guardado is not None and guardado.exists():
        try:
            return json.loads(guardado.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass        # si esta roto se vuelve a escuchar, y ya

    python = motor.asegurar()
    if python is None:
        return []

    respuesta = _preguntar(
        python, "texto", [ruta, modelo, idioma],
        cuanto_tarda="Escuchando lo que se dice, para agrupar las "
                     "repetidas. Es lo que mas tarda, y se guarda para "
                     "no repetirlo.")

    if respuesta is None:
        return []

    escuchado = respuesta.get("frases", [])
    if guardado is not None and escuchado:
        try:
            guardado.parent.mkdir(parents=True, exist_ok=True)
            guardado.write_text(json.dumps(escuchado, ensure_ascii=False),
                                encoding="utf-8")
        except OSError:
            pass        # no poder guardarlo no es motivo para fallar
    return escuchado
