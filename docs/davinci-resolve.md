# DaVinci Resolve por scripting

Todo lo de acá salió de escribir `_comunes/sacar-silencios`, la
herramienta que arma una línea de tiempo con los silencios ya cortados,
el **13/09/2026**. Se probó contra **DaVinci Resolve Studio 21.0.2.4**
en Windows 11.

**Aviso de arranque, y es el resumen de todo lo demás: en la API de
Resolve casi nada tira un error.** Cuando algo no se puede hacer, la
llamada devuelve `None` o `False` y sigue como si nada. Las trampas de este documento se manifestaron todas igual, con un "no"
pelado, y cada una tardó su rato en encontrarse. Ante un `None`, la
pregunta no es «¿qué salió mal?» sino «¿cuál de estas cinco es?».

---

## Antes de nada: activar el scripting

En Resolve, una sola vez por computadora:

    Preferences > System > General
    External scripting using: Local

Sin eso, `scriptapp("Resolve")` devuelve `None` y no hay nada que hacer.

Las tres variables que pide el módulo de Blackmagic conviene ponerlas
desde el propio Python y no en el `.bat`, así el script funciona igual
si se lo corre a mano, desde el editor o con doble clic:

```python
RESOLVE_SCRIPT_API = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
RESOLVE_SCRIPT_LIB = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
# y agregar RESOLVE_SCRIPT_API\Modules al sys.path
```

---

## 1. El Python de Microsoft Store no sirve

Es el primer muro y el más desconcertante, porque el Python de la Store
es justamente el que Windows ofrece cuando uno escribe `python` sin
tenerlo instalado. En esta máquina era el único 3.11 disponible.

El error que tira es:

    SystemError: initialization of fusionscript failed without raising
    an exception

No dice nada de permisos ni de la Store. El motivo real es que ese
Python corre en un cajón aislado que le prohíbe cargar librerías de
fuera, y `fusionscript.dll` es exactamente eso.

**Qué funciona:** cualquier Python instalado de verdad. Acá anduvo el
que trae Visual Studio, en
`C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe`.
El de python.org también sirve.

**Cómo se resolvió:** el script comprueba al arrancar si puede cargar la
librería y, si no puede, busca otros Python en la máquina y se vuelve a
lanzar solo con el primero que sirva. Al usuario no le aparece nada.
Conviene excluir del rastreo cualquier ruta que contenga `WindowsApps`,
que es donde vive el de la Store.

---

## 2. Una ventana abierta encima deja la API respondiendo a medias

Con Preferences, Project Settings o cualquier cartel de Resolve abierto,
la API contesta, pero importar un clip o crear una línea de tiempo
devuelve `None`. No hay error, no hay aviso, y se pierde mucho rato
buscando el problema en el código.

**Cómo se detecta:** `resolve.GetCurrentPage()` devuelve `None`. Con
Resolve trabajando normalmente devuelve `'media'`, `'cut'`, `'edit'`,
`'fusion'`, `'color'`, `'fairlight'` o `'deliver'`.

Vale la pena comprobarlo al conectar y frenar ahí, diciendo que hay que
cerrar la ventana, en vez de fallar tres pasos más adelante.

---

## 3. La página en la que está Resolve cambia lo que se puede hacer

Aun sin ninguna ventana encima, `ImportMedia` devuelve `None` si Resolve
quedó parado en la página **Cut**. Hay que llevarlo antes a Media:

```python
resolve.OpenPage("media")
```

Conviene además terminar en `OpenPage("edit")`, que es donde sigue el
trabajo a mano.

---

## 4. Importar un archivo que ya está adentro devuelve vacío

`ImportMedia` con la ruta de un clip que ya está en el media pool no
devuelve el clip existente ni avisa de nada: devuelve `None`, igual que
si el archivo no existiera.

Y ése es el caso normal, porque los clips se suelen subir a mano antes
de empezar. **Siempre hay que buscar primero en el media pool** y sólo
importar si no está. La búsqueda va por la propiedad `File Path` del
clip, comparando rutas ya resueltas y en minúsculas, porque Windows no
distingue mayúsculas y la misma carpeta puede venir escrita de varias
formas.

Hay que recorrer también las subcarpetas (`GetSubFolderList`), no sólo
la raíz.

---

## 5. El cuadro de salida queda AFUERA del tramo

La trampa más cara, porque no rompe nada: deja el resultado casi bien.

En `AppendToTimeline([{clipInfo}])`, el `endFrame` de cada tramo **es el
primer cuadro que ya no entra**, no el último que entra. La documentación
de Blackmagic no lo aclara y Resolve acepta cualquiera de los dos valores
sin protestar.

Pasándole el último que entra, cada tramo pierde su cuadro final. A 60
cuadros por segundo son 16 milésimas por corte, imperceptibles de a una;
con sesenta y cinco cortes el video termina un segundo más corto de lo
que dice la cuenta propia.

**La única forma de saberlo es medir la timeline después de armarla**,
comparando lo pedido contra lo que quedó:

```python
item.GetLeftOffset()                          # donde empieza dentro del clip
item.GetLeftOffset() + item.GetDuration()     # donde termina, exclusivo
```

Vale como norma general: después de armar algo por script, medirlo.

---

## 6. El ritmo que manda es el que ve Resolve, no el del archivo

Un `.MOV` de cámara puede venir marcado como 59,94 (`60000/1001`) y
Resolve tratarlo como 60 exacto. Pasó con los clips de una Casio.

Como los números de cuadro se los da uno a Resolve, el ritmo con el que
hay que convertir los segundos es **el que reporta Resolve**, no el que
lee ffprobe:

```python
ritmo   = float(clip.GetClipProperty("FPS"))
cuadros = int(clip.GetClipProperty("Frames"))
```

Con la diferencia entre 59,94 y 60, los cortes se van corriendo y al
final de un video de cinco minutos llegan un tercio de segundo tarde.
En un video de una hora serían casi cuatro segundos.

De ahí sale el orden correcto de trabajo: **los silencios se detectan en
segundos, que es lo único que no depende de quién lea el archivo, y se
pasan a cuadros recién cuando Resolve ya dijo a qué ritmo ve el clip.**

---

## 7. El ritmo del proyecto sólo se cambia con el proyecto sin timelines

`project.SetSetting("timelineFrameRate", "60")` funciona únicamente
mientras el proyecto no tenga ninguna línea de tiempo. En cuanto hay
una, Resolve lo traba, y como siempre, **sin decirlo**: `SetSetting`
devuelve que sí y el valor se queda como estaba.

Por eso hay que **volver a leerlo después de escribirlo** en vez de
confiar en la respuesta.

Si el ritmo del proyecto y el del clip no coinciden, Resolve conforma el
material y todos los cortes caen corridos, con el audio fuera de
sincronía. No es un detalle estético: hay que igualarlos o no armar nada.

---

## 7 bis. El ritmo de REPRODUCCIÓN es otro ajuste, y ése no se puede tocar

Éste costó una tarde y merece su propio apartado, porque el síntoma
apunta a cualquier lado menos al culpable.

Además de `timelineFrameRate` existe `timelinePlaybackFrameRate`, que es
a qué velocidad sale la timeline por el visor. **No se arrastra cuando
uno cambia el de la timeline**, ni siquiera en un proyecto recién creado
y vacío, y `SetSetting` lo rechaza siempre: devuelve `False` con todas
las variantes (`"60"`, `"60.0"`, `"59.94"`). Sale de las preferencias de
Resolve del usuario, no del proyecto.

Con la timeline a 60 y la reproducción a 50, **el video se reproduce al
83% de su velocidad**: de cada seis cuadros muestra cinco. Lo que se oye
es la voz arrastrada y entrecortada, que suena a problema de rendimiento
o de códec y no lo es.

Como no se puede arreglar por script, **la salida es al revés: armar la
timeline al ritmo al que ese Resolve ya reproduce**, en vez de pelearse
con el ajuste. Conviene leer los dos valores antes de empezar y, si no
coinciden, decidir con eso en la mano.

---

## 7 ter. Un clip a otro ritmo que la timeline NO se ralentiza

Es el miedo razonable al llegar acá, y conviene saber que no pasa,
porque si no uno fuerza la timeline al ritmo del clip sin necesidad.

Medido: un tramo de 600 cuadros de un clip de 60 (diez segundos reales)
puesto en una timeline de 50 ocupa **500 cuadros, o sea los mismos diez
segundos**. Resolve descarta cuadros y conserva la duración y el audio.
El movimiento queda algo menos fluido y nada más.

Esto quiere decir que los `startFrame` y `endFrame` se calculan siempre
**en cuadros del clip**, con el ritmo del clip, sin importar a qué ritmo
vaya la timeline. Resolve hace la conversión.

---

## 8. Los tramos se mandan todos juntos

`AppendToTimeline` acepta una lista de tramos en una sola llamada:

```python
pedido = [{"mediaPoolItem": clip, "startFrame": a, "endFrame": b}
          for a, b in cortes]
pool.AppendToTimeline(pedido)
```

De a uno también funciona, pero cada llamada tiene su ida y vuelta con
el programa y en un video con doscientos cortes la diferencia es de
minutos. Conviene igual comparar `len(puestos)` contra `len(cortes)`,
porque Resolve puede aceptar unos y descartar otros en silencio.

---

## 9. Un video vertical dice que mide 1920x1080

ffprobe informa el tamaño del cuadro **antes** de aplicar la rotación.
Un video de móvil o de cámara grabado en vertical sale como
`width=1920, height=1080` y hay que mirar aparte el dato de rotación:

```
ffprobe -v error -select_streams v:0 \
  -show_entries stream_side_data=rotation -of default=noprint_wrappers=1 archivo
```

Con `rotation=-90`, lo que se ve en pantalla es **1080 de ancho por 1920
de alto**. Resolve sí lo informa ya girado en
`clip.GetClipProperty("Resolution")`, así que ante la duda, ése es el
que dice la verdad.

Importa porque montar material vertical en una timeline horizontal
obliga a Resolve a rotar y escalar cada cuadro en tiempo real, encima de
decodificar, y es una de las cosas que hacen que la reproducción se
arrastre. Y porque preguntar "¿4K o Full HD?" dando por sentado que es
horizontal lleva a configurar el proyecto al revés.

---

## 10. Las copias optimizadas no se pueden generar por script

No hay nada en la API para lanzar *Generate Optimized Media*. Lo único
que hay es `LinkProxyMedia(ruta)`, `LinkFullResolutionMedia(ruta)` y
`UnlinkProxyMedia()`, que sirven para enganchar archivos que uno ya
generó por su cuenta, no para pedirle a Resolve que los haga.

Así que eso hay que pedirlo a mano, y conviene saberlo antes de prometer
que todo se puede automatizar.

Peor: **cambiar la resolución del proyecto invalida las copias
optimizadas que ya estaban hechas**. `clip.GetClipProperty("Optimized
Media")` pasa a decir `None` y Resolve vuelve a decodificar el original.
Si alguien acaba de esperar un rato largo generándolas, tocarle la
resolución después le tira ese trabajo a la basura. Los ajustes del
proyecto se dejan como van a quedar **antes** de generar nada.

---

## 11. Borrar un clip de una pista se puede llevar clips de OTRA

Esto rompió trabajo de verdad el 13/09/2026 y es la razón para no
confiarse con nada de lo de arriba.

Reemplazar el clip de una pista superior parece inocente:

```python
viejo = timeline.GetItemListInTrack("video", 2)
timeline.DeleteClips(viejo)          # <- asi no
```

Después de hacer eso dos veces, la **pista 1** había pasado de 39 clips
a 27, y la línea de tiempo de 2:16 a 1:31. Se perdieron doce tramos del
tramo final, en una pista que nadie había tocado.

La documentación dice que `DeleteClips([items], Bool)` hace borrado en
cascada sólo si el segundo argumento es `True`, y que por defecto es
`False`. En la práctica no se comportó así, de modo que **el segundo
argumento se pasa siempre y de forma explícita**:

```python
timeline.DeleteClips(viejo, False)
```

Y la regla que de verdad protege, porque vale aunque la causa fuera
otra: **después de cualquier operación que borre algo, hay que contar
los clips de TODAS las pistas y comparar con lo que había antes.** No
alcanza con mirar que la operación devolviera `True`, ni con comprobar
la pista sobre la que se estaba trabajando. El daño fue visible sólo
porque un `print` de control imprimía de paso cuántos clips tenía la
pista de abajo.

Antes de reemplazar algo en una línea de tiempo que ya tiene trabajo
encima, conviene además **guardar el estado en un archivo**: para cada
clip, su posición dentro del material y sus propiedades (`ZoomX`,
`ZoomY`, `Pan`, `Tilt`, `Opacity`). Con eso, rehacerla desde cero deja
de ser una pérdida: los ajustes hechos a mano se vuelven a aplicar
buscando cada clip **por el segundo del original en el que empieza**, y
no por su número de orden, que cambia en cuanto falta uno.

---

## 12. En una pista que ya tiene algo, no deja poner otro clip

> **Corrección del 02/10/2026, Resolve 21.0.2:** ya no pasa. Dos textos
> en la misma pista con dos llamadas separadas entraron los dos, y 298
> clips se pegaron detrás de los que ya había en V1 y A1. Se deja lo de
> abajo como historia; si vuelve a aparecer, la salida sigue siendo una
> pista por apoyo.

`AppendToTimeline` con `recordFrame` y `trackIndex` coloca un clip en un
punto concreto de una pista, y funciona perfectamente **la primera vez**.
Para meter un segundo clip en esa misma pista, aunque sea en un hueco
que está libre y lejos del primero, devuelve `[None]` y no pasa nada.

La salida es dar a cada apoyo **su propia pista**:

```python
timeline.AddTrack("video")
pool.AppendToTimeline([{... "trackIndex": 3, "recordFrame": inicio}])
```

Que además sale mejor de lo que parece: con una pista por apoyo, cada
uno se enciende y se apaga por separado desde la interfaz.

---

## 13. `SetLUT` sólo acepta tablas que Resolve ya encontró

La tabla de color se le pasa con la ruta entera, así que parece que puede
estar en cualquier lado. No: si el `.cube` no vive **dentro de la carpeta
de LUTs de Resolve**, `SetLUT` devuelve `False` y, como siempre, sin
decir por qué.

En Windows esa carpeta es:

    C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT

Se puede usar una subcarpeta propia ahí adentro, y se escribe sin permisos
de administrador. Después de dejar el archivo hay que avisarle a Resolve
de que existe, o tampoco lo encuentra:

```python
proyecto.RefreshLUTList()
item.SetLUT(1, str(ruta_absoluta_dentro_de_esa_carpeta))
```

Conviene además guardar una copia de la tabla al lado del script, porque
la carpeta del programa se la lleva puesta cualquier reinstalación.

Para sacarla: `item.SetLUT(indice, "")`, que sí funciona y deja el clip
exactamente como estaba. Medido: la pantalla volvió del 0,568 al 0,451
de origen, al tercer decimal.

---

## 14. `ExportStills` no crea la carpeta de destino

Y devuelve `True` igual. Se queda uno mirando una carpeta que no existe
con la sensación de que la exportación anduvo, porque la llamada dijo
que sí.

```python
pathlib.Path(carpeta).mkdir(parents=True, exist_ok=True)   # primero
album.ExportStills([still], carpeta, prefijo, "png")
```

Vale la pena saber lo demás de este camino, porque es **la única forma
de ver lo que hay en la línea de tiempo**:

```python
tl.SetCurrentTimecode("01:00:28:00")
still = tl.GrabStill()                       # sólo desde la página color
album = proyecto.GetGallery().GetCurrentStillAlbum()
album.ExportStills([still], carpeta, "antes", "png")
album.DeleteStills([still])                  # para no llenarle la galería
```

Sale un PNG del tamaño de la línea de tiempo, ya compuesto y con las
correcciones puestas. Al lado deja un `.drx`, que es la corrección de
ese fotograma; el cuerpo del `.drx` va comprimido en binario, así que
sirve para volver a aplicar un ajuste pero no para escribirlo a mano.

---

## 15. Un título no tiene punto de entrada

`GetLeftOffset()` devuelve `None` en cualquier clip que no salga de un
archivo: un título, un generador, una barra de color. `GetMediaPoolItem()`
también devuelve `None` o un item sin ruta.

Parece un detalle y no lo es: `respaldar-edicion` recorría los clips
dividiendo `GetLeftOffset()` por el ritmo, y **un solo título que Juani
había puesto en la pista 2 tiraba el respaldo entero**, justo antes de
tocar la edición, que es el momento en que menos se puede estar sin red.
Arreglado el 14/09/2026.

La regla general: de un clip de la línea de tiempo, lo único que siempre
contesta es `GetName()`, `GetStart()`, `GetEnd()` y `GetDuration()`.
Todo lo demás puede venir vacío.

---

## 16. Recien abierto, Resolve dice que hay un proyecto y no deja tocarlo

Descubierto el 18/09/2026 al hacer que el programa abriera Resolve solo,
en vez de pedirle al usuario que lo abriera.

Con Resolve recien arrancado, el gestor de proyectos esta delante y la
API contesta lo siguiente:

    resolve.GetCurrentPage()              -> None
    projectManager.GetCurrentProject()    -> "Untitled Project"

O sea que **dice que hay un proyecto abierto y no lo hay**: lo que hay es
el gestor en pantalla. Cualquier codigo que confie en `GetCurrentProject`
para decidir que ya esta todo listo se queda esperando en la puerta.

Y visto desde la API es **indistinguible de tener Preferences abierto**,
que es el otro caso en que la pagina queda vacia. La diferencia se saca
mirando el proyecto: en el arranque se llama `Untitled Project` y tiene
cero lineas de tiempo.

Lo que NO saca a Resolve de ahi, probado:

```python
resolve.OpenPage("edit")             # devuelve None, no pasa nada
gestor.LoadProject("Untitled Project")  # devuelve True, no pasa nada
```

Recargar el proyecto que ya figura como abierto no hace nada. **Lo unico
que cierra el gestor es entrar a un proyecto DISTINTO**, sea cargando uno
que exista o creando uno nuevo:

```python
gestor.CreateProject("lo que sea")   # y la pagina pasa a 'cut'
```

Detalle util: una vez que se salio del gestor, ya no se vuelve a ese
estado. Cerrando el proyecto con `CloseProject`, la pagina se queda en la
que estaba y el proyecto actual vuelve a ser `Untitled Project`, pero
esta vez si se puede trabajar. El estado raro es exclusivo del arranque.

---

## 17. Las banderas son del clip de origen, no del tramo

La mas cara de las nuevas, porque el resultado se ve bien hasta que se
mira de cerca.

`TimelineItem.AddFlag(color)` figura en el SDK como metodo del item de la
linea de tiempo, y devuelve `True` sobre el item que uno le pasa. Pero la
bandera **se guarda en el clip del media pool**, no en el tramo. En un
video cortado en pedazos, que es el caso normal de cualquier montaje,
todos los tramos salen del mismo archivo, asi que:

```python
items[1].AddFlag("Red")
[it.GetFlagList() for it in items]
# -> [['Red'], ['Red'], ['Red'], ['Red']]
```

Se marco uno y quedaron los cuatro. Y `ClearFlags` se comporta igual, o
sea que tampoco se puede limpiar uno solo.

**Lo que si es de cada tramo es el color de clip**, que ademas se ve
mejor porque pinta el clip entero en la linea de tiempo:

```python
items[1].SetClipColor("Orange")
[it.GetClipColor() for it in items]
# -> ['', 'Orange', '', '']
```

Los marcadores (`AddMarker`) tambien son de cada tramo, comprobado en la
misma prueba.

Ojo con los nombres de los colores, que son **dos juegos distintos**. Los
de bandera son Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia,
Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream. Los de clip son
Orange, Apricot, Yellow, Lime, Olive, Green, Teal, Navy, Blue, Purple,
Violet, Pink, Tan, Beige, Brown, Chocolate. Pasarle un color del juego
equivocado devuelve `False` y, como siempre, no explica nada.

Y entre los de clip **no hay rojo**: `SetClipColor("Red")` devuelve
`False` (comprobado en Resolve 21, el 02/10/2026). Cuando Juani pide un
clip en rojo, lo mas cercano es el naranja, y el rojo va en un marcador,
que si lo admite.

---

## 18. Un proxy sin el codigo de tiempo del original se rechaza

`MediaPoolItem.LinkProxyMedia(ruta)` devuelve `False` si la copia
liviana no arranca en el mismo codigo de tiempo que el original. ffmpeg
no lo copia solo: las copias salen en `00:00:00:00`, y las camaras Sony
graban con el reloj del dia (`03:21:01:22`). Coincidir en tamano de
cuadro, ritmo, duracion y pistas de audio no alcanza.

Se arregla pasandole a ffmpeg `-timecode` con el del original, que en
los `.MP4` de Sony esta en la pista de datos (`tmcd`), no en la de video.
A una copia ya hecha se le puede poner sin recodificar:
`ffmpeg -i copia.mov -map 0 -c copy -timecode 03:21:01:22 nueva.mov`.

Paso el 02/10/2026: Resolve rechazo las once copias de un montaje y el
programa siguio como si nada, con un aviso por clip que se pierde entre
el resto. Desde entonces `proxies.py` lo copia siempre.

---

## 19. `GetSourceStartFrame` a veces miente por un cuadro

Para saber donde empieza un tramo dentro del material hay dos llamadas,
y no dan lo mismo:

```python
item.GetSourceStartFrame()   # 3153
item.GetLeftOffset()         # 3154  <- el bueno
```

`GetLeftOffset` es el que coincide con el audio y con lo que se pidio al
armar. Rearmando una linea de tiempo con `GetSourceStartFrame`, unos
ochenta clips de trescientos quedaron corridos un cuadro respecto de su
sonido. Para el final, `GetLeftOffset() + GetDuration()`.

---

## 20. En una pista bloqueada, `DeleteClips` devuelve `False` y nada mas

Si la pista tiene el candado puesto, borrar un clip de ella no hace nada
y devuelve `False`, sin decir que es por el candado. Se mira con
`timeline.GetIsTrackLocked("audio", 2)` y se quita con
`timeline.SetTrackLock("audio", 2, False)`.

Juani bloquea la pista de la musica mientras corta, para que sus cortes
no la partan. Por eso, al reemplazar la musica: se desbloquea, se cambia
y **se vuelve a bloquear**, que es como el la tenia. Paso el 02/10/2026.

---

## 21. Conectarse antes de tiempo deja a Resolve sin scripting

Si el script abre Resolve y se pone a llamar a `scriptapp("Resolve")`
mientras arranca, Resolve abre normal pero no contesta nunca: la primera
llamada se queda trabada y las siguientes dan `None`. La causa se lee en
`Support\logs\ResolveDebug.txt`: Resolve lanza su servidor de scripting
(`fuscript.exe -s`, que escucha en el puerto 1144), el servidor recibe
la conexion a medio hacer que dejo el script y muere con
`RemoteApp::Connect ... ioctlsocket(block) err 1`. Resolve lo relanza
dos veces mas, se rinde ("Failed to connect to script server") y ya no
atiende a nadie hasta cerrarlo.

El 02/10/2026 parecio que la causa era lanzarlo colgado de la consola, y
lanzarlo suelto contesto una vez. El 06/10/2026 volvio a fallar suelto,
tres de tres, y tambien abriendolo a traves del Explorador. Lo que lo
arreglo fue no tocar el puerto hasta que el servidor escucha: se mira la
tabla de `netstat` sin conectarse, y recien con el 1144 escuchando se
llama a `scriptapp`. Asi contesto a los 24 y a los 31 segundos, dos de
dos, por el mismo camino que fallaba. Esta en `resolve/conexion.py`,
`_servidor_escuchando`.

---

## 22. Un título de Fusion siempre cae en la pista 1, partiendo el video

`timeline.InsertFusionTitleIntoTimeline("Text+")` mete el título en la
pista de video 1, en el cursor, como edición de inserción: parte el clip
de abajo y empuja todo lo que viene después, así que la imagen queda
corrida respecto del sonido. Con la pista 1 bloqueada devuelve `None` y
no lo pone en ninguna otra, y no hay forma de elegir la pista de
destino. Medido el 02/10/2026.

Por eso los textos se dibujan con ffmpeg en un `.mov` transparente
(ProRes 4444) y se colocan con `AppendToTimeline` en su propia pista,
que sí respeta `trackIndex` y `recordFrame`.

---

## 23. Exportar por script funciona derecho

`SetCurrentRenderFormatAndCodec("mp4", "H264_NVIDIA")`, después
`SetRenderSettings` con `SelectAllFrames`, `TargetDir` y `CustomName`,
después `AddRenderJob`, `StartRendering([trabajo], False)`, y mientras
`IsRenderingInProgress()`, `GetRenderJobStatus(trabajo)` da el
porcentaje. Al final, `DeleteRenderJob` para no dejar la cola sucia.
`GetRenderCodecs("mp4")` dice qué codificadores hay: en esta máquina
también están los de NVIDIA, mucho más rápidos.

## 24. El video de iPhone viene con ritmo variable, y descuadra todo

El iPhone graba con ritmo variable (VFR): ffprobe da `r_frame_rate`
60000/1001 pero `avg_frame_rate` distinto (2631000/43877), y Resolve
cuenta otra cantidad de cuadros que ffmpeg (9008 contra 9002 en un clip
de 2:30). Dos síntomas, ninguno con error:

- `LinkProxyMedia` devuelve `False` con todas las copias, aunque
  lleven el mismo ritmo, duración y cuadros que dice ffprobe.
- La imagen (del video) y el sonido (del `.wav` nivelado) se van
  corriendo a lo largo de cada clip: 15 cuadros al final de uno de 4
  minutos. `desalineados()` lo delata.

Se arregla pasando los originales a ritmo fijo **antes** de montar
(`-fps_mode cfr -r 60000/1001 -c:v libx264 -crf 16 -c:a copy`) y
montando sobre esas copias. Con eso las copias livianas entran y los 31
tramos quedaron alineados al cuadro. Pasó el 18/10/2026 con un video
para Casio.

---

## Y la forma de no perder nada: exportar antes de tocar

`ProjectManager.ExportProject(nombre, ruta)` guarda el proyecto entero
en un `.drp` que se vuelve a meter desde la ventana de proyectos con
botón derecho e *Import*, y entra como un proyecto aparte sin pisar
nada. `Timeline.Export(ruta, resolve.EXPORT_DRT)` hace lo mismo con una
línea de tiempo sola.

Conviene pasarlo **antes de tocar una edición que ya tiene trabajo
hecho a mano**, y conviene acompañarlo de un volcado a JSON de cada
clip con sus propiedades, porque el `.drp` se restaura entero o nada:
si lo que hay que recuperar son los recortes de catorce clips
conservando lo demás, el que sirve es el JSON.

Eso está hecho en `_comunes/respaldar-edicion.bat`.

---

## Lo que sí avisa

Para no quedar con la idea de que nada funciona: crear timelines,
borrarlas (`DeleteTimelines`), sacar clips del pool (`DeleteClips`),
cambiar de página y leer propiedades anduvo todo a la primera y devuelve
`True` o `False` de forma confiable. El problema está concentrado en
importar, en armar y en los ajustes del proyecto.

## Lo que la API no hace

No reproduce el video ni opina sobre él. Pero **sí saca fotogramas
sueltos**, que es lo del punto 14, y con eso alcanza para medir: cuánto
mide una pantalla, si una corrección hizo lo que decía, dónde cae un
encuadre. Antes del 14/09/2026 esto estaba escrito como que lo visual
quedaba entero fuera de alcance, y no es cierto.

Lo que sigue fuera es el criterio: si una toma quedó bien, dónde poner un
zoom, cuánto de fuerte es demasiado. Eso es de Juani. Lo que rinde del
lado del script es lo mecánico y lo medible.

---

## Y una que no es de Resolve pero sale siempre con ella

**Detectar silencio no es lo mismo que detectar que nadie habla**, y
confundirlos arruina el resultado aunque todo lo demás esté bien.

El filtro `silencedetect` de ffmpeg mide volumen. Con él, un teclado, un
golpe en la mesa, una silla o el aire acondicionado superan el umbral y
se conservan como si fueran habla. En el video con el que se probó esto,
una demostración de calculadora, los primeros treinta y cinco segundos
no tenían una sola palabra y sobrevivieron enteros, troceados en
pedacitos de un segundo.

Lo que corresponde usar es un detector de voz. El de Silero viene dentro
de `faster-whisper`, que ya está instalado en
`herramientas/transcribir-audios/.venv`, y no hace falta transcribir nada para
usarlo:

```python
from faster_whisper.vad import get_speech_timestamps, VadOptions
tramos = get_speech_timestamps(audio, VadOptions(threshold=0.5),
                               sampling_rate=16000)
```

El audio se le da plano, a 16 kHz y en un solo canal, que es como fue
entrenado. Sobre el mismo video, pasó de 65 tramos a 39.

**Ojo con los dos Python.** El motor de voz vive en ese entorno virtual,
que está hecho sobre el Python de Microsoft Store, y ése es justamente
el que no puede abrir la librería de Resolve. Son dos Python que no
pueden ser el mismo. La solución que quedó es que el programa principal
lance al otro como un proceso aparte y le lea la respuesta en JSON, en
vez de intentar tener todo en uno.

