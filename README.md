# Peskito y Medio

Sitio web del podcast **Peskito y Medio**, un programa de amig@s frikis que hablan de series, cómics, ciencia ficción, fantasía, juegos de mesa, doramas, bandas sonoras, rol, Marvel y DC, Star Wars, Cthulhu y muchas cosas más.

- **Web:** <https://peskitoymedio.github.io/>
- **Podcast en iVoox:** <https://www.ivoox.com/podcast-peskito-medio-tu-podcast-friki_sq_f1661614_1.html>
- **Repositorio:** <https://github.com/peskitoymedio/peskitoymedio.github.io>

Es una web estática: no hay servidor, base de datos ni proceso de compilación. Todo el contenido de los episodios se genera a partir del feed RSS oficial del podcast.

## Características

- Archivo completo de episodios con portada, número, tipo, fecha, duración y descripción.
- Descripciones completas en HTML que se muestran recortadas y se pueden desplegar bajo demanda.
- Filtros por **programas**, **especiales**, **promos** y **colaboraciones**, además de buscador por texto.
- Reproductor integrado que usa los MP3 publicados en el feed.
- Vídeo de presentación incrustado desde YouTube.
- Sección de reconocimientos con los premios de la Asociación Podcast y los rankings de Goodpods.
- Contadores de episodios y de cada categoría calculados en tiempo real.
- Diseño adaptable a móvil, tableta y escritorio, con una estética de cómic y aire friki.
- Navegación por teclado, textos alternativos y contraste cuidado.
- Sin dependencias de JavaScript: solo HTML, CSS y JS del navegador.

## Contenido de los episodios

Los datos viven en `js/episodes.js`, en el array `EPISODES`. Cada entrada incluye el identificador de iVoox, el número de programa, el tipo, el título, la fecha, la duración, el enlace, la portada local, la URL del audio, un resumen corto (`desc`) y la descripción completa en HTML (`descHtml`).

Ese archivo se regenera automáticamente desde el feed; no se edita a mano.

### Clasificación

| Tipo | Regla |
|---|---|
| Promo | El título empieza por «Promo» |
| Colaboración | El título no empieza por `PYM` (y no es una promo) |
| Especial | El título empieza por `PYM` y contiene «Especial» |
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
3. Descarga y optimiza las portadas nuevas y regenera `js/episodes.js`.
4. Si hay cambios, hace commit y push de los datos actualizados.
5. Publica el sitio en GitHub Pages con `actions/deploy-pages`.

Los push solo despliegan el contenido, sin ejecutar la actualización, para evitar bucles de commits.

### Notas de despliegue

- El cron está en UTC y GitHub puede retrasar la ejecución unos minutos.
- Si el repositorio pasa más de 60 días sin actividad, GitHub puede pausar el workflow programado; se reactiva desde la pestaña Actions o lanzándolo a mano.
- El sitio se publica como artefacto con `actions/upload-pages-artifact` y `actions/deploy-pages`. La opción «Deploy from a branch» no es compatible con este flujo, porque los commits hechos con `GITHUB_TOKEN` no disparan builds de Pages.
- El workflow necesita permisos de escritura sobre el contenido del repositorio para poder guardar los episodios nuevos.

## Actualizador manual

`actualizar.py` reproduce el mismo proceso en local. Solo necesita Python 3.9 o superior y conexión a internet; usa únicamente la biblioteca estándar.

```bash
python actualizar.py            # actualiza los datos y las portadas
python actualizar.py --dry-run  # muestra qué episodios nuevos hay, sin escribir nada
python actualizar.py --feed RUTA  # usa otro feed local o remoto (para pruebas)
```

Si están disponibles, se usan **Pillow** o **ffmpeg** para reducir las portadas nuevas a unos 600 px y que la web cargue más rápido. Si no lo están, la imagen se guarda tal cual.

En Windows, `actualizar.bat` abre el mismo script con doble clic.

## Estructura

```
index.html              Página principal
css/styles.css          Estilos, variables de diseño y adaptación a móvil
js/main.js              Renderizado, filtros, buscador, navegación y reproductor
js/episodes.js          Datos de los episodios (generado automáticamente)
img/episodes/           Portadas de los episodios
img/                    Logo, iconos y favicons
actualizar.py           Actualizador desde el feed del podcast
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
