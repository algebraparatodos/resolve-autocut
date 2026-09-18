# -*- coding: utf-8 -*-
"""
Saber donde hay voz y que se dice.

Todo este paquete corre en un Python que no es el del programa
principal, y conviene entender por que antes de tocarlo: el motor de voz
se instala en un entorno virtual aparte, y la libreria de DaVinci
Resolve no se puede abrir desde cualquier Python. Son dos requisitos que
no siempre se cumplen a la vez en la misma instalacion.

La salida fue dejar de pelearse con eso: el programa principal lanza
estos scripts como procesos separados y les lee la respuesta en JSON.
"""
