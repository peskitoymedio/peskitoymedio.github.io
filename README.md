# Peskito y Medio

Sitio web del podcast **Peskito y Medio**, un programa de amig@s frikis que hablan de series, cómics, ciencia ficción, fantasía, juegos de mesa, doramas, bandas sonoras, rol, Marvel y DC, Star Wars, Cthulhu y muchas cosas más.

- **Web:** <https://peskitoymedio.github.io/>
- **Podcast en iVoox:** <https://www.ivoox.com/podcast-peskito-medio-tu-podcast-friki_sq_f1661614_1.html>
- **Repositorio:** <https://github.com/peskitoymedio/peskitoymedio.github.io>

Es una web estática: no hay servidor, base de datos ni proceso de compilación. Todo el contenido de los episodios se genera a partir del feed RSS oficial del podcast.

## Características

- Archivo completo de episodios con portada, número, tipo, fecha, duración y descripción.
- Una **página propia por episodio** (`episodios/<slug>.html`) con sus notas completas, ficha rápida, reproductor, navegación anterior/siguiente y episodios relacionados.
- Datos estructurados `PodcastEpisode`, `BreadcrumbList` y `CollectionPage` para mejorar el SEO y los resultados enriquecidos.
- Archivo estático navegable en `episodios/index.html`, con enlaces reales a todas las fichas.
- Descripciones completas en HTML que se muestran recortadas y se pueden desplegar bajo demanda.
- Filtros por **programas**, **especiales**, **promos** y **colaboraciones**, además de buscador por texto.
- Reproductor integrado que usa los MP3 publicados en el feed.
- Vídeo de presentación incrustado desde YouTube.
- Sección de reconocimientos con los premios de la Asociación Podcast y los rankings de Goodpods.
- Contadores de episodios y de cada categoría calculados en tiempo real.
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
- Un `BreadcrumbList` que coincide con las migas de pan visibles.
- Enlaces de navegación al episodio anterior/siguiente, a otros episodios relacionados y al archivo completo.

`episodios/index.html` es el archivo completo, renderizado como HTML estático (no depende de JavaScript), de modo que los buscadores siempre tienen un camino de enlaces hacia todas las fichas. La parrilla de la portada también enlaza cada tarjeta con su página.

El `slug` se guarda en `js/episodes.js`. Mientras el título no cambie, la URL se mantiene estable entre actualizaciones. Si un episodio nuevo coincide con otro slug, se añade un sufijo numérico.


## Contenido de los episodios

Los datos viven en `js/episodes.js`, en el array `EPISODES`. Cada entrada incluye el identificador de iVoox, el número de programa, el tipo, el título, la fecha, la duración, el enlace, la portada local, la URL del audio, un resumen corto (`desc`), la descripción completa en HTML (`descHtml`) y el `slug` de su página.

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

También genera `desc`, un resumen en texto plano de unas 190 letras. La web muestra ese resumen recortado y, si la descripción tiene más contenido o enlaces, añade un botón **Leer más** para desplegar el HTML completo sin salir de la tarjeta.

### Portadas

Las portadas se descargan a `img/episodes/` y se guardan con un nombre estable basado en el ID de iVoox: `ep-<id>.jpg`. Así, volver a ejecutar la actualización nunca duplica ni pisa imágenes de otros episodios. Las portadas antiguas conservan su nombre original.

`feed.xml` y `episodes-raw.json` son copias de referencia del último feed descargado.

## Actualización automática

El workflow `.github/workflows/actualizar-pages.yml` mantiene la web al día sin intervención manual. Se ejecuta cada seis horas, al lanzarlo a mano desde la pestaña **Actions** y en cada push a `main` o `master`.

En las ejecuciones programadas y manuales:

1. Descarga el feed oficial del podcast desde Feedburner.
2. Ejecuta `actualizar.py`, que detecta los episodios que aún no están en la web.
3. Descarga y optimiza las portadas nuevas, regenera `js/episodes.js` y crea o actualiza las páginas de `episodios/`.
4. Actualiza `sitemap.xml` con la portada, el archivo y una URL por episodio.
5. Si hay cambios, hace commit y push de los datos y las páginas actualizadas.
6. Publica el sitio en GitHub Pages con `actions/deploy-pages`.

Los push solo despliegan el contenido, sin ejecutar la actualización, para evitar bucles de commits.

### Notas de despliegue

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
robots.txt              Directrices para buscadores
sitemap.xml             Mapa del sitio con la portada, el archivo y cada episodio
css/styles.css          Estilos, variables de diseño y adaptación a móvil
css/episodio.css        Estilos de las fichas de episodio y del archivo
js/main.js              Renderizado, filtros, buscador, navegación y reproductor de la portada
js/episode.js           Reproductor y navegación de las fichas de episodio
js/episodes.js          Datos de los episodios (generado automáticamente)
img/episodes/           Portadas de los episodios
img/                    Logo, iconos y favicons
actualizar.py           Actualizador desde el feed del podcast (datos y páginas)
actualizar.bat          Lanzador para Windows
feed.xml                Última copia del feed descargado
episodes-raw.json       Última copia de los datos crudos del feed
.github/workflows/      Workflow de actualización y despliegue
```

## Tecnologías

- HTML5 semántico y CSS3 con variables, grid y flexbox.
- JavaScript sin frameworks ni compilación.
- Tipografías [Bangers y Outfit](https://fonts.google.com/) desde Google Fonts.
- Iconos de [Font Awesome](https://fontawesome.com/).
- GitHub Actions y GitHub Pages para la actualización y el alojamiento.

## Créditos

Los audios, portadas, títulos y descripciones pertenecen a **Peskito y Medio** y se obtienen de su feed oficial. La web es un proyecto hecho por un peskite para la comunidad.

El código puede reutilizarse libremente; los contenidos del podcast conservan los derechos de sus autores.
