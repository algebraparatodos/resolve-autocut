# -*- coding: utf-8 -*-
"""
Todo lo que habla con DaVinci Resolve.

Se separa del resto porque esta API tiene una peculiaridad que contagia
el estilo de cualquier codigo que la toque: casi nada tira un error.
Cuando algo no se puede hacer, la llamada devuelve None o False y sigue
como si nada. De ahi que cada funcion de aca comprueba lo que hizo en
vez de confiar en lo que le contestaron.

Las trampas concretas estan en 'docs/davinci-resolve.md' y conviene
leerlas antes de tocar este paquete.
"""
