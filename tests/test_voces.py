# -*- coding: utf-8 -*-
"""Partir los tramos para que cada clip tenga una sola voz."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from montaje import voces  # noqa: E402


class Partir(unittest.TestCase):

    def test_sin_voz_grave_no_cambia_nada(self):
        self.assertEqual(voces.partir([[0, 5], [7, 9]], []),
                         ([[0, 5], [7, 9]], set()))

    def test_el_en_medio_de_ella_deja_tres_clips(self):
        # El caso que pidio Juani: ella habla, el mete una indicacion y
        # ella sigue. Tienen que quedar tres clips, el del medio suyo.
        nuevos, suyos = voces.partir([[40, 50]], [[42.2, 44.0]])
        self.assertEqual(nuevos, [[40, 42.2], [42.2, 44.0], [44.0, 50]])
        self.assertEqual(suyos, {1})

    def test_tramo_entero_de_el(self):
        # Su voz manda sobre los bordes: si se le oye desde antes de que
        # el detector diera el tramo por empezado, el clip arranca antes.
        nuevos, suyos = voces.partir([[10, 12]], [[9.5, 12.5]])
        self.assertEqual((nuevos, suyos), ([[9.5, 12.5]], {0}))

    def test_su_voz_entra_aunque_el_detector_no_la_viera(self):
        # De fondo y lejos del microfono, el detector de voz no lo
        # reconoce: lo que se oye de el entra igual, como clip suyo.
        nuevos, suyos = voces.partir([[0, 5], [10, 15]], [[6, 8]])
        self.assertEqual(nuevos, [[0, 5], [6, 8], [10, 15]])
        self.assertEqual(suyos, {1})

    def test_su_voz_que_se_pega_a_un_tramo_lo_alarga(self):
        nuevos, suyos = voces.partir([[43.13, 50]], [[42.21, 44.01]])
        self.assertEqual(nuevos, [[42.21, 44.01], [44.01, 50]])
        self.assertEqual(suyos, {0})

    def test_pedacito_de_ella_pegado_a_el_es_superposicion(self):
        # Una decima de ella entre dos frases de el: hablan encima, y eso
        # cuenta como suyo. Queda un solo clip de el, no tres.
        nuevos, suyos = voces.partir([[0, 10]], [[2, 4], [4.1, 6]])
        self.assertEqual(nuevos, [[0, 2], [2, 6], [6, 10]])
        self.assertEqual(suyos, {1})

    def test_pedacito_de_el_es_error_del_detector(self):
        nuevos, suyos = voces.partir([[0, 10]], [[5, 5.05]])
        self.assertEqual((nuevos, suyos), ([[0, 10]], set()))

    def test_los_indices_cuentan_todos_los_tramos(self):
        # Los indices son de la lista nueva entera, no de cada tramo: es
        # lo que despues se usa para pintar el clip correcto.
        nuevos, suyos = voces.partir([[0, 3], [5, 9]], [[6, 7]])
        self.assertEqual(nuevos, [[0, 3], [5, 6], [6, 7], [7, 9]])
        self.assertEqual(suyos, {2})


if __name__ == "__main__":
    unittest.main()
