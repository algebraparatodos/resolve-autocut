# Montaje automático para DaVinci Resolve

Le arrastrás la carpeta con lo que grabaste y te deja en Resolve una
línea de tiempo lista para editar: el audio parejo, el material liviano
para que la reproducción no se arrastre, todo lo que no sea voz cortado,
y las frases que dijiste dos veces marcadas con banderas del mismo color.

No exporta nada, no elige tomas y no pone efectos. Lo que devuelve es el
punto desde el que empieza la edición de verdad.

```
montar.bat  <carpeta con los videos>
```

## Qué hace, siempre lo mismo y en este orden

| | Paso | Por qué está |
|---|---|---|
| 1 | Mide el material | De ahí salen el lienzo y el ritmo, incluido si viene vertical |
| 2 | Configura el proyecto | Lienzo, ritmo y uso de proxies. Va antes de generar nada |
| 3 | Nivela el audio a -14 LUFS | Escribe sólo la pista de sonido, no una copia del video |
| 4 | Genera copias livianas | Y se las engancha a Resolve, para poder reproducir fluido |
| 5 | Importa los clips | Reutilizando los que ya estuvieran adentro |
| 6 | Corta donde no hablás | Detectando voz, no volumen |
| 7 | Monta imagen y sonido | La imagen del original, el sonido del audio nivelado |
| 8 | Marca las frases repetidas | Sin descartar ninguna, y comprueba la sincronía |

## Las cuatro decisiones que lo explican

**Silencio es donde nadie habla, no donde no suena nada.** Son dos cosas
distintas y confundirlas arruina el resultado aunque todo lo demás esté
bien. Medir volumen parece lo obvio y falla enseguida: un teclado, un
golpe en la mesa, una silla o el aire acondicionado pasan cualquier
umbral y se conservan como si fueran habla. En un video de prueba, los
primeros treinta y cinco segundos no tenían una sola palabra y
sobrevivían enteros, troceados en pedacitos de un segundo. Lo que se usa
acá es el detector de voz de Silero, que distingue una voz humana de un
ruido aunque el ruido suene más fuerte.

**Lo ambiguo se marca, no se descarta.** Cuando alguien se traba y repite
una frase, la buena suele ser la última, pero no siempre. Ese "no
siempre" es carísimo: la toma que se pierde no se nota, porque el montaje
queda perfectamente coherente sin ella. Así que el programa conserva
todas las versiones y las pinta del mismo color para que se vean de un
golpe, y el corte lo decide una persona.

Reconocer que dos clips dicen lo mismo tiene más trampa de la que parece,
y las tres cosas que importan se aprendieron midiendo sobre material real:

* **Se compara por parecido, no por coincidencia exacta**, porque nadie
  repite una frase palabra por palabra. Y hay un segundo criterio que
  salva los casos que el parecido global no ve: seis palabras seguidas
  iguales, que aparecen cuando se dice lo mismo cambiando el final o
  cuando el corte parte la frase al medio.
* **La ventana se mide en segundos, no en cantidad de clips.** Trabarse y
  volver a empezar es cosa de tiempo: pasa dentro del medio minuto
  siguiente, diga uno lo que diga en el medio. Contando clips, un video
  troceado en pedacitos deja la ventana en unos pocos segundos y la
  segunda toma queda fuera.
* **El texto de cada clip se asigna por solapamiento y no por el punto
  medio de la frase.** El reconocedor junta en una sola frase lo que hay
  antes y después de una pausa, y esa pausa es justo lo que el montaje
  corta, así que el punto medio cae en un hueco que ya no existe y la
  frase entera se pierde. Medido en un video real: cuatro de doce clips
  se quedaban sin una palabra, incluido un saludo repetido que se veía a
  simple vista.

**El material original no se toca ni se duplica.** Resolve no deja
cambiar el volumen de un clip por script, así que el nivelado hay que
hacerlo antes de importar. La forma obvia, copiar el video con el audio
corregido, duplica la carpeta entera en disco: para una carpeta de 23 GB
son 22 GB tirados para tocar 90 MB de sonido. Lo que se hace acá es lo
que hace cualquier editor: se escribe sólo la pista de audio como un
`.wav` aparte, y en la línea de tiempo se monta la imagen del original
con ese sonido. Quedan alineados al cuadro, y el programa lo comprueba
antes de dar el montaje por bueno.

**Lo que dice la API hay que comprobarlo.** En la API de Resolve casi
nada tira un error: cuando algo no se puede hacer, la llamada devuelve
`None` o `False` y sigue como si nada. De ahí que acá se escriba un
ajuste y se vuelva a leer, se arme la línea de tiempo y se cuenten los
clips, y se enganche un proxy y se relea la propiedad. Las quince
trampas concretas, con lo que falla y cómo se reconoce, están en
[docs/davinci-resolve.md](docs/davinci-resolve.md).

## Lo que hace falta tener

* **DaVinci Resolve** instalado. No hace falta abrirlo: si no está
  corriendo, el programa lo abre y espera, y si no hay ningún proyecto,
  lo crea con el nombre de la carpeta. Si ya tenías uno abierto, trabaja
  ahí y no te lo cambia.
* **El scripting activado**, una sola vez por computadora:
  `Preferences > System > General > External scripting using: Local`.
  Esto sí es a mano, y por un problema de huevo y gallina: mientras esté
  apagado la API no responde, así que no hay forma de encenderlo desde
  la API.
* **Python instalado de verdad**, no el de Microsoft Store: ése corre en
  un cajón aislado que le prohíbe cargar la librería de Resolve. Si es el
  único que hay, el programa busca otro y se relanza solo.
* **ffmpeg** en el sistema (`winget install Gyan.FFmpeg`).
* **El motor de voz**, que se instala solo la primera vez. Son unos 300
  MB y no se vuelve a tocar.

## Ajustes

Todo lo que se puede cambiar vive en [ajustes.ini](ajustes.ini), con el
motivo de cada número escrito al lado. No hace falta abrirlo para usar el
programa, y lo que se borre vuelve al valor de fábrica.

Lo que más se toca: `pausa_minima` si los cortes quedan atropellados,
`confianza_voz` si se cuela ruido o se come palabras, y
`similitud_minima` si las banderas agrupan de más o de menos.

## Cómo está armado

```
montaje/
  __main__.py        la puerta de entrada
  pipeline.py        la cadena de pasos, en orden
  ajustes.py         valores por defecto y lectura del .ini
  audio.py           nivelado con loudnorm de dos pasadas
  proxies.py         copias livianas en DNxHR
  repeticiones.py    agrupado de frases por similitud
  herramientas.py    ffmpeg y ffprobe
  interprete.py      conseguir un Python que hable con Resolve
  resolve/           todo lo que toca la API de Resolve
  voz/               detección de voz y transcripción
tests/               pruebas del agrupado de repeticiones
docs/                las trampas de la API, documentadas
```

El paquete `montaje` no sabe que existe una consola ni un `.bat`: cada
paso cuenta lo que hace y quien lo lanza decide cómo se ve. El módulo
`repeticiones` no habla con Resolve ni con ffmpeg, entra texto con
tiempos y salen grupos, y por eso se puede probar entero sin abrir nada:

```
python tests/test_repeticiones.py
```

## Lo que no hace, a propósito

No descarta tomas, no pone zooms, no escribe textos, no corrige color y
no exporta. Un programa que entregara el video terminado le sacaría a
quien edita justamente la parte que quiere hacer.

## Limpiar el disco cuando terminaste

Editar video llena el disco en tres sitios, y dos no se ven desde ningún
lado. `limpiar.bat` los muestra con lo que ocupa cada uno y borra lo que
le digas:

* **Lo que genera el programa**, en la carpeta `<lo que sea> - montaje`
  que queda al lado de los crudos. Casi todo son los proxies.
* **La caché de Resolve**, donde van las copias optimizadas y el render
  cache. Es la que sorprende: crece con cada proyecto, no la vacía nadie
  nunca, y en una máquina de trabajo normal se midieron **78 GB**. Para
  saber dónde la tiene hay que preguntárselo a Resolve, así que conviene
  tenerlo abierto.
* **Los originales**, que no se tocan jamás.

Nada se borra sin escribir "borrar" para confirmar. Los proxies se
vuelven a generar solos la próxima vez, así que borrarlos no pierde nada
salvo el rato que tardan.

Un detalle de Windows que conviene saber: si Resolve tiene abierto un
proyecto que usaba esos archivos, **el espacio no se libera hasta que lo
cierres**, aunque los archivos ya no estén.
