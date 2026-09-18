# -*- coding: utf-8 -*-
"""
Monta en DaVinci Resolve una linea de tiempo lista para editar a partir
de una carpeta de grabaciones crudas.

Lo que hace de corrido, sin pedir nada mas que la carpeta:

  1. Nivela el audio, para que no quede ni alto ni bajo.
  2. Genera copias livianas y se las engancha a Resolve, para que la
     reproduccion no se arrastre.
  3. Configura el proyecto: lienzo, ritmo y cache.
  4. Corta todo lo que no sea alguien hablando.
  5. Agrupa las frases repetidas y las marca con banderas de color.

Lo que NO hace, a proposito: elegir por vos. No descarta tomas, no pone
zooms, no escribe textos y no exporta nada. Devuelve una linea de tiempo
para seguir trabajando encima.
"""

__version__ = "0.1.0"
