# -*- coding: utf-8 -*-
"""
Los valores con los que trabaja el montaje.

El programa se usa arrastrandole una carpeta y nada mas: no lleva
opciones de linea de comandos porque hace siempre lo mismo. Lo que se
puede cambiar vive en 'ajustes.ini', al lado del .bat, y casi nunca hay
que abrirlo.

Los valores por defecto estan aca y no solo en el .ini a proposito: si
alguien borra el archivo, o lo deja a medias, el programa tiene que
seguir funcionando igual. El .ini manda sobre estos valores, no los
reemplaza.
"""

import configparser
import pathlib


# ---------------------------------------------------------------------
#  Lo que se puede cambiar, con el motivo de cada numero
# ---------------------------------------------------------------------

POR_DEFECTO = {
    "audio": {
        # A cuanto se nivela la voz. -14 LUFS es lo que usan Instagram,
        # YouTube y Spotify: si se entrega mas fuerte lo bajan ellos, y
        # si se entrega mas bajo lo suben con todo el ruido de fondo
        # adentro. Dejarlo aca es que suene como se penso.
        "objetivo_lufs": -14.0,
        # Pico real maximo. -1 dBTP deja margen para que la compresion
        # de las redes no distorsione en los picos de voz.
        "pico_maximo_dbtp": -1.0,
        # Cuanto rango dinamico se permite. 11 LU es el valor con el que
        # la voz hablada queda pareja sin sonar aplastada.
        "rango_lu": 11.0,
    },
    "silencios": {
        # A partir de cuantos segundos sin voz se corta. Por debajo de
        # medio segundo se estan cortando las pausas naturales del habla
        # y el resultado suena atropellado.
        "pausa_minima": 0.5,
        # Aire que se deja antes y despues de cada tramo hablado. El
        # detector marca la voz justa y sin esto se come el ataque de la
        # primera palabra y el final de la ultima.
        "margen_antes": 0.20,
        "margen_despues": 0.30,
        # Tramos mas cortos que esto se descartan: son toses, chasquidos
        # y golpes de labios que el detector da por voz.
        "tramo_minimo": 0.25,
        # Cuan exigente es el detector para dar algo por voz, de 0 a 1.
        "confianza_voz": 0.5,
    },
    "repeticiones": {
        # Cuanto se tienen que parecer dos tramos para darlos por la
        # misma frase dicha dos veces, de 0 a 1. Por debajo de 0,75
        # empieza a agrupar frases que solo comparten el arranque.
        "similitud_minima": 0.75,
        # Cuantos segundos mas adelante se sigue buscando la
        # repeticion. Va en segundos y no en cantidad de tramos porque
        # trabarse y volver a empezar es un fenomeno de tiempo: pasa
        # dentro del medio minuto siguiente, diga uno lo que diga en el
        # medio. Mirar mucho mas lejos agrupa frases que se parecen por
        # casualidad.
        "ventana_segundos": 45.0,
        # Frases mas cortas que esto no se comparan: "si", "claro" o
        # "bueno" se repiten todo el tiempo sin ser una toma fallida.
        "palabras_minimas": 3,
        # La otra forma de reconocer una repeticion: cuantas palabras
        # seguidas iguales alcanzan para darla por buena aunque el resto
        # de la frase cambie. Seis, ya sin muletillas, no coinciden por
        # casualidad. Sirve sobre todo cuando el texto viene cortado a
        # mitad de oracion, que es lo normal con tramos de pocos
        # segundos.
        "palabras_seguidas_iguales": 6,
    },
    "proxies": {
        # Alto de las copias livianas. 720 alcanza para editar comodo y
        # se genera rapido; la calidad final sale del original, que no
        # se toca nunca.
        "alto": 720,
    },
    "proyecto": {
        # Ritmo de la linea de tiempo. 0 quiere decir "el del material",
        # que es lo que conviene: si no coinciden, Resolve conforma el
        # video y todos los cortes caen corridos.
        "ritmo": 0,
    },
}


def cargar(carpeta_del_programa):
    """
    Devuelve los ajustes, con lo que diga el .ini puesto encima de los
    valores por defecto.

    Un valor mal escrito en el archivo no tira el programa: se avisa y
    se usa el de fabrica. Quien edita esto a mano no tiene por que
    quedarse sin montaje por una coma.
    """
    valores = {seccion: dict(claves)
               for seccion, claves in POR_DEFECTO.items()}

    archivo = pathlib.Path(carpeta_del_programa) / "ajustes.ini"
    if not archivo.exists():
        return valores, []

    lector = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    quejas = []
    try:
        lector.read(archivo, encoding="utf-8")
    except configparser.Error as fallo:
        return valores, ["no pude leer ajustes.ini ({})".format(fallo)]

    for seccion in lector.sections():
        if seccion not in valores:
            quejas.append("ajustes.ini: no conozco la seccion [{}]"
                          .format(seccion))
            continue
        for clave, texto in lector.items(seccion):
            if clave not in valores[seccion]:
                quejas.append("ajustes.ini: no conozco '{}' en [{}]"
                              .format(clave, seccion))
                continue
            modelo = POR_DEFECTO[seccion][clave]
            try:
                valores[seccion][clave] = (int(texto)
                                           if isinstance(modelo, int)
                                           else float(texto))
            except ValueError:
                quejas.append(
                    "ajustes.ini: '{}' de [{}] tiene que ser un numero, "
                    "dice '{}'. Uso {}".format(clave, seccion, texto, modelo))

    return valores, quejas
