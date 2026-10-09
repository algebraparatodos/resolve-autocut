# -*- coding: utf-8 -*-
"""
Proponer titulos de seccion a partir de lo que se dice en el video.

Decision de Juani del 02/10/2026: los textos no los dicta, los propone el
programa y el elige cuales van. Asi que esto NUNCA pone nada sin que el
lo apruebe: muestra la lista numerada y espera.

De donde sale el texto: de las transcripciones que el montaje ya guardo
en "<carpeta> - montaje/lo que se dice", una por video original. Para
cada clip de voz de la linea de tiempo se toma lo que se dice en su
pedazo de material y se lo ubica en el minuto de la linea de tiempo en
que suena. Asi los titulos caen donde quedo el video despues de los
cortes, no donde estaba en el crudo.
"""

import json
import pathlib

from . import consola, ia

SISTEMA = (
    "Recibis la transcripcion de un video ya editado, con el minuto de la "
    "linea de tiempo en que se dice cada frase. Casi siempre es una clase "
    "de ceramica de Natalia (moldes, escayola, barro, encofrados). "
    "Dividilo en las partes en que cambia de tema o de etapa del trabajo y "
    "propone un titulo para cada parte, para ponerlo en pantalla. "
    "Reglas: entre 3 y 10 partes; titulos de 2 a 5 palabras, en castellano "
    "rioplatense, sin punto final, que digan que se hace o se ve (por "
    "ejemplo 'Preparamos el encofrado'); 'segundo' es donde empieza esa "
    "parte: copia tal cual, sin convertirlo, el numero entre corchetes de "
    "la frase con que empieza; no inventes partes que no estan; "
    "no pongas ninguna en los primeros 3 segundos. En 'por_que' una frase "
    "corta que explique de que va la parte.")

ESQUEMA = {
    "type": "object",
    "properties": {
        "secciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "segundo": {"type": "number"},
                    "por_que": {"type": "string"},
                },
                "required": ["titulo", "segundo", "por_que"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["secciones"],
    "additionalProperties": False,
}


def _transcripcion_de(wav):
    """
    Lo que se dice en el video de ese .wav nivelado, o [].

    El .wav vive en "<x> - montaje/audio nivelado/C0031.wav" y su texto
    en "<x> - montaje/lo que se dice/C0031.<tamano>.json". Si hay mas de
    uno (el video se reemplazo), vale el mas nuevo.
    """
    wav = pathlib.Path(wav)
    carpeta = wav.parent.parent / "lo que se dice"
    candidatos = sorted(carpeta.glob(wav.stem + ".*.json"),
                        key=lambda r: r.stat().st_mtime, reverse=True)
    for archivo in candidatos:
        try:
            return json.loads(archivo.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
    return []


def lo_que_se_dice(linea):
    """
    [(segundo_en_la_linea, texto)] en orden, de la pista de audio 1.

    Una frase del reconocedor puede caer en dos clips seguidos (el corte
    la parte); se cuenta una sola vez, en el primero.
    """
    ritmo = float(linea.GetSetting("timelineFrameRate"))
    cero = linea.GetStartFrame()
    cache, salida, ya = {}, [], set()
    for item in linea.GetItemListInTrack("audio", 1) or []:
        clip = item.GetMediaPoolItem()
        if clip is None:
            continue
        ruta = clip.GetClipProperty("File Path") or ""
        if ruta not in cache:
            cache[ruta] = _transcripcion_de(ruta)
        desde = item.GetLeftOffset() / ritmo
        hasta = desde + item.GetDuration() / ritmo
        en = (item.GetStart() - cero) / ritmo
        for frase in cache[ruta]:
            if frase["fin"] <= desde or frase["inicio"] >= hasta:
                continue
            clave = (ruta, frase["inicio"])
            if clave in ya:
                continue
            ya.add(clave)
            salida.append((en + max(0.0, frase["inicio"] - desde),
                           frase["texto"]))
    return sorted(salida)


def proponer(linea):
    """Las secciones que propone la IA: [{titulo, segundo, por_que}]."""
    frases = lo_que_se_dice(linea)
    if not frases:
        consola.error("no encuentro lo que se dice en esta linea de tiempo "
                      "(las transcripciones las guarda el montaje).")
        return []
    # Los segundos van a secas, no en "m:ss": con "3:21.5" la IA a veces
    # devolvia 3,3 en vez de 201,5 y todos los titulos caian en el primer
    # minuto (paso el 02/10/2026).
    texto = "\n".join("[{:.0f}] {}".format(s, t) for s, t in frases)
    consola.detalle("Le paso a la IA {} frases para que proponga titulos..."
                    .format(len(frases)))
    respuesta = ia.preguntar(SISTEMA, texto, ESQUEMA, "secciones")
    return sorted(respuesta.get("secciones") or [],
                  key=lambda s: s["segundo"])


def elegir(secciones):
    """
    Muestra la lista y deja elegir. Devuelve las secciones aprobadas.

    Se contesta con numeros ("1,3,4"), "todos" o Enter para ninguno. Un
    titulo se cambia escribiendo "2=Otro titulo".
    """
    if not secciones:
        return []
    consola.detalle()
    for n, s in enumerate(secciones, start=1):
        consola.detalle("{:>2}. {:>7}  {}".format(
            n, consola.duracion(s["segundo"]), s["titulo"]))
        consola.detalle("              ({})".format(s["por_que"]))
    consola.detalle()
    consola.detalle("Cuales pongo? Numeros separados por coma, 'todos', o "
                    "Enter para ninguno.")
    consola.detalle("Para cambiar uno: 2=Otro titulo")
    while True:
        respuesta = consola.preguntar("      Titulos: ")
        if not respuesta:
            return []
        if "=" in respuesta:
            numero, nuevo = respuesta.split("=", 1)
            try:
                secciones[int(numero) - 1]["titulo"] = nuevo.strip()
                consola.hecho("cambiado. Ahora decime cuales pongo.")
            except (ValueError, IndexError):
                consola.alerta("no hay titulo numero {}".format(numero))
            continue
        if respuesta.lower() in ("todos", "todo", "t"):
            return secciones
        try:
            numeros = [int(x) for x in respuesta.replace(" ", "").split(",")
                       if x]
            return [secciones[n - 1] for n in numeros
                    if 1 <= n <= len(secciones)]
        except ValueError:
            consola.alerta("no entendi. Numeros con coma, 'todos', o Enter.")
