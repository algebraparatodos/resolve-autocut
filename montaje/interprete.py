# -*- coding: utf-8 -*-
"""
Conseguir un Python capaz de hablar con DaVinci Resolve.

Hacen falta dos Python distintos y no pueden ser el mismo, que es la
parte que desconcierta:

  * La libreria de Resolve ('fusionscript.dll') solo la puede abrir un
    Python instalado de verdad. El de Microsoft Store, que es el que
    Windows ofrece cuando uno escribe 'python' sin tenerlo, corre en un
    cajon aislado que le prohibe cargar librerias de fuera. El error que
    tira no menciona nada de eso:

        SystemError: initialization of fusionscript failed without
        raising an exception

  * El detector de voz vive en un entorno virtual aparte, hecho sobre
    otro Python. Ese se llama como un proceso separado (ver 'montaje.voz')
    y no hace falta que sea este.

Lo que hace este modulo es comprobar si el Python que esta corriendo
sirve para lo primero y, si no sirve, volver a lanzar el programa con
uno que si. El usuario no se entera de nada.
"""

import os
import pathlib
import subprocess
import sys

from . import consola

# Bandera para no llamarse a si mismo para siempre si el relanzado
# tampoco puede cargar la libreria.
_YA_CAMBIE = "MONTAJE_YA_CAMBIE_PYTHON"


def preparar_entorno():
    """
    Deja puestas las tres variables que pide el modulo de Blackmagic.

    Se hacen aca y no en el .bat para que el programa funcione igual
    corriendolo a mano, desde el editor o con doble clic. Devuelve la
    carpeta del SDK, o None si Resolve no esta instalado.
    """
    programa = pathlib.Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    api = (programa / "Blackmagic Design" / "DaVinci Resolve" / "Support"
           / "Developer" / "Scripting")
    libreria = pathlib.Path(r"C:\Program Files\Blackmagic Design"
                            r"\DaVinci Resolve\fusionscript.dll")

    if not api.exists() or not libreria.exists():
        return None

    os.environ["RESOLVE_SCRIPT_API"] = str(api)
    os.environ["RESOLVE_SCRIPT_LIB"] = str(libreria)
    modulos = str(api / "Modules")
    if modulos not in sys.path:
        sys.path.insert(0, modulos)
    return api


def puede_cargar_resolve():
    """Prueba si ESTE Python puede abrir la libreria de Resolve."""
    if preparar_entorno() is None:
        return False
    try:
        import DaVinciResolveScript  # noqa: F401
        return True
    except Exception:
        return False


def candidatos():
    """
    Otros Python instalados en la maquina, los mas nuevos primero.

    Se mira donde quedan los que estan instalados de verdad: el de
    python.org, el que trae Visual Studio y el que se instala para todos
    los usuarios. Se descarta cualquier ruta con 'WindowsApps', que es
    donde vive el de la Store.
    """
    casa = pathlib.Path.home()
    lugares = [
        pathlib.Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Shared"),
        casa / "AppData" / "Local" / "Programs" / "Python",
        pathlib.Path(r"C:\Program Files"),
        pathlib.Path("C:/"),
    ]

    encontrados = []
    for lugar in lugares:
        if not lugar.exists():
            continue
        try:
            for patron in ("Python3*/python.exe", "Python*_64/python.exe"):
                for ruta in lugar.glob(patron):
                    if "WindowsApps" not in str(ruta):
                        encontrados.append(ruta)
        except OSError:
            continue

    return sorted(set(encontrados), reverse=True)


def asegurar_capaz(argumentos):
    """
    Si el Python que corre no sirve, relanza el programa con otro.

    No vuelve: o bien no hizo falta cambiar, o bien termina el proceso
    con el codigo de salida del que si sirvio.
    """
    if puede_cargar_resolve():
        return
    if os.environ.get(_YA_CAMBIE):
        return

    raiz = pathlib.Path(__file__).resolve().parent.parent
    yo = pathlib.Path(sys.executable).resolve()

    for otro in candidatos():
        if otro.resolve() == yo:
            continue
        prueba = subprocess.run(
            [str(otro), "-c",
             "import os,sys;"
             "sys.path.insert(0, os.environ['RESOLVE_SCRIPT_API']+'\\Modules');"
             "import DaVinciResolveScript"],
            capture_output=True, text=True, env=dict(os.environ))
        if prueba.returncode != 0:
            continue

        consola.alerta("Este Python no puede hablar con Resolve (es el de")
        consola.alerta("Microsoft Store, que no lo tiene permitido). Cambio a:")
        consola.alerta(str(otro))

        entorno = dict(os.environ)
        entorno[_YA_CAMBIE] = "1"
        sys.exit(subprocess.call(
            [str(otro), "-m", "montaje"] + list(argumentos),
            cwd=str(raiz), env=entorno))
