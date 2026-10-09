# -*- coding: utf-8 -*-
"""
Exportar el video terminado, cuando Juani lo pide.

Hasta el 02/10/2026 el programa no exportaba nunca, a proposito: entrega
una linea de tiempo para seguir trabajando. Ese dia Juani pidio poder
ordenarlo al final. Sigue sin exportar solo: solo cuando se lo piden, y
preguntando antes.

Formato elegido por Juani: MP4 H.264 al tamano y ritmo de la linea de
tiempo, con el nombre del proyecto y la fecha, en Desktop\\Edicion\\
exportados. Si la placa NVIDIA esta, se usa su codificador, que en un
video de un cuarto de hora va mucho mas rapido; si no, el comun.
"""

import datetime
import pathlib
import time

from . import consola

CARPETA = pathlib.Path.home() / "Desktop" / "Edicion" / "exportados"


def exportar(proyecto):
    """Exporta la linea de tiempo abierta. True si termino bien."""
    linea = proyecto.GetCurrentTimeline()
    CARPETA.mkdir(parents=True, exist_ok=True)
    nombre = "{} - {}".format(proyecto.GetName(),
                              datetime.datetime.now().strftime("%Y-%m-%d %H%M"))
    ancho = int(linea.GetSetting("timelineResolutionWidth"))
    alto = int(linea.GetSetting("timelineResolutionHeight"))

    respuesta = consola.preguntar(
        '      Exporto "{}" ({}x{}) a {}? (s/n) '.format(
            linea.GetName(), ancho, alto, CARPETA))
    if respuesta.lower() not in ("s", "si", "sí", "y", "dale"):
        consola.detalle("No exporto.")
        return True

    codecs = proyecto.GetRenderCodecs("mp4") or {}
    codec = "H264_NVIDIA" if "H264_NVIDIA" in codecs.values() else "H264"
    if not proyecto.SetCurrentRenderFormatAndCodec("mp4", codec):
        consola.error("Resolve no acepto MP4 {}.".format(codec))
        return False
    if not proyecto.SetRenderSettings({
            "SelectAllFrames": True, "TargetDir": str(CARPETA),
            "CustomName": nombre, "ExportVideo": True, "ExportAudio": True,
            "FormatWidth": ancho, "FormatHeight": alto}):
        consola.error("Resolve no acepto los ajustes de exportacion.")
        return False

    trabajo = proyecto.AddRenderJob()
    if not trabajo or not proyecto.StartRendering([trabajo], False):
        consola.error("Resolve no arranco la exportacion.")
        return False

    consola.paso_suelto("Exporto ({})".format(codec.replace("_", " ")))
    ultimo = -1
    try:
        while proyecto.IsRenderingInProgress():
            estado = proyecto.GetRenderJobStatus(trabajo) or {}
            avance = int(estado.get("CompletionPercentage") or 0)
            if avance >= ultimo + 10:
                falta = (estado.get("EstimatedTimeRemainingInMs") or 0) / 1000
                consola.detalle("{:>3} %{}".format(avance, (
                    "   (faltan unos {})".format(consola.duracion(falta))
                    if falta else "")))
                ultimo = avance
            time.sleep(2)
        estado = proyecto.GetRenderJobStatus(trabajo) or {}
    finally:
        proyecto.DeleteRenderJob(trabajo)

    archivo = CARPETA / (nombre + ".mp4")
    if estado.get("JobStatus") != "Complete" or not archivo.exists():
        consola.error("la exportacion no termino bien ({}).".format(
            estado.get("JobStatus")))
        return False
    consola.hecho("exportado: {} ({:.0f} MB)".format(
        archivo, archivo.stat().st_size / 1048576.0))
    return True
