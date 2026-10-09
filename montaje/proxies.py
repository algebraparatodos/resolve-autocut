# -*- coding: utf-8 -*-
"""
Copias livianas para que Resolve reproduzca sin arrastrarse.

Por que se generan aca y no se le piden a Resolve: la API no tiene nada
equivalente a 'Generate Optimized Media'. Lo unico que expone es
'LinkProxyMedia(ruta)', que engancha un archivo que ya existe, mas
'LinkFullResolutionMedia' y 'UnlinkProxyMedia'. Comprobado contra el SDK
de Resolve 21. Asi que en vez de devolver un paso a mano, el programa
genera el archivo el mismo y despues lo engancha.

El formato por defecto es DNxHR LB, que es lo que quiere Resolve para
esto. Pesa mas que un H.264 del mismo tamano, pero cada cuadro se
descomprime solo, sin depender de los vecinos, y eso es exactamente lo
que hace que arrastrar la cabeza por la linea de tiempo vaya suave. Un
H.264 liviano ocupa poco y se reproduce peor, que es el negocio al
reves.

Un proxy que no coincide en ritmo, duracion Y CODIGO DE TIEMPO con su
original Resolve lo rechaza sin decir nada, asi que aca no se recorta,
no se cambia el ritmo y se le copia el codigo de tiempo de arranque: lo
unico que cambia es el tamano del cuadro. Lo del codigo de tiempo costo
un montaje entero: ffmpeg no lo copia solo, las copias arrancaban en
00:00:00:00, y Resolve rechazo las once (02/10/2026).

El audio del proxy va comprimido y da igual como suene, porque el sonido
del montaje no sale de aca: sale del .wav nivelado que se monta aparte.
Se le deja una pista igualmente, porque un proxy sin audio donde el
original si tiene es de las cosas que Resolve rechaza sin explicar.
"""

import pathlib

from . import consola, herramientas


def _tamano_del_proxy(datos, alto_pedido):
    """
    Cuanto mide el proxy, conservando la forma del original.

    Las dos medidas se redondean a numero par porque los codecs de video
    trabajan en bloques y uno impar hace fallar la codificacion con un
    error que no menciona el tamano.
    """
    ancho, alto = datos.get("ancho") or 0, datos.get("alto") or 0
    if not ancho or not alto:
        return None

    if alto <= alto_pedido:
        return None  # ya es mas chico que el proxy: no vale la pena

    nuevo_alto = int(alto_pedido)
    nuevo_ancho = int(round(ancho * nuevo_alto / float(alto)))
    return (nuevo_ancho - nuevo_ancho % 2, nuevo_alto - nuevo_alto % 2)


# Los dos formatos que sirven para esto, en orden. ProRes Proxy va de
# reserva porque el codificador DNxHR de ffmpeg a veces se planta en un
# video concreto ("Assertion s->buf_ptr < s->buf_end failed", le paso a
# un clip de 15 minutos) y reintentar con lo mismo da el mismo error.
# Los dos se descomprimen cuadro por cuadro, que es lo que importa.
FORMATOS = [
    ["-c:v", "dnxhd", "-profile:v", "dnxhr_lb", "-pix_fmt", "yuv422p"],
    ["-c:v", "prores_ks", "-profile:v", "0", "-pix_fmt", "yuv422p10le"],
]


def generar(origen, destino, datos, ajustes):
    """Escribe el proxy. Devuelve (salio_bien, motivo_si_no)."""
    medida = _tamano_del_proxy(datos, ajustes["alto"])
    if medida is None:
        return False, "el original ya es chico"

    destino = pathlib.Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    motivo = "ffmpeg no pudo"
    for formato in FORMATOS:
        orden = [herramientas.FFMPEG, "-nostdin", "-hide_banner", "-y",
                 "-i", str(origen),
                 "-map", "0:v:0", "-map", "0:a:0?",
                 "-vf", "scale={}:{}".format(*medida)]
        orden += formato
        orden += ["-c:a", "aac", "-b:a", "128k"]
        if datos.get("timecode"):
            orden += ["-timecode", datos["timecode"]]
        orden.append(str(destino))

        salida = herramientas.correr(orden)
        if salida.returncode == 0 and destino.exists():
            return True, ""
        # Lo que quedo a medias no puede quedar con el nombre del bueno:
        # la proxima corrida lo daria por hecho y lo reutilizaria.
        if destino.exists():
            destino.unlink()
        ultimo = (salida.stderr or "").strip().splitlines()[-1:]
        motivo = ultimo[0] if ultimo else motivo
    return False, motivo


def preparar(origen, carpeta_destino, datos, ajustes):
    """
    Deja el proxy listo y devuelve su ruta, o None si no hizo falta.

    Si ya existe uno de antes se reutiliza: generar proxies es lo que
    mas tarda de todo el montaje y rehacerlos en cada corrida seria
    castigar al que vuelve a pasar la misma carpeta.
    """
    # '_tc' marca los que ya llevan el codigo de tiempo: los '_proxy.mov'
    # de antes del 02/10/2026 no lo tienen, Resolve los rechaza, y con el
    # mismo nombre se reutilizarian para siempre.
    nombre = pathlib.Path(origen).stem + "_proxy_tc.mov"
    destino = pathlib.Path(carpeta_destino) / nombre

    if destino.exists() and destino.stat().st_size > 0:
        consola.hecho("{}: ya tenia proxy".format(pathlib.Path(origen).name))
        return destino

    salio, motivo = generar(origen, destino, datos, ajustes)
    if not salio:
        consola.alerta("sin proxy para {} ({})"
                       .format(pathlib.Path(origen).name, motivo))
        return None

    peso = destino.stat().st_size / (1024.0 * 1024.0)
    consola.hecho("{}: proxy de {} px de alto, {:.0f} MB"
                  .format(pathlib.Path(origen).name, ajustes["alto"], peso))
    return destino
