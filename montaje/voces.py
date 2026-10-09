# -*- coding: utf-8 -*-
"""
Partir los tramos hablados para que cada clip tenga una sola voz.

En los videos de Natalia se oye de fondo a Juani dando indicaciones, y el
quiere que el clip donde habla el tenga SOLO su voz: nada de un clip que
empieza con ella y termina con el. Asi lo puede sacar, o dejar, de un
solo gesto.

Esto es matematica de intervalos y nada mas, sin Resolve ni audio de por
medio, para poder probarlo con tests.
"""

# Un pedazo de Natalia mas corto que esto, pegado a uno de Juani, no se
# deja como clip propio: es el final de una palabra de ella pisada por
# el, o una superposicion. Se lo queda el, que es lo que Juani pidio
# para cuando hablan a la vez.
PEDAZO_MINIMO_DE_ELLA = 0.25

# Un pedazo de Juani mas corto que esto es un error del detector, no una
# palabra.
PEDAZO_MINIMO_DE_EL = 0.10


def partir(tramos, graves):
    """
    Corta cada tramo hablado en los bordes de la voz grave.

    'tramos' son los tramos hablados del video y 'graves' donde se oye a
    Juani, los dos en segundos. Devuelve (tramos_nuevos, suyos): la lista
    de tramos ya partidos, en orden, y el conjunto de indices de esa
    lista que son de Juani.
    """
    # Lo que es voz de Juani es habla aunque el detector de voz no lo
    # haya visto: de fondo y lejos del microfono, Silero no lo reconoce,
    # y su "para que vean que soy responsable" quedaba fuera del montaje.
    tramos = _unir(list(tramos) + [list(g) for g in graves])

    piezas = []                                  # [inicio, fin, es_suyo]
    for inicio, fin in tramos:
        piezas.extend(_partir_uno(inicio, fin, graves))

    piezas = _absorber_pedazos(piezas)

    nuevos = [[a, b] for a, b, _ in piezas]
    suyos = {i for i, (_, _, suyo) in enumerate(piezas) if suyo}
    return nuevos, suyos


def _unir(tramos):
    """Junta los tramos que se pisan o se tocan, en orden."""
    unidos = []
    for inicio, fin in sorted(tramos):
        if unidos and inicio <= unidos[-1][1]:
            unidos[-1][1] = max(unidos[-1][1], fin)
        else:
            unidos.append([inicio, fin])
    return unidos


def _partir_uno(inicio, fin, graves):
    """Un tramo, partido en pedazos de el y de ella."""
    cortes = []
    for a, b in graves:
        a, b = max(a, inicio), min(b, fin)
        if b > a:
            cortes.append((a, b))

    piezas, cursor = [], inicio
    for a, b in sorted(cortes):
        if a > cursor:
            piezas.append([cursor, a, False])
        piezas.append([max(a, cursor), b, True])
        cursor = max(cursor, b)
    if fin > cursor:
        piezas.append([cursor, fin, False])
    return [p for p in piezas if p[1] > p[0]]


def _absorber_pedazos(piezas):
    """
    Quita los pedazos demasiado cortos para ser un clip.

    Un pedacito de ella pegado a el pasa a ser de el (superposicion). Un
    pedacito de el se le devuelve a ella. Despues se juntan los pedazos
    seguidos del mismo dueno, que si no quedarian dos clips donde va uno.
    """
    for i, pieza in enumerate(piezas):
        largo = pieza[1] - pieza[0]
        suyo = pieza[2]
        pegado_a_el = any(
            0 <= j < len(piezas) and piezas[j][2]
            and (piezas[j][1] == pieza[0] or piezas[j][0] == pieza[1])
            for j in (i - 1, i + 1))
        if not suyo and largo < PEDAZO_MINIMO_DE_ELLA and pegado_a_el:
            pieza[2] = True
        elif suyo and largo < PEDAZO_MINIMO_DE_EL:
            pieza[2] = False

    juntas = []
    for pieza in piezas:
        if juntas and juntas[-1][2] == pieza[2] and juntas[-1][1] == pieza[0]:
            juntas[-1][1] = pieza[1]
        else:
            juntas.append(list(pieza))
    return juntas
