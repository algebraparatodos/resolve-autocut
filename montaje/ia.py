# -*- coding: utf-8 -*-
"""
Preguntarle a OpenAI, para entender las ordenes que Juani escribe.

La IA no toca Resolve ni archivos: solo traduce lo que Juani escribe a
una de las acciones que el programa sabe hacer, con sus datos. Lo que
pasa despues lo hace el programa, con las mismas comprobaciones de
siempre. Asi una orden mal entendida termina, como mucho, en una accion
equivocada que se ve en pantalla, nunca en algo que nadie pidio.

Va con gpt-6-luna, el modelo barato que usan todos los proyectos de
Juani, y sin librerias: una llamada HTTP a la API de respuestas, igual
que en espacio-bogota. La clave es la de J-DEV (OPENAI_API_KEY_JDEV), por
decision de Juani del 02/10/2026; se puede pisar con una propia en
edicion-de-videos/.claves.env.
"""

import json
import os
import pathlib
import urllib.error
import urllib.request

MODELO = "gpt-6-luna"
CLAVES = ("OPENAI_API_KEY_EDICION", "OPENAI_API_KEY_JDEV")

PROYECTO = pathlib.Path(__file__).resolve().parent.parent
# Las claves de Juani viven en Desarrollos\Gestion\.claves.env, y esta
# herramienta vive en Desarrollos\herramientas\edicion-de-videos.
RAIZ = PROYECTO.parent.parent / "Gestion"


class SinIA(Exception):
    """No hay clave, no hay red, o OpenAI contesto algo que no sirve."""


def _leer_claves():
    """Los .claves.env de la raiz y del proyecto; el del proyecto pisa."""
    valores = {}
    for archivo in (RAIZ / ".claves.env", PROYECTO / ".claves.env"):
        if not archivo.exists():
            continue
        for linea in archivo.read_text(encoding="utf-8",
                                       errors="replace").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            nombre, valor = linea.split("=", 1)
            valores[nombre.strip()] = valor.strip().strip('"').strip("'")
    return valores


def clave():
    """La clave a usar: primero el entorno, despues los .claves.env."""
    archivo = _leer_claves()
    for nombre in CLAVES:
        valor = os.environ.get(nombre) or archivo.get(nombre)
        if valor:
            return valor
    raise SinIA("no encuentro la clave de OpenAI ({}) en .claves.env"
                .format(" ni ".join(CLAVES)))


def preguntar(sistema, usuario, esquema, nombre_esquema="respuesta"):
    """
    Le pregunta al modelo y devuelve su respuesta ya convertida a dict.

    'esquema' es un JSON Schema en modo estricto: todos los campos en
    'required' y 'additionalProperties' en false. OpenAI garantiza que la
    respuesta cumple el esquema, asi que no hace falta adivinar que quiso
    decir.
    """
    cuerpo = {
        "model": MODELO,
        # Lo fijo primero y lo variable al final: OpenAI cachea solo el
        # principio que se repite, y lo cacheado cuesta la decima parte.
        "input": [{"role": "system", "content": sistema},
                  {"role": "user", "content": usuario}],
        "text": {"format": {"type": "json_schema", "name": nombre_esquema,
                            "schema": esquema, "strict": True}},
        "reasoning": {"effort": "low"},
        "max_output_tokens": 4000,
    }
    pedido = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Authorization": "Bearer " + clave(),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=120) as r:
            respuesta = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as fallo:
        detalle = fallo.read().decode("utf-8", "replace")[:300]
        raise SinIA("OpenAI contesto {}: {}".format(fallo.code, detalle))
    except (urllib.error.URLError, OSError, ValueError) as fallo:
        raise SinIA("no pude hablar con OpenAI: {}".format(fallo))

    for salida in respuesta.get("output") or []:
        for parte in salida.get("content") or []:
            if parte.get("type") == "output_text" and parte.get("text"):
                try:
                    return json.loads(parte["text"])
                except ValueError:
                    raise SinIA("OpenAI contesto algo que no es JSON")
    raise SinIA("OpenAI no contesto nada (estado: {})"
                .format(respuesta.get("status")))
