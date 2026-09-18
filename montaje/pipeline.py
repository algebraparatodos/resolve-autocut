# -*- coding: utf-8 -*-
"""
La cadena entera, de una carpeta de crudos a una linea de tiempo.

El orden de los pasos no es casual y conviene no tocarlo sin leer esto:

  1. **Sondear** el material, para saber que forma tiene.
  2. **Configurar el proyecto** (lienzo y ritmo) ANTES de generar nada.
     Cambiar la resolucion despues invalida los proxies y las copias
     optimizadas que ya existan, y quien acaba de esperar un rato largo
     generandolas se queda sin ellas sin que nadie se lo diga.
  3. **Nivelar el audio**, que reescribe los archivos.
  4. **Generar los proxies**, que salen de los archivos ya nivelados.
  5. **Importar** y engancharle a cada clip su proxy.
  6. **Detectar la voz** y calcular los cortes.
  7. **Armar y medir**, porque la API acepta cosas que despues no hace.
  8. **Marcar las repetidas**, que es lo ultimo porque necesita saber
     que clips quedaron de verdad.
"""

import pathlib

from . import audio, consola, herramientas, proxies, repeticiones
from .resolve import conexion, linea, medios
from .resolve import proyecto as ajustes_proyecto
from .voz import deteccion

PASOS = 8


class Resultado(object):
    """Lo que paso, para poder contarlo al final."""

    def __init__(self):
        self.videos = []
        self.tramos = 0
        self.grupos = 0
        self.segundos_crudos = 0.0
        self.segundos_montados = 0.0
        self.avisos = []
        self.nombre_timeline = ""

    @property
    def porcentaje_conservado(self):
        if not self.segundos_crudos:
            return 0.0
        return 100.0 * self.segundos_montados / self.segundos_crudos


def carpeta_de_trabajo(origen):
    """
    Donde van los archivos que genera el programa.

    Al lado de los crudos y no adentro: asi la carpeta que se paso sigue
    teniendo solo lo que se grabo, y volver a arrastrarla no toma por
    material los archivos que hizo el programa.
    """
    origen = pathlib.Path(origen)
    base = origen if origen.is_dir() else origen.parent
    trabajo = base.parent / (base.name + " - montaje")
    trabajo.mkdir(parents=True, exist_ok=True)
    return trabajo


def montar(carpeta, ajustes):
    """Hace todo. Devuelve un Resultado, o None si no se pudo empezar."""
    resultado = Resultado()

    if not herramientas.estan_instaladas():
        consola.error("no encuentro ffmpeg. Se instala con:")
        consola.detalle("winget install Gyan.FFmpeg")
        return None

    videos = herramientas.videos_de(carpeta)
    if not videos:
        consola.error("no hay ningun video en esa carpeta.")
        return None

    origen = pathlib.Path(carpeta)
    nombre = origen.name if origen.is_dir() else origen.stem

    # El orden importa: primero se engancha (abriendo Resolve si no
    # estaba), despues se asegura un proyecto, y recien entonces se
    # comprueba que no haya ventanas encima. Recien abierto, Resolve
    # muestra el gestor de proyectos, que cuenta como ventana encima;
    # crear o cargar el proyecto es justamente lo que la cierra.
    try:
        resolve = conexion.conectar()
        abierto, _ = conexion.asegurar_proyecto(resolve, nombre)
        conexion.comprobar_que_deja_trabajar(resolve)
    except conexion.NoHayResolve as fallo:
        consola.error(str(fallo))
        return None

    trabajo = carpeta_de_trabajo(carpeta)

    # --- 1. Que hay en la carpeta ------------------------------------
    consola.paso(1, PASOS, "Miro el material")
    datos = {}
    for ruta in videos:
        info = herramientas.datos_del_video(ruta)
        if info is None or not info["tiene_audio"]:
            consola.alerta("{} no tiene audio que pueda leer, lo dejo fuera"
                           .format(ruta.name))
            continue
        datos[ruta] = info
        resultado.segundos_crudos += info["largo"]
        consola.detalle("{}  {}  {}x{}  {:g} fps"
                        .format(ruta.name, consola.duracion(info["largo"]),
                                info["ancho"], info["alto"],
                                info["ritmo"] or 0))

    if not datos:
        consola.error("ninguno de los videos sirve.")
        return None

    # --- 2. El proyecto, antes de generar nada -----------------------
    consola.paso(2, PASOS, "Configuro el proyecto")
    lienzo, quejas = ajustes_proyecto.lienzo_del_material(list(datos.values()))
    ritmo, otras = ajustes_proyecto.ritmo_del_material(list(datos.values()))
    resultado.avisos.extend(quejas + otras)

    if ajustes["proyecto"]["ritmo"]:
        ritmo = ajustes["proyecto"]["ritmo"]

    # Si el proyecto tiene el ritmo trabado en otro que el del material,
    # no se monta aca: se hace uno nuevo. Montar igual dejaria la linea
    # de tiempo entregando cuadros a un ritmo mientras el reproductor los
    # pide a otro, y el video se ve acelerado. Como eso no se puede
    # arreglar despues, hay que evitarlo antes.
    if ajustes_proyecto.necesita_proyecto_nuevo(abierto, ritmo):
        viejo = abierto.GetName()
        try:
            abierto = conexion.crear_aparte(resolve, nombre)
        except conexion.NoHayResolve as fallo:
            consola.error(str(fallo))
            return None
        consola.alerta('el proyecto "{}" tiene el ritmo trabado en otro '
                       'que el de tu material'.format(viejo))
        consola.hecho('monto en un proyecto nuevo: "{}"'
                      .format(abierto.GetName()))
        resultado.avisos.append(
            'no monte en "{}" porque ya tenia lineas de tiempo y Resolve '
            'no deja cambiarle el ritmo; hice "{}"'
            .format(viejo, abierto.GetName()))

    if lienzo:
        resultado.avisos.extend(
            ajustes_proyecto.configurar(abierto, lienzo, ritmo))

    # --- 3. El audio, parejo -----------------------------------------
    #
    # Se escribe SOLO la pista de audio, no una copia del video. Copiar
    # el video para cambiarle el nivel duplica la carpeta entera en
    # disco: en un material de 23 GB son 22 GB tirados para tocar 90 MB
    # de sonido. El video sale del original y el audio de este .wav, y se
    # juntan recien en la linea de tiempo.
    consola.paso(3, PASOS, "Nivelo el audio a {:g} LUFS"
                 .format(ajustes["audio"]["objetivo_lufs"]))
    pistas = {}
    for ruta in datos:
        pistas[ruta] = audio.preparar(ruta, trabajo / "audio nivelado",
                                      ajustes["audio"])[0]

    # --- 4. Las copias livianas --------------------------------------
    consola.paso(4, PASOS, "Genero las copias livianas para reproducir")
    hechos = {}
    for ruta in datos:
        proxy = proxies.preparar(ruta, trabajo / "proxies",
                                 datos[ruta], ajustes["proxies"])
        if proxy:
            hechos[ruta] = proxy

    # --- 5. Adentro de Resolve ---------------------------------------
    consola.paso(5, PASOS, "Meto los clips en Resolve")
    preparado = medios.preparar(
        resolve, [{"video": r, "audio": pistas.get(r), "proxy": hechos.get(r)}
                  for r in datos])
    if preparado is None:
        consola.error("perdi el proyecto de Resolve por el camino.")
        return None

    _, pool, clips = preparado
    if not clips:
        consola.error("Resolve no acepto ninguno de los videos.")
        return None
    consola.hecho("{} clip(s) listos".format(len(clips)))

    # --- 6. Donde se habla -------------------------------------------
    consola.paso(6, PASOS, "Busco donde hablas y corto el resto")
    pedido, pedido_audio, por_video = [], [], []

    for clip in clips:
        original = clip["ruta"]
        largo = datos[original]["largo"]

        # Se escucha el .wav y no el video: es el mismo sonido ya
        # nivelado, y leerlo es mucho mas rapido que abrir el video.
        donde_escuchar = pistas.get(original) or original

        tramos = deteccion.tramos_con_voz(donde_escuchar,
                                          ajustes["silencios"], largo)
        if tramos is None:
            consola.alerta("sin detector de voz no puedo cortar {}: "
                           "lo pongo entero".format(original.name))
            tramos = [[0.0, largo]]

        cortes = linea.a_cuadros(tramos, clip["ritmo"], clip["cuadros"])
        hablado = sum(f - i for i, f in tramos)
        resultado.segundos_montados += hablado
        resultado.videos.append((original.name, largo, hablado, len(cortes)))

        consola.hecho("{}: {} tramos, queda {} de {}"
                      .format(original.name, len(cortes),
                              consola.duracion(hablado),
                              consola.duracion(largo)))

        por_video.append({"original": original, "ruta": donde_escuchar,
                          "tramos": tramos, "desde": len(pedido)})

        # Con pista de audio aparte hay que decir que de cada clip se
        # toma solo la imagen (1) o solo el sonido (2). Sin ella, el clip
        # entra completo y no se manda 'mediaType'.
        if clip["pista"] is not None:
            pedido.extend({"mediaPoolItem": clip["clip"], "mediaType": 1,
                           "startFrame": a, "endFrame": b} for a, b in cortes)
            pedido_audio.extend({"mediaPoolItem": clip["pista"],
                                 "mediaType": 2,
                                 "startFrame": a, "endFrame": b}
                                for a, b in cortes)
        else:
            pedido.extend({"mediaPoolItem": clip["clip"],
                           "startFrame": a, "endFrame": b} for a, b in cortes)

    resultado.tramos = len(pedido)
    if not pedido:
        consola.error("no encontre a nadie hablando en ningun video.")
        return None

    # --- 7. Armar y medir --------------------------------------------
    consola.paso(7, PASOS, "Armo la linea de tiempo")
    la_linea, _ = linea.armar(abierto, pool, pedido, pedido_audio,
                              "{} - montado".format(nombre))
    if la_linea is None:
        return None

    resultado.nombre_timeline = la_linea.GetName()

    # Se mide siempre despues de armar: la API acepta cosas que despues
    # no hace, y contar los clips de todas las pistas es lo unico que
    # delata que una operacion se llevo algo por delante.
    conteo = linea.medir(la_linea)
    en_video = sum(c for (tipo, _), c in conteo.items() if tipo == "video")
    if en_video != len(pedido):
        resultado.avisos.append(
            "pedi {} tramos y en la linea de tiempo hay {}"
            .format(len(pedido), en_video))

    corridos = linea.desalineados(la_linea)
    if corridos == -1:
        resultado.avisos.append(
            "la pista de video y la de audio quedaron con distinta "
            "cantidad de clips: revisa la sincronia antes de editar")
    elif corridos:
        resultado.avisos.append(
            "{} tramos quedaron con la imagen y el sonido corridos"
            .format(corridos))
    elif pedido_audio:
        consola.hecho("imagen y sonido alineados al cuadro en los {} tramos"
                      .format(en_video))

    # --- 8. Las repetidas, marcadas ----------------------------------
    consola.paso(8, PASOS, "Marco las frases repetidas")
    items = la_linea.GetItemListInTrack("video", 1) or []
    grupos_globales = []

    for video in por_video:
        # Se escucha el .wav, que se lee rapido, pero lo escuchado se
        # guarda a nombre del video original, que es lo unico que no
        # cambia si se vuelve a generar el audio.
        frases = deteccion.frases(video["ruta"], trabajo / "lo que se dice",
                                  clave=video["original"])
        if not frases:
            continue
        grupos, _ = repeticiones.buscar(video["tramos"], frases,
                                        ajustes["repeticiones"])
        for grupo in grupos:
            grupos_globales.append([video["desde"] + i for i in grupo])

    if grupos_globales:
        marcados = linea.marcar_grupos(items, grupos_globales)
        resultado.grupos = len(grupos_globales)
        consola.hecho("{} frase(s) dichas mas de una vez, {} clips "
                      "pintados. No saque ninguna: elegis vos."
                      .format(len(grupos_globales), marcados))
    else:
        consola.hecho("no encontre frases repetidas.")

    conexion.soltar(resolve)
    return resultado
