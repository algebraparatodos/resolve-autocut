# -*- coding: utf-8 -*-
"""
Ver y borrar lo que ocupa disco despues de terminar un video.

Editar video llena el disco en tres sitios distintos, y dos de ellos no
se ven desde ninguna parte:

  1. **Lo que genera este programa**, en la carpeta "<lo que sea> -
     montaje" que queda al lado de los crudos: los proxies, el audio
     nivelado y las transcripciones.
  2. **La cache de Resolve**, donde van las copias optimizadas y el
     render cache. Vive donde diga el propio Resolve y crece con cada
     proyecto sin que nadie la vacie nunca. Medido en una maquina de
     trabajo normal: 78 GB.
  3. **Los archivos originales**, que son de quien los grabo y este
     programa no toca jamas.

Nada se borra sin que la persona lo diga escribiendolo. Y se avisa de lo
que va a costar: los proxies se vuelven a generar solos, pero tardan.
"""

import pathlib
import shutil
import sys

from . import consola, interprete


def _pesa(carpeta):
    """Cuanto ocupa una carpeta entera, en bytes."""
    carpeta = pathlib.Path(carpeta)
    if not carpeta.exists():
        return 0
    total = 0
    for hijo in carpeta.rglob("*"):
        try:
            if hijo.is_file():
                total += hijo.stat().st_size
        except OSError:
            continue
    return total


def en_gb(bytes_):
    return bytes_ / (1024.0 ** 3)


def cache_de_resolve():
    """
    Donde guarda Resolve sus copias optimizadas y su render cache.

    Se le pregunta a Resolve en vez de suponerlo, porque es un ajuste que
    cada uno pone donde quiere y adivinarlo mal significaria no limpiar
    nada o, peor, borrar la carpeta equivocada.
    """
    if interprete.preparar_entorno() is None:
        return None
    try:
        import DaVinciResolveScript as motor
    except Exception:
        return None

    resolve = motor.scriptapp("Resolve")
    if resolve is None:
        return None

    gestor = resolve.GetProjectManager()
    proyecto = gestor.GetCurrentProject() if gestor else None
    if proyecto is None:
        return None

    ruta = (proyecto.GetSetting() or {}).get("perfCacheClipsLocation")
    return pathlib.Path(ruta) if ruta else None


def carpetas_de_montaje(desde):
    """
    Las carpetas de trabajo que genero el programa.

    Con una carpeta concreta se busca la suya; sin nada, se buscan todas
    las que haya al lado del programa.
    """
    if desde:
        origen = pathlib.Path(desde)
        base = origen if origen.is_dir() else origen.parent
        propia = base.parent / (base.name + " - montaje")
        return [propia] if propia.exists() else []

    raiz = pathlib.Path(__file__).resolve().parent.parent
    return sorted(p for p in raiz.parent.rglob("* - montaje") if p.is_dir())


def inventario(carpetas):
    """Que hay y cuanto pesa, partido por tipo."""
    filas = []
    for carpeta in carpetas:
        for nombre, que in (("proxies", "copias livianas para reproducir"),
                            ("audio nivelado", "pistas de audio corregidas"),
                            ("lo que se dice", "transcripciones")):
            sitio = carpeta / nombre
            if sitio.exists():
                filas.append((sitio, que, _pesa(sitio)))
    return filas


def _preguntar(texto):
    try:
        return input(texto).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return ""


def _borrar(sitio):
    try:
        shutil.rmtree(sitio)
        return True
    except OSError as fallo:
        consola.error("no pude borrar {} ({})".format(sitio.name, fallo))
        return False


def main(argumentos=None):
    argumentos = list(sys.argv[1:] if argumentos is None else argumentos)
    consola.titulo("Limpiar lo que ocupa disco")

    desde = argumentos[0] if argumentos else None
    filas = inventario(carpetas_de_montaje(desde))

    consola.detalle("Lo que genero el programa:")
    if not filas:
        consola.detalle("   nada, esta todo limpio")
    for sitio, que, peso in filas:
        consola.detalle("   {:>8.2f} GB  {:22} ({})"
                        .format(en_gb(peso), sitio.name, que))
    del_programa = sum(p for _, _, p in filas)

    cache = cache_de_resolve()
    peso_cache = _pesa(cache) if cache else 0
    consola.detalle()
    consola.detalle("La cache de Resolve:")
    if cache is None:
        consola.detalle("   no pude preguntarle a Resolve donde la tiene.")
        consola.detalle("   Abrilo con un proyecto y volve a pasar esto.")
    else:
        consola.detalle("   {:>8.2f} GB  {}".format(en_gb(peso_cache), cache))
        consola.detalle("   Son las copias optimizadas y el render cache de")
        consola.detalle("   TODOS tus proyectos, no solo del ultimo.")

    consola.detalle()
    consola.detalle("En total se pueden recuperar {:.1f} GB."
                    .format(en_gb(del_programa + peso_cache)))

    if not (del_programa or peso_cache):
        return 0

    consola.detalle()
    consola.detalle("Que borro:")
    consola.detalle("   1  solo los proxies (se regeneran solos, pero tardan)")
    consola.detalle("   2  todo lo del programa")
    consola.detalle("   3  todo lo del programa y la cache de Resolve")
    consola.detalle("   0  nada")
    consola.detalle()

    elegido = _preguntar("      Elegi: ")
    if elegido not in ("1", "2", "3"):
        consola.detalle("No toco nada.")
        return 0

    objetivos = [s for s, _, _ in filas
                 if elegido != "1" or s.name == "proxies"]
    if elegido == "3" and cache and cache.exists():
        objetivos.append(cache)

    consola.detalle()
    consola.detalle("Voy a borrar:")
    for sitio in objetivos:
        consola.detalle("   " + str(sitio))
    consola.detalle()
    consola.alerta("Esto no se puede deshacer.")

    if _preguntar('      Escribi "borrar" para confirmar: ') != "borrar":
        consola.detalle("No toco nada.")
        return 0

    consola.detalle()
    liberado = 0
    for sitio in objetivos:
        peso = _pesa(sitio)
        if _borrar(sitio):
            liberado += peso
            consola.hecho("{:.2f} GB  {}".format(en_gb(peso), sitio.name))

    # La cache tiene que seguir existiendo o Resolve se queja al escribir
    # la proxima. Se borra el contenido, no el sitio.
    if cache and cache in objetivos:
        cache.mkdir(parents=True, exist_ok=True)

    consola.detalle()
    consola.detalle("Liberados {:.1f} GB.".format(en_gb(liberado)))
    consola.detalle()
    consola.alerta("Si Resolve tiene abierto un proyecto que usaba estos")
    consola.alerta("archivos, Windows no devuelve el espacio hasta que lo")
    consola.alerta("cierres. Cerra el proyecto y mira de nuevo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
