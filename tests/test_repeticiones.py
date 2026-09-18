# -*- coding: utf-8 -*-
"""
Pruebas del agrupado de frases repetidas.

Se prueba esta parte y no el resto porque es la unica que decide algo:
si agrupa de menos, quien edita no ve que hay tres tomas de lo mismo; si
agrupa de mas, le pinta del mismo color frases que no tienen nada que
ver y deja de confiar en las banderas. Las dos fallas se notan tarde,
mirando el video, que es cuando mas caro sale.

Lo demas del programa habla con Resolve o con ffmpeg y se comprueba
midiendo el resultado, no con pruebas.
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from montaje import repeticiones
from montaje.ajustes import POR_DEFECTO

AJUSTES = POR_DEFECTO["repeticiones"]


def seguidos(cuantos, dura=5.0, pausa=1.0):
    """
    Tramos uno detras de otro, para las pruebas donde el tiempo da igual.

    Se separan un segundo, que es menos que la ventana, asi que todos se
    comparan entre si y lo unico que decide es el parecido del texto.
    """
    return [(i * (dura + pausa), i * (dura + pausa) + dura)
            for i in range(cuantos)]


class Normalizar(unittest.TestCase):

    def test_quita_tildes_y_signos(self):
        self.assertEqual(repeticiones.normalizar("¿Cuánto es, dos?"),
                         ["cuanto", "es", "dos"])

    def test_quita_muletillas(self):
        # El reconocedor mete muletillas de forma irregular: la misma
        # toma puede volver con "eh" y sin el.
        self.assertEqual(repeticiones.normalizar("eh bueno, el teorema"),
                         ["el", "teorema"])

    def test_la_misma_frase_con_y_sin_muletilla_es_identica(self):
        self.assertEqual(repeticiones.normalizar("o sea, el limite"),
                         repeticiones.normalizar("El límite."))


class Parecido(unittest.TestCase):

    def test_identicas(self):
        unas = repeticiones.normalizar("el area del circulo es pi por radio")
        self.assertEqual(repeticiones.parecido(unas, unas), 1.0)

    def test_una_palabra_distinta_sigue_pareciendose(self):
        unas = repeticiones.normalizar("sabias que cero nueve periodico es uno")
        otras = repeticiones.normalizar("sabias que cero nueve periodico es dos")
        self.assertGreater(repeticiones.parecido(unas, otras), 0.75)

    def test_frases_distintas_no_se_parecen(self):
        unas = repeticiones.normalizar("vamos a ver el teorema de pitagoras")
        otras = repeticiones.normalizar("la derivada mide cuanto cambia algo")
        self.assertLess(repeticiones.parecido(unas, otras), 0.5)

    def test_frase_vacia(self):
        self.assertEqual(repeticiones.parecido([], ["hola"]), 0.0)


class TextoDeCadaTramo(unittest.TestCase):

    def test_cada_frase_cae_en_su_tramo(self):
        tramos = [(0.0, 5.0), (10.0, 15.0)]
        frases = [{"inicio": 1.0, "fin": 2.0, "texto": "uno"},
                  {"inicio": 11.0, "fin": 12.0, "texto": "dos"}]
        self.assertEqual(repeticiones.texto_de_cada_tramo(tramos, frases),
                         ["uno", "dos"])

    def test_una_frase_a_caballo_de_un_corte_cae_en_uno_solo(self):
        # Empieza en el primer tramo y termina en el segundo. Va al que
        # mas se pisa, asi que no se cuenta dos veces.
        tramos = [(0.0, 5.0), (5.0, 10.0)]
        frases = [{"inicio": 4.0, "fin": 8.0, "texto": "a caballo"}]
        salida = repeticiones.texto_de_cada_tramo(tramos, frases)
        self.assertEqual(salida, ["", "a caballo"])

    def test_una_frase_larga_con_un_silencio_en_el_medio_no_se_pierde(self):
        # El caso que rompia la deteccion de repeticiones en material
        # real. El reconocedor junta en una sola frase lo que hay antes y
        # despues de una pausa, y esa pausa es justo lo que el montaje
        # corta. Asignando por el punto medio, la frase caia en el hueco
        # y desaparecia: el saludo de bienvenida repetido se veia en
        # pantalla y el programa no lo tenia.
        tramos = [(0.0, 4.0), (16.0, 20.0)]
        frases = [{"inicio": 14.3, "fin": 23.0,
                   "texto": "hola y bienvenidas a esta nueva clase"}]
        salida = repeticiones.texto_de_cada_tramo(tramos, frases)
        self.assertEqual(salida[1], "hola y bienvenidas a esta nueva clase")

    def test_frase_lejos_de_todo_tramo_se_descarta(self):
        # Material que el montaje tiro. Meterlo en el tramo mas cercano
        # seria atribuirle a un clip algo que ahi no se dice.
        tramos = [(0.0, 5.0)]
        frases = [{"inicio": 90.0, "fin": 92.0, "texto": "en un silencio"}]
        self.assertEqual(repeticiones.texto_de_cada_tramo(tramos, frases),
                         [""])

    def test_frase_pegada_al_borde_si_entra(self):
        # Se la comio el margen del corte por medio segundo: es de ese
        # tramo.
        tramos = [(0.0, 5.0)]
        frases = [{"inicio": 5.5, "fin": 6.5, "texto": "justo al final"}]
        self.assertEqual(repeticiones.texto_de_cada_tramo(tramos, frases),
                         ["justo al final"])


class Agrupar(unittest.TestCase):

    def test_dos_tomas_de_la_misma_frase(self):
        textos = ["hoy vamos a ver como se resuelve una ecuacion",
                  "hoy vamos a ver como se resuelve una ecuacion",
                  "empecemos por el lado izquierdo"]
        self.assertEqual(repeticiones.agrupar(textos, seguidos(len(textos)), AJUSTES), [[0, 1]])

    def test_tres_tomas_seguidas_van_al_mismo_grupo(self):
        frase = "el discriminante nos dice cuantas soluciones hay"
        grupos = repeticiones.agrupar([frase] * 3, seguidos(3), AJUSTES)
        self.assertEqual(grupos, [[0, 1, 2]])

    def test_frases_distintas_no_se_agrupan(self):
        textos = ["vamos a ver el teorema de pitagoras",
                  "la derivada mide cuanto cambia una funcion",
                  "el area del circulo es pi por radio al cuadrado"]
        self.assertEqual(repeticiones.agrupar(textos, seguidos(len(textos)), AJUSTES), [])

    def test_las_frases_cortas_no_cuentan(self):
        # "si", "claro" o "bueno" se repiten todo el tiempo sin que eso
        # sea una toma fallida.
        self.assertEqual(
            repeticiones.agrupar(["claro"] * 3, seguidos(3), AJUSTES), [])

    def test_lejos_en_el_tiempo_no_se_agrupa(self):
        # La misma frase dicha dos veces con diez minutos en el medio no
        # es alguien que se trabo: es una estructura que se repite en la
        # clase. Los textos son identicos a proposito, asi que lo unico
        # que los separa es el tiempo.
        frase = "ahora prestemos atencion a lo que pasa del otro lado"
        tramos = [(0.0, 5.0), (600.0, 605.0)]
        self.assertEqual(repeticiones.agrupar([frase, frase], tramos,
                                              AJUSTES), [])

    def test_repetir_despues_de_un_intento_largo_si_se_agrupa(self):
        # El caso que la ventana medida en cantidad de tramos se perdia:
        # uno arranca, se enreda un rato largo y vuelve a empezar. Pasan
        # treinta segundos y varios tramos en el medio, pero es la misma
        # frase intentada dos veces.
        frase = "hoy vamos a ver como se resuelve una ecuacion de segundo grado"
        textos = [frase,
                  "perdon que me trabe con esto un momento",
                  "dejame que lo diga de nuevo desde el principio",
                  frase]
        tramos = [(0.0, 6.0), (7.0, 13.0), (14.0, 20.0), (21.0, 27.0)]
        self.assertEqual(repeticiones.agrupar(textos, tramos, AJUSTES),
                         [[0, 3]])

    def test_no_se_va_encadenando_de_a_poco(self):
        # A se parece a B y B se parece a C, pero A y C no tienen nada
        # que ver. Sin exigir parecido con todo el grupo, los tres
        # terminarian con la misma bandera.
        textos = ["el gato negro come pescado crudo por la manana",
                  "el gato negro come carne cruda por la manana",
                  "el perro blanco come carne cruda por la noche"]
        grupos = repeticiones.agrupar(textos, seguidos(len(textos)), AJUSTES)
        self.assertNotIn([0, 1, 2], grupos)
        for grupo in grupos:
            self.assertNotIn(2, grupo)

    def test_un_tramo_vacio_no_agrupa_con_otro_vacio(self):
        # Sin texto no se puede afirmar que digan lo mismo.
        self.assertEqual(
            repeticiones.agrupar(["", "", ""], seguidos(3), AJUSTES), [])

    def test_la_union_es_transitiva(self):
        # Primera y tercera no se parecen tanto entre si, pero las dos se
        # parecen a la del medio: son la misma frase intentada tres veces.
        textos = ["el resultado de esta cuenta es siempre positivo",
                  "el resultado de esta cuenta es siempre negativo",
                  "el resultado de esta cuenta es siempre cero"]
        grupos = repeticiones.agrupar(textos, seguidos(len(textos)), AJUSTES)
        self.assertEqual(grupos, [[0, 1, 2]])

    def test_ningun_tramo_aparece_en_dos_grupos(self):
        frase, otra = "primera frase larga para la prueba", "segunda frase distinta del todo"
        textos = [frase, frase, otra, otra]
        vistos = [i for g in repeticiones.agrupar(textos, seguidos(len(textos)), AJUSTES) for i in g]
        self.assertEqual(len(vistos), len(set(vistos)))


class PalabrasSeguidas(unittest.TestCase):
    """
    El segundo criterio: una tirada larga de palabras iguales.

    Existe porque el parecido global se hunde cuando el texto viene
    cortado a mitad de oracion, que es lo normal con tramos de pocos
    segundos, y cuando se dice lo mismo cambiando el final.
    """

    def _repiten(self, a, b):
        return repeticiones.se_repiten(
            repeticiones.normalizar(a), repeticiones.normalizar(b),
            AJUSTES["similitud_minima"], AJUSTES["palabras_seguidas_iguales"])

    def test_la_misma_frase_con_otro_final(self):
        # Se parecen 0,74, por debajo del umbral, pero comparten siete
        # palabras seguidas: es la misma frase empezada dos veces.
        self.assertTrue(self._repiten(
            "entonces lo que hacemos es pasar el dos dividiendo",
            "lo que hacemos es pasar el dos para el otro lado"))

    def test_la_misma_frase_cortada_por_el_medio(self):
        self.assertTrue(self._repiten(
            "sabias que cero coma nueve periodico es igual a uno y te lo voy a demostrar",
            "cero coma nueve periodico es igual a uno, mira"))

    def test_frases_distintas_que_comparten_vocabulario(self):
        # Caso real de un video de Juani: se parecen 0,57 y comparten
        # cuatro palabras seguidas, pero son dos frases distintas de la
        # misma explicacion. Marcarlas seria pintar de color algo que no
        # es una repeticion, y eso hace que las marcas dejen de servir.
        self.assertFalse(self._repiten(
            "super importante porque cuando vertamos la escalola si nuestro modelo no esta",
            "cuando vertamos la escalola nuestro modelo va directamente a flotar"))

    def test_cuenta_palabras_y_no_letras(self):
        self.assertEqual(repeticiones.bloque_comun(
            repeticiones.normalizar("uno dos tres cuatro cinco seis siete"),
            repeticiones.normalizar("antes uno dos tres cuatro cinco seis siete despues")), 7)

    def test_sin_texto_no_hay_bloque(self):
        self.assertEqual(repeticiones.bloque_comun([], ["hola"]), 0)


class Buscar(unittest.TestCase):

    def test_de_punta_a_punta(self):
        tramos = [(0.0, 4.0), (5.0, 9.0), (10.0, 14.0)]
        frase = "sabias que cero coma nueve periodico es igual a uno"
        frases = [{"inicio": 1.0, "fin": 3.0, "texto": frase},
                  {"inicio": 6.0, "fin": 8.0, "texto": frase},
                  {"inicio": 11.0, "fin": 13.0,
                   "texto": "vamos a demostrarlo con algebra"}]

        grupos, textos = repeticiones.buscar(tramos, frases, AJUSTES)
        self.assertEqual(grupos, [[0, 1]])
        self.assertEqual(textos[2], "vamos a demostrarlo con algebra")


if __name__ == "__main__":
    unittest.main(verbosity=2)
