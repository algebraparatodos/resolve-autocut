# -*- coding: utf-8 -*-
"""
Encontrar las frases que se dijeron mas de una vez.

Lo que NO hace, y es la decision de diseno mas importante del programa:
no elige cual se queda y no descarta ninguna. Cuando alguien se traba y
vuelve a empezar, la buena suele ser la ultima, pero no siempre, y ese
"no siempre" es carisimo: la toma que se pierde no se nota, porque el
montaje queda perfectamente coherente sin ella. Un error que no se ve es
peor que uno que se ve.

Asi que se conservan todas y se marcan con una bandera del mismo color,
para que quien edite vea de un golpe que esos tres clips dicen lo mismo
y elija mirando.

Este modulo no habla con Resolve ni con ffmpeg: entra texto con tiempos
y salen grupos de indices. Por eso se puede probar entero sin abrir nada.
"""

import difflib
import re
import unicodedata


# Palabras que no aportan nada al comparar dos frases. Se quitan solo
# para la comparacion: en el video se quedan, porque sacarlas seria
# editar, y editar no es tarea de este programa.
MULETILLAS = {
    "eh", "em", "este", "esto", "mmm", "mm", "aja", "bueno", "digamos",
    "entonces", "o", "sea", "osea", "tipo", "viste", "nada", "pues",
    "vale", "ok", "a", "ver",
}


def normalizar(texto):
    """
    Deja una frase comparable con otra.

    Se quitan tildes, signos y mayusculas porque el reconocedor de habla
    no es consistente con ninguna de las tres cosas: la misma frase dicha
    dos veces puede volver con y sin coma, o con 'que' y 'que'. Comparar
    sin normalizar hace que dos tomas identicas no se parezcan.
    """
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9ñ\s]", " ", texto)
    return [p for p in texto.split() if p and p not in MULETILLAS]


def parecido(unas, otras):
    """
    Cuanto se parecen dos frases, de 0 a 1.

    Se comparan listas de palabras y no cadenas de caracteres a
    proposito. Por caracteres, 'el cuadrado de dos' y 'el cuadrado de
    tres' salen casi identicas porque comparten casi todas las letras;
    por palabras, la diferencia pesa lo que tiene que pesar.
    """
    if not unas or not otras:
        return 0.0
    return difflib.SequenceMatcher(None, unas, otras).ratio()


def bloque_comun(unas, otras):
    """
    Cuantas palabras seguidas iguales comparten dos frases.

    Es la otra forma de reconocer una repeticion, y hace falta porque el
    parecido global se queda corto en dos situaciones muy comunes:

    * **El texto viene fragmentado.** Los tramos duran unos segundos, asi
      que lo que cae en cada uno no es una oracion sino un pedazo. Dos
      pedazos de la misma frase repetida pueden empezar y terminar en
      puntos distintos, y entonces el parecido global baja mucho aunque
      en el medio digan exactamente lo mismo.
    * **Se repite la idea con otro envoltorio.** "Entonces lo que hacemos
      es pasar el dos dividiendo" y "lo que hacemos es pasar el dos para
      el otro lado" comparten seis palabras seguidas, pero el resto
      cambia lo suficiente como para hundir el promedio.

    Seis palabras seguidas iguales, ya sin muletillas, no pasan por
    casualidad: es la misma frase dicha dos veces.
    """
    if not unas or not otras:
        return 0
    igual = difflib.SequenceMatcher(None, unas, otras).find_longest_match(
        0, len(unas), 0, len(otras))
    return igual.size


def se_repiten(unas, otras, umbral, palabras_seguidas):
    """
    Si dos frases son la misma dicha dos veces.

    Alcanza con cualquiera de los dos criterios: que se parezcan en
    conjunto, o que compartan una tirada larga de palabras iguales.
    """
    if parecido(unas, otras) >= umbral:
        return True
    return bloque_comun(unas, otras) >= palabras_seguidas


# Cuanto puede estar una frase de un tramo para darla igualmente por
# suya. Cubre los bordes que se comieron los margenes del corte, y nada
# mas: dos segundos es menos que la pausa mas corta que el montaje deja.
PEGADA = 2.0


def _cuanto_se_pisan(uno, otro):
    """Segundos que comparten dos intervalos, o 0 si no se tocan."""
    return max(0.0, min(uno[1], otro[1]) - max(uno[0], otro[0]))


def _distancia(uno, otro):
    """Segundos de hueco entre dos intervalos que no se tocan."""
    return max(0.0, max(uno[0], otro[0]) - min(uno[1], otro[1]))


def texto_de_cada_tramo(tramos, frases):
    """
    Que se dice dentro de cada tramo hablado.

    Cada frase va al tramo con el que MAS se pisa en el tiempo. Asi cada
    frase cae en uno solo, y sobre todo, ninguna se pierde.

    La primera version asignaba la frase al tramo donde caia su punto
    medio, que parece razonable y pierde material a lo bestia. El motivo
    es que las frases del reconocedor no coinciden con los tramos
    hablados: el reconocedor junta en una sola frase lo que hay antes y
    despues de una pausa, asi que una frase puede durar nueve segundos
    con un silencio en el medio. Ese silencio es justo lo que el montaje
    corta, de modo que el punto medio de la frase cae en un hueco que ya
    no existe, y la frase entera se queda sin tramo.

    Medido en el arranque de un video real: cuatro de doce tramos se
    quedaban sin nada de texto, incluido el saludo de bienvenida repetido
    que se veia a simple vista en pantalla. Se comparaba con un tercio
    del material invisible, y por eso no se detectaban repeticiones
    obvias.
    """
    textos = [[] for _ in tramos]

    for frase in frases:
        cuando = (float(frase["inicio"]), float(frase["fin"]))

        mejor, cuanto = None, 0.0
        for indice, tramo in enumerate(tramos):
            pisa = _cuanto_se_pisan(cuando, tramo)
            if pisa > cuanto:
                mejor, cuanto = indice, pisa

        # Una frase que no se pisa con ningun tramo va al mas cercano,
        # pero solo si esta pegada: son los bordes que se comieron los
        # margenes del corte. Una frase que cayo en un silencio largo,
        # en cambio, es material que el montaje descarto, y meterla en
        # un tramo que esta a un minuto seria atribuirle algo que ahi no
        # se dice.
        if mejor is None and tramos:
            cerca = min(range(len(tramos)),
                        key=lambda i: _distancia(cuando, tramos[i]))
            if _distancia(cuando, tramos[cerca]) <= PEGADA:
                mejor = cerca

        if mejor is not None:
            textos[mejor].append(frase["texto"])

    return [" ".join(partes).strip() for partes in textos]


def agrupar(textos, tramos, ajustes):
    """
    Los grupos de tramos que dicen lo mismo.

    Devuelve una lista de listas de indices, solo con los grupos de dos
    o mas. Cada tramo esta en un grupo como mucho.

    Solo se mira hacia adelante y hasta una ventana corta: cuando alguien
    se traba, vuelve a empezar enseguida. Comparar contra todo el video
    agrupa frases que se parecen por casualidad, como dos enunciados con
    la misma estructura dichos en minutos distintos.

    **La ventana se mide en segundos y no en cantidad de tramos**, y la
    diferencia importa mas de lo que parece. Trabarse y volver a empezar
    es un fenomeno de tiempo: pasa dentro del medio minuto siguiente,
    diga uno lo que diga en el medio. Contando tramos, en cambio, la
    ventana dura lo que duren esos tramos: en un video con cortes largos
    son varios minutos, y en uno troceado en pedacitos de tres segundos
    son doce segundos, demasiado poco para llegar a la segunda toma. Con
    425 tramos en una hora, contar cuatro tramos se quedaba corto.

    Para entrar en un grupo hay que parecerse a TODAS las que ya estan,
    no solo a la ultima. Sin esa exigencia el agrupado se va derivando:
    A se parece a B, B se parece a C, y termina en el mismo grupo un C
    que no tiene nada que ver con A. Con frases cortas eso pasa enseguida
    y el resultado son banderas del mismo color sobre cosas distintas,
    que es peor que no marcar nada, porque quien edita deja de creerles.
    """
    palabras = [normalizar(t) for t in textos]
    minimo = int(ajustes["palabras_minimas"])
    umbral = float(ajustes["similitud_minima"])
    ventana = float(ajustes["ventana_segundos"])
    seguidas = int(ajustes["palabras_seguidas_iguales"])

    grupo_de = {}
    grupos = []

    def entra_en(grupo, candidata):
        return all(se_repiten(palabras[miembro], candidata, umbral, seguidas)
                   for miembro in grupo)

    for i, unas in enumerate(palabras):
        if len(unas) < minimo:
            continue
        for j in range(i + 1, len(palabras)):
            # Cuanto tiempo paso desde que termino el tramo i hasta que
            # empieza el j. Pasada la ventana se corta el barrido: los
            # tramos estan en orden, asi que los de mas adelante estan
            # todavia mas lejos.
            if tramos[j][0] - tramos[i][1] > ventana:
                break

            otras = palabras[j]
            if len(otras) < minimo or j in grupo_de:
                continue
            if not se_repiten(unas, otras, umbral, seguidas):
                continue

            if i in grupo_de:
                grupo = grupos[grupo_de[i]]
                if not entra_en(grupo, otras):
                    continue
                grupo.append(j)
                grupo_de[j] = grupo_de[i]
            else:
                grupos.append([i, j])
                grupo_de[i] = grupo_de[j] = len(grupos) - 1

    return [sorted(set(g)) for g in grupos if len(set(g)) > 1]


def buscar(tramos, frases, ajustes):
    """
    De los tramos hablados y lo que se dice, los grupos de repetidas.

    Devuelve (grupos, textos) porque el informe necesita las dos cosas:
    los indices para marcar y el texto para contar que se repitio.
    """
    textos = texto_de_cada_tramo(tramos, frases)
    return agrupar(textos, tramos, ajustes), textos
