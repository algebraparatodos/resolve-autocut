# -*- coding: utf-8 -*-
"""
ffmpeg y ffprobe: donde estan y como se les pregunta por un archivo.

Todo lo que sabe el programa sobre el material crudo sale de aca. Lo que
NO sale de aca es el ritmo con el que se calculan los cortes: ese lo
dice Resolve, porque un .MOV marcado como 59,94 puede ser 60 exacto para
Resolve, y los numeros de cuadro se los damos nosotros a el.
"""

import json
import pathlib
import shutil
import subprocess


EXTENSIONES = {".mp4", ".mov", ".mkv", ".avi", ".mxf", ".m4v", ".mts", ".wmv"}


def _buscar(programa):
    """
    ffmpeg puede no estar en el PATH segun como se abrio la consola, asi
    que si no aparece se mira donde lo deja winget.
    """
    encontrado = shutil.which(programa)
    if encontrado:
        return encontrado
    patron = (pathlib.Path.home() / "AppData" / "Local" / "Microsoft"
              / "WinGet" / "Packages")
    for ruta in patron.glob("Gyan.FFmpeg*/**/bin/" + programa + ".exe"):
        return str(ruta)
    return None


FFMPEG = _buscar("ffmpeg")
FFPROBE = _buscar("ffprobe")


def estan_instaladas():
    return FFMPEG is not None and FFPROBE is not None


def correr(orden):
    """
    Lanza un programa y devuelve el resultado, sin abrir una ventana.

    'nostdin' es importante: sin eso, ffmpeg se queda esperando una
    tecla si cree que va a sobrescribir algo, y el programa se cuelga
    sin decir por que.
    """
    return subprocess.run(orden, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def videos_de(carpeta):
    """
    Los videos de una carpeta, en orden alfabetico.

    El orden importa y no es un detalle: es el orden en el que van a
    quedar en la linea de tiempo. Grabando por tomas numeradas, el orden
    del nombre es el orden del relato.
    """
    carpeta = pathlib.Path(carpeta)
    if carpeta.is_file():
        return [carpeta] if carpeta.suffix.lower() in EXTENSIONES else []
    return sorted(
        (r for r in carpeta.iterdir()
         if r.is_file() and r.suffix.lower() in EXTENSIONES),
        key=lambda r: r.name.lower())


def datos_del_video(ruta):
    """
    Ritmo, duracion, tamano en pantalla y si tiene audio.

    El ritmo se pide como fraccion y no como decimal a proposito: los
    videos de camara suelen venir a 30000/1001, que es 29,97 con
    decimales infinitos. Redondeandolo, en un video de una hora el error
    acumulado corre los cortes casi cuatro segundos.

    El tamano se devuelve YA GIRADO. ffprobe informa el cuadro antes de
    aplicar la rotacion, asi que un video grabado en vertical dice medir
    1920x1080 y hay que mirar aparte el dato de rotacion. Preguntarlo mal
    lleva a configurar el lienzo al reves.
    """
    salida = correr([FFPROBE, "-v", "error", "-print_format", "json",
                     "-show_streams", "-show_format", str(ruta)])
    if salida.returncode != 0:
        return None

    try:
        info = json.loads(salida.stdout)
    except ValueError:
        return None

    pistas = info.get("streams", [])
    video = next((p for p in pistas if p.get("codec_type") == "video"), None)
    audio = next((p for p in pistas if p.get("codec_type") == "audio"), None)

    ritmo = None
    ancho = alto = 0
    if video is not None:
        fraccion = video.get("r_frame_rate") or ""
        if "/" in fraccion:
            arriba, abajo = fraccion.split("/", 1)
            try:
                arriba, abajo = float(arriba), float(abajo)
                if abajo:
                    ritmo = arriba / abajo
            except ValueError:
                ritmo = None

        ancho = int(video.get("width") or 0)
        alto = int(video.get("height") or 0)
        if _esta_girado(video):
            ancho, alto = alto, ancho

    try:
        largo = float(info.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        largo = 0.0

    return {"ritmo": ritmo, "largo": largo, "ancho": ancho, "alto": alto,
            "tiene_video": video is not None, "tiene_audio": audio is not None}


def _esta_girado(pista):
    """
    Si la pista viene marcada para girar un cuarto de vuelta.

    La rotacion aparece en dos sitios segun la version de ffprobe y
    segun como se grabo: en los metadatos de la pista o en los datos
    laterales de la matriz de pantalla. Hay que mirar los dos.
    """
    valores = []
    etiquetas = pista.get("tags") or {}
    if "rotate" in etiquetas:
        valores.append(etiquetas["rotate"])
    for lateral in pista.get("side_data_list") or []:
        if "rotation" in lateral:
            valores.append(lateral["rotation"])

    for valor in valores:
        try:
            grados = abs(int(float(valor))) % 180
        except (TypeError, ValueError):
            continue
        if grados == 90:
            return True
    return False
