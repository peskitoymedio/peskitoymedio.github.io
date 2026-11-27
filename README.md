# Peskito y Medio

Sitio web del podcast **Peskito y Medio**, un programa de amig@s frikis que hablan de series, cómics, ciencia ficción, fantasía, juegos de mesa, doramas, bandas sonoras, rol, Marvel y DC, Star Wars, Cthulhu y muchas cosas más.

- **Web:** <https://www.peskitoymedio.es/>
- **Podcast en iVoox:** <https://www.ivoox.com/podcast-peskito-medio-tu-podcast-friki_sq_f1661614_1.html>
- **Repositorio:** <https://github.com/peskitoymedio/peskitoymedio.github.io>

Es una web estática: no hay servidor, base de datos ni proceso de compilación. Todo el contenido de los episodios se genera a partir del feed RSS oficial del podcast.

## Características

- Archivo completo de episodios con portada, número, tipo, fecha, duración y descripción.
- Una **página propia por episodio** (`episodios/<slug>.html`) con sus notas completas, ficha rápida, reproductor, navegación anterior/siguiente y episodios relacionados. La ficha rápida incluye enlaces para comentar en iVoox, en X y en Telegram.
- Enlace directo a cada episodio en Spotify, guardado en `spotify_cache.json` y actualizado automáticamente.
- **Secciones con minutaje** en las fichas de episodio, leídas de los capítulos Podlove (`psc:chapters`) del feed. Al pulsar una sección, el reproductor salta a ese instante y empieza a sonar. Si el capítulo trae enlace o imagen, también se muestran junto a la sección.
- **Transcripciones**: cada ficha muestra, en un bloque desplegable, la transcripción completa del episodio con los minutajes (al pulsar un párrafo, el reproductor salta a ese instante) y un buscador para filtrar el texto dentro de la transcripción.
- **Minutajes dentro de las descripciones**: las líneas que incluyen una marca de tiempo se destacan y, al pulsarlas, el reproductor salta a ese instante. Al final de las notas aparece un botón **Escucha el episodio en iVoox**.
- Datos estructurados `Organization`, `WebSite`, `PodcastSeries` (con `hasPart` de los últimos episodios), `PodcastEpisode`, `BreadcrumbList`, `CollectionPage` e `ItemList` para mejorar el SEO y la comprensión del sitio.
- Archivo estático navegable en `episodios/index.html`, con enlaces reales a todas las fichas.
- Descripciones completas en HTML que se muestran recortadas y se pueden desplegar bajo demanda.
- Filtros por **programas**, **especiales**, **promos** y **colaboraciones**, además de buscador por texto, tanto en la portada como en el archivo completo. El buscador del archivo incluye las notas completas de cada episodio (ocultas visualmente) para encontrar cualquier tema mencionado.
- Reproductor integrado que usa los MP3 publicados en el feed.
- Vídeo de presentación incrustado desde YouTube.
- Sección de reconocimientos con los premios de la Asociación Podcast y los rankings de Goodpods.
- Contadores de episodios y de cada categoría calculados en tiempo real.
- **Juego de Bandas Sonoras** (`juegos/juegobsos/`): minijuego online para adivinar películas a partir de fragmentos de sus bandas sonoras. Banco de 89 películas frikis, 10 rondas, puntuación por acierto y rapidez, modo de dificultad (3/5/10 segundos), tarjeta de resultado para compartir y descargar, audio preview vía iTunes API sin almacenar archivos en el servidor y ranking online (diario, semanal e histórico).
- Diseño adaptable a móvil, tableta y escritorio, con una estética de cómic y aire friki.
- Navegación por teclado, textos alternativos y contraste cuidado.
- Sin dependencias de JavaScript: solo HTML, CSS y JS del navegador.

## SEO y páginas de episodio

Cada episodio tiene su propia URL estable, generada a partir de su título:

```
episodios/pym-63-pikmin-bloom-festival-...html
```

Cada ficha incluye:

- `<title>` y `<meta name="description">` propios.
- `link rel="canonical"` absoluta y metadatos Open Graph/Twitter.
- Un bloque JSON-LD `PodcastEpisode` con `partOfSeries`, `episodeNumber`, `datePublished`, `duration` en ISO 8601, `image`, `associatedMedia` y `author`.
- Cuando hay transcripción, `associatedMedia.transcript` con la URL del fichero SRT y `accessibilityFeature: transcript`.
- Un `BreadcrumbList` que coincide con las migas de pan visibles.
- Enlaces de navegación al episodio anterior/siguiente, a otros episodios relacionados y al archivo completo.

`episodios/index.html` es el archivo completo, renderizado como HTML estático (no depende de JavaScript), de modo que los buscadores siempre tienen un camino de enlaces hacia todas las fichas. La parrilla de la portada también enlaza cada tarjeta con su página.

La entidad `Organization` (con logo y redes) se declara en la portada y se referencia desde `WebSite`, `PodcastSeries` y las fichas mediante `@id`. El actualizador mantiene solos `PodcastSeries.hasPart` (últimos 6 episodios) y el `ItemList` del archivo, que incluye nombre, portada, fecha y duración de cada episodio.

El `slug` se guarda en `js/episodes.js`. Mientras el título no cambie, la URL se mantiene estable entre actualizaciones. Si un episodio nuevo coincide con otro slug, se añade un sufijo numérico.


## Transcripciones

Cada ficha incluye la transcripción completa del episodio en un bloque desplegable. El actualizador la integra en el HTML (para que sea indexable y accesible) y declara en el JSON-LD la URL del fichero SRT dentro de `associatedMedia.transcript`.

La fuente es [PodTranscript](https://www.pod-transcript.com/podcast/1453280178), que expone la transcripción completa del programa (la que genera Apple Podcasts) en formato SRT, con los tiempos de cada fragmento.

Cómo funciona:

1. `actualizar.py` consulta el catálogo de episodios de PodTranscript (`/api/podcasts/1453280178/episodes`) y asocia cada episodio con su GUID de iVoox.
2. Para cada episodio sin fichero local, pide la transcripción (`/api/podcasts/1453280178/transcript?episodeGuid=...`) y la guarda como SRT en `transcripciones/<id>.srt`.
3. La ficha lee ese SRT, agrupa los fragmentos en párrafos legibles y los pinta con su minutaje. Cada párrafo es un botón: al pulsarlo, el reproductor salta a ese instante.
4. Encima del bloque hay un buscador que filtra la transcripción en vivo: muestra solo los párrafos que contienen el texto buscado, los resalta y cuenta las coincidencias. Ignora mayúsculas y acentos (`numero` encuentra `número`).

El `<id>` es el número que aparece en la URL de iVoox del episodio, después de `_rf_`:

```
https://www.ivoox.com/pym-63-...-audios-mp3_rf_183682229_1.html
                                             ^^^^^^^^^
transcripciones/183682229.srt
```

Los ficheros SRT **no** se guardan en `js/episodes.js`: así el archivo que carga el navegador no crece con textos largos. El workflow de GitHub Actions añade `transcripciones/` al commit y copia los SRT a `_site/transcripciones/` (son la URL que declara el JSON-LD en `associatedMedia.transcript`). Cuando aparece una transcripción que antes faltaba, `actualizar.py` añade también el tag `<podcast:transcript>` de Podcast 2.0 al item correspondiente de `util/pre-feedburner.xml` (si ya está, no lo duplica). Así Feedburner la publica en cuanto el SRT está disponible.

Si el fichero ya existe en `transcripciones/`, no se vuelve a descargar. Para regenerarlo basta con borrarlo y ejecutar `python actualizar.py`. Las transcripciones automáticas pueden contener errores de reconocimiento de voz.

Los episodios que no tienen transcripción se anotan en `transcripciones/ausentes.json` con la fecha de la comprobación. Los **episodios recientes** (publicados en los últimos 60 días) se vuelven a consultar en **cada actualización**, porque el servicio puede publicar la transcripción días después de salir el episodio; los antiguos solo se reconsultan cada 30 días. En cuanto PodTranscript tiene la transcripción, se descarga, se borra de `ausentes.json` y la ficha la muestra.


## Contenido de los episodios

Los datos viven en `js/episodes.js`, en el array `EPISODES`. Cada entrada incluye el identificador de iVoox, el número de programa, el tipo, el título, la fecha, la duración, el enlace, la portada local, la URL del audio, un resumen corto (`desc`), la descripción completa en HTML (`descHtml`), los capítulos Podlove (`chapters`) y el `slug` de su página.

Cada capítulo guarda su `start`, su `title` y, cuando el feed los incluye, su `href` e `image`. Las imágenes de capítulos se descargan a `img/chapters/` para servirlas desde el propio sitio.

Ese archivo se regenera automáticamente desde el feed; no se edita a mano. Las páginas de `episodios/` también se generan desde el mismo proceso.

### Clasificación

| Tipo | Regla |
|---|---|
| Promo | El título empieza por «Promo» |
| Colaboración | El título no empieza por `PYM` (y no es una promo) |
| Especial | El título empieza por `PYM` y contiene la palabra «Especial» con la E mayúscula (distingue mayúsculas de minúsculas) o la expresión «Star Wars Special» |
| Programa | Cualquier otro episodio de `PYM` |

### Descripciones

El feed entrega las descripciones en HTML. El actualizador conserva una versión completa y segura en `descHtml`: elimina las imágenes, los scripts y cualquier etiqueta no permitida, y retira la promo de los Premios iVoox que encabeza algunas descripciones. Los enlaces se mantienen y se abren en una pestaña nueva.

También limpia el bloque final de autopromoción (**Enlace al programa en iVoox**, **Síguenos en nuestras redes sociales** y **Suscríbete en iVoox y dale a Me gusta**) y convierte cada línea con minutaje en un control que salta al instante correspondiente del reproductor. En la ficha del episodio, ese bloque se sustituye por el botón **Escucha el episodio en iVoox**.

También genera `desc`, un resumen en texto plano de unas 190 letras. La web muestra ese resumen recortado y, si la descripción tiene más contenido o enlaces, añade un botón **Leer más** para desplegar el HTML completo sin salir de la tarjeta.

### Portadas

Las portadas se descargan a `img/episodes/` y se guardan con un nombre estable basado en el ID de iVoox: `ep-<id>.jpg`. Así, volver a ejecutar la actualización nunca duplica ni pisa imágenes de otros episodios. Las portadas antiguas conservan su nombre original.

`feed.xml` y `episodes-raw.json` son copias de referencia del último feed descargado.

### Enlaces de Spotify

`spotify_cache.json` relaciona cada título con su URL pública de Spotify. En cada actualización, `actualizar.py` consulta la página pública del programa y valida las altas nuevas con la [API oEmbed oficial de Spotify](https://developer.spotify.com/documentation/embeds/reference/oembed). No usa la Web API de pago ni endpoints internos.

La página pública incluye los episodios más recientes, por lo que cada programa nuevo se incorpora automáticamente en su siguiente ejecución. Si Spotify todavía no lo ha publicado o su oEmbed no responde, el enlace queda pendiente y **se reintenta en cada actualización** (cada seis horas), sin impedir la actualización de la web. Para tolerate cambios de título se comparan también los títulos truncados y el número de programa (`PYM 62`, `PYM 4.1`), siempre validando con oEmbed antes de guardar el enlace.

## Juego de Bandas Sonoras

La web incluye un minijuego online autocontenido en `juegos/juegobsos/index.html` para adivinar películas a partir de fragmentos de sus bandas sonoras.

### Datos del juego

| Dato | Valor |
|---|---|
| URL | `https://www.peskitoymedio.es/juegos/juegobsos/` |
| Banco de películas | 89 títulos frikis (cine, animación, sci-fi, cultos, ganadores del Óscar) |
| Rondas por partida | 10 |
| Duración de cada pista | 3 s (Leyenda), 5 s (Normal) o 10 s (Relax) |
| Puntuación | 100 puntos fijos por acierto + hasta 50 de bonus por rapidez (máx. 1500 por ronda) |
| Audio | Previews de iTunes / Apple Music (no se almacena ningún archivo en el servidor) |
| Resultado | Pantalla final con veredicto, resumen de acertadas/falladas y tarjeta para compartir/descargar |

### Cómo funciona

El banco de películas vive en `juegos/juegobsos/peliculas.js` (`window.PELICULAS_BSO`): cada entrada guarda `titulo` y `consulta` (término de búsqueda). Se carga como script en vez de como `.json` para que el juego siga funcionando con `file://`, donde `fetch()` sería bloqueado por CORS. La búsqueda de previews está en `itunes-preview.js` (`itunes.apple.com/search`, JSONP), compartida por el juego y por el laboratorio. Al iniciar una partida se barajan las películas, se cargan hasta 10 previews válidas y se juega ronda por ronda contra el reloj.

Cada ronda muestra:
- Un reproductor animado (vinilo) que se puede pulsar para volver a escuchar la pista.
- Cuatro opciones de respuesta (1 correcta + 3 distractoras aleatorias).
- Una barra de progreso que se agota al tiempo que suena el clip.

Al terminar se muestra una pantalla final con la puntuación, el veredicto ("Maestro Absoluto de las BSOs", etc.), el listado de películas acertadas y falladas, y botones para compartir la tarjeta de resultado en X, WhatsApp, Facebook y Telegram (Web Share API con archivo adjunto cuando el navegador lo permite).

### SEO y metadatos

La página declara `<title>` y `<meta name="description">` propios, `link rel="canonical"` absoluta, y metadatos Open Graph/Twitter con imagen de vista previa (`og-image.png`, 1200×630). Se enlaza desde la navegación principal del sitio y del pie de página.

### Ranking online

La clasificación pública está en `juegos/juegobsos/ranking.html` (enlazada desde el juego) y se alimenta de Supabase mediante las funciones RPC definidas en `supabase-setup.sql`. El cliente compartido es `ranking.js` (`window.PYMRanking`) y las credenciales viven en `config.js`: si están vacías, el juego sigue funcionando y la página de ranking muestra un aviso en lugar de dar error.

| Dato | Valor |
|---|---|
| Pestañas | `diario`, `semanal`, `historico` (hora de `Europe/Madrid`) e `insignias` |
| Fechas pasadas | En Diario y Semanal, selector de periodos con datos + calendario; `p_fecha` en `ranking()`/`puesto_de()` |
| Tamaño | Top 50 por pestaña |
| Usuario | Alias de hasta 24 caracteres; el identificador anónimo se guarda en `localStorage` (`pym-bso-jugador-id`) |
| Mejora | Solo entra la mejor marca del alias en cada periodo; `registrar_puntuacion` devuelve `null` si no la supera |
| Desempate | Menor tiempo de envío (marca más antigua) gana a igual puntuación; el alias se compara sin distinguir mayúsculas |
| Seguridad | Token de un solo uso emitido al pulsar «Dale al play» (≤ 10 min), detalle de las 10 respuestas validado en servidor y puntuación recalculada allí |
| Extras | `periodos_disponibles()` para el selector, contadores de victorias, `puesto_de` para puestos fuera del top 50, tarjeta compartible del récord y detalle de cada partida |

**Rankings pasados:** `ranking(p_periodo, p_fecha)` y `puesto_de(p_alias, p_periodo, p_fecha)` aceptan una fecha (día, o lunes de la semana); `null` = vigente. En una vista pasada, las insignias y la corona se cuentan **solo hasta el final de ese periodo**, no hasta hoy. Los trofeos se reconstruyen desde `puntuaciones` (mejor marca por día/semana, con el mismo desempate que `actualizar_lideres()`), no desde `victorias`, que solo guarda al líder final y no permite recuperar líderes intermedios. En Semanal la fecha se normaliza al lunes ISO de su semana antes de calcular el corte. `periodos_disponibles(p_periodo)` devuelve los días/semanas con partidas para el selector; el calendario permite además ir a cualquier fecha. Con `p_fecha = null` los contadores coinciden con los de `victorias`.

**Pestaña Insignias** (`ranking_insignias()` / `puesto_de_insignias()` en Supabase): incluye alias con al menos una victoria diaria o semanal y, además, al campeón histórico (la corona cuenta como insignia aunque tenga 0 victorias). Columnas: `#`, `Jugador`, `Semanales`, `Diarias`, `Mejor marca` y detalle. Se ordena por **semanales desc, diarias desc y mejor marca histórica desc**. La mejor marca es la mejor puntuación histórica del alias. La corona morada (`fa-crown`, `es_campeon_historico`) distingue al campeón histórico, es decir, el primero de `ranking('historico')` (mismo desempate por fecha), y se muestra en el alias de **todas** las pestañas. El orden de las insignias en el alias es corona → semanal → diaria.

Nota: «el juego», «el ranking», «la clasificación», «el top» o «mi puesto» en este proyecto significan siempre esta sección; no confundir con los rankings de Goodpods ni con las transcripciones de `episodios/`.

### Estructura

```
juegos/juegobsos/
  index.html            Página del juego (HTML, estilos embebidos y lógica JS)
  ranking.html          Clasificación pública (diaria, semanal, histórica e insignias)
  ranking.js            Cliente Supabase compartido por juego y ranking
  config.js             URL y clave pública de Supabase (vacías = ranking off)
  supabase-setup.sql    Esquema, RPC y reglas del ranking (fuente de verdad)
  peliculas.js          Banco externo de películas (titulo + consulta)
  itunes-preview.js     Búsqueda de previews compartida con el laboratorio
  previews.js           Caché/localizador de previews
  generar-previews.py   Generación de la caché de previews
  card-images-local.js  Imágenes locales para la tarjeta de resultado
  lab-bso.html          Laboratorio privado: listado, filtro, test de previews y prueba de descripciones alternativas (noindex + robots.txt)
  og-image.png          Imagen de vista previa para redes sociales
```

## Actualización automática

El workflow `.github/workflows/actualizar-pages.yml` mantiene la web al día sin intervención manual. Se ejecuta cada seis horas, al lanzarlo a mano desde la pestaña **Actions** y en cada push a `main` o `master`.

En las ejecuciones programadas y manuales:

1. Descarga el feed oficial del podcast desde Feedburner.
2. Ejecuta `actualizar.py`, que detecta los episodios que aún no están en la web.
3. Descarga y optimiza las portadas nuevas, actualiza `spotify_cache.json`, regenera `js/episodes.js` y crea o actualiza las páginas de `episodios/`.
4. Actualiza `sitemap.xml` con la portada, el archivo y una URL por episodio.
5. Si hay cambios, hace commit y push de los datos y las páginas actualizadas.
6. Publica el sitio en GitHub Pages con `actions/deploy-pages`.

Los push solo despliegan el contenido, sin ejecutar la actualización, para evitar bucles de commits.

Los datos que llegan tarde no se pierden: en cada pasada se vuelven a comprobar los episodios recientes a los que les falte la URL de Spotify o la transcripción, y el log indica cuáles siguen pendientes.

### Preparación del feed de Feedburner

`actualizar-pre-feedburner.py` lee el feed básico de iVoox (`https://feeds.ivoox.com/feed_fg_f1661614_filtro_1.xml`), toma el episodio más reciente y, si su ID aún no aparece en `util/pre-feedburner.xml`, lo añade en primer lugar con la descripción en HTML, `itunes:summary`, capítulos Podlove, personas, `podcast:socialInteract` y el bloque final de autopromoción. No añade transcripciones: las incorpora después `actualizar.py` cuando el SRT esté disponible. Es idempotente: si el episodio ya está, no escribe nada.

El workflow `.github/workflows/actualizar-pre-feedburner.yml` ejecuta ese script **solo bajo demanda** (pestaña *Actions* → *Run workflow*) y hace commit y push de `util/pre-feedburner.xml` cuando hay cambios. `actualizar.py` añade después la etiqueta `<podcast:transcript>` cuando el SRT está disponible; este workflow solo prepara el item nuevo.

El workflow de Pages copia el fichero a `_site/util/`, de modo que queda publicado en <https://www.peskitoymedio.es/util/pre-feedburner.xml>. Esa es la URL que debe configurarse como **Source Feed** en Feedburner. No se añade a `sitemap.xml` y `robots.txt` lo bloquea para el resto de agentes, con una excepción explícita para `FeedBurner` y `FeedBurner/1.0`: el backend actual de Feedburner aplica `robots.txt` y, sin esa excepción, el source feed quedaría en estado `URL_ROBOTED` y dejaría de actualizarse.

```bash
python actualizar-pre-feedburner.py            # añade el último episodio si falta
python actualizar-pre-feedburner.py --dry-run  # muestra el item generado sin escribir
```

### Notas de despliegue

- El source feed de Feedburner se publica en `/util/pre-feedburner.xml`. No entra en `sitemap.xml` y `robots.txt` evita que lo indexen los buscadores, salvo FeedBurner, que necesita poder leerlo.
- El cron está en UTC y GitHub puede retrasar la ejecución unos minutos.
- Si el repositorio pasa más de 60 días sin actividad, GitHub puede pausar el workflow programado; se reactiva desde la pestaña Actions o lanzándolo a mano.
- El sitio se publica como artefacto con `actions/upload-pages-artifact` y `actions/deploy-pages`. La opción «Deploy from a branch» no es compatible con este flujo, porque los commits hechos con `GITHUB_TOKEN` no disparan builds de Pages.
- El workflow necesita permisos de escritura sobre el contenido del repositorio para poder guardar los episodios nuevos.

## Actualizador manual

`actualizar.py` reproduce el mismo proceso en local. Solo necesita Python 3.9 o superior y conexión a internet; usa únicamente la biblioteca estándar.

```bash
python actualizar.py            # actualiza los datos, las portadas, las páginas y el sitemap
python actualizar.py --dry-run  # muestra qué episodios y páginas cambiarían, sin escribir nada
python actualizar.py --feed RUTA  # usa otro feed local o remoto (para pruebas)
```

Si están disponibles, se usan **Pillow** o **ffmpeg** para reducir las portadas nuevas a unos 600 px y que la web cargue más rápido. Si no lo están, la imagen se guarda tal cual.

En Windows, `actualizar.bat` abre el mismo script con doble clic.

## Estructura

```
index.html              Página principal
episodios/              Una página por episodio + archivo completo (generado)
juegos/juegobsos/       Juego online de bandas sonoras (autocontenido: HTML, CSS y JS)
robots.txt              Directrices para buscadores
sitemap.xml             Mapa del sitio con la portada, el archivo y cada episodio
css/styles.css          Estilos, variables de diseño y adaptación a móvil
css/episodio.css        Estilos de las fichas de episodio y del archivo
js/main.js              Renderizado, filtros, buscador, navegación y reproductor de la portada
js/episode.js           Reproductor y navegación de las fichas de episodio
js/episodes.js          Datos de los episodios (generado automáticamente)
img/episodes/           Portadas de los episodios
img/chapters/           Imágenes asociadas a capítulos (generado)
img/                    Logo, iconos y favicons
actualizar.py           Actualizador desde el feed del podcast (datos y páginas)
actualizar-pre-feedburner.py  Prepara el último episodio en util/pre-feedburner.xml
actualizar.bat          Lanzador para Windows
util/pre-feedburner.xml Source feed de Feedburner (se publica en /util/)
feed.xml                Última copia del feed descargado
episodes-raw.json       Última copia de los datos crudos del feed
spotify_cache.json      Mapa de títulos y enlaces públicos de Spotify
.github/workflows/      Workflow de actualización y despliegue
```

## Tecnologías

- HTML5 semántico y CSS3 con variables, grid y flexbox.
- JavaScript sin frameworks ni compilación.
- Tipografías [Bangers y Outfit](https://fonts.google.com/) desde Google Fonts.
- Iconos de [Font Awesome](https://fontawesome.com/).
- GitHub Actions y GitHub Pages para la actualización y el alojamiento.

## Créditos

Los audios, portadas, títulos y descripciones pertenecen a **Peskito y Medio** y se obtienen de su feed oficial. La web es un proyecto hecho por un peskito para la comunidad.

El código puede reutilizarse libremente; los contenidos del podcast conservan los derechos de sus autores.
