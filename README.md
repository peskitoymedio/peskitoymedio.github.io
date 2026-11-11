# Peskito y Medio · web estática

Web del podcast **Peskito y Medio**. Contenido, portadas y datos obtenidos del feed oficial de iVoox.

- Web publicada: <https://peskitoymedio.github.io/>
- Repositorio: <https://github.com/peskitoymedio/peskitoymedio.github.io>

## Publicar un episodio nuevo

Cuando publiques un episodio en iVoox, no hay que tocar el HTML ni el CSS. Basta con actualizar los datos:

1. **Doble clic en `actualizar.bat`** (o ejecuta `python actualizar.py` en esta carpeta).
2. El script descarga el feed, detecta los episodios nuevos, baja su portada a `img/episodes/` y regenera `js/episodes.js`.
3. Si la web está publicada, sube a tu hosting los archivos que hayan cambiado:
   - `js/episodes.js`
   - las portadas nuevas de `img/episodes/` (el script te dice cuáles)
   - opcionalmente `feed.xml` y `episodes-raw.json` (son copias de referencia)

Con eso, la portada del hero, la barra superior, el contador, los filtros, el buscador y el reproductor se actualizan solos: todo se genera a partir de `EPISODES` en `js/episodes.js`.

### Comprobar sin modificar nada

```bash
python actualizar.py --dry-run
```

Muestra los episodios nuevos que encontraría, pero no descarga ni escribe archivos.

### Requisitos

- Python 3.9 o superior (`python --version`).
- Conexión a internet para leer el feed de iVoox.
- No hacen falta librerías externas. Pillow o ffmpeg son opcionales: si están disponibles, las portadas nuevas se optimizan a ~600 px.

### Qué hace exactamente

- Lee `https://feeds.ivoox.com/feed_fg_f1661614_filtro_1.xml`.
- Identifica cada episodio por su ID de iVoox, así que puede ejecutarse tantas veces como quieras sin duplicar nada.
- Clasifica automáticamente:
  - títulos que no empiezan por `PYM` → **colaboración**
  - títulos `PYM` que contienen “Especial” → **especial**
  - resto → **programa**
- Extrae el número de `PYM 63. ...` para la etiqueta `PYM 63`.
- Limpia la descripción, quita la promo de los Premios iVoox y la recorta para las tarjetas.
- Guarda las portadas nuevas con un nombre estable: `ep-<id-de-iVoox>.jpg`. Las portadas antiguas no se renombran.

## Actualización automática en GitHub Pages

El repositorio incluye `.github/workflows/actualizar-pages.yml`. Cada 6 horas (y cuando lo lances a mano) el workflow:

1. descarga el feed de iVoox,
2. ejecuta `actualizar.py`,
3. si hay episodios nuevos, guarda la portada y hace commit de los datos,
4. publica el sitio actualizado en GitHub Pages.

### Puesta en marcha (solo una vez)

Este repositorio ya está configurado. Si algún día hay que recrearlo:

1. Crea un repositorio en GitHub llamado `peskitoymedio.github.io`. Para usar Pages gratis, que sea **público**.
2. Sube el contenido de esta carpeta a la **raíz** del repositorio, incluida la carpeta oculta `.github`.
3. En el repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
4. En **Settings → Actions → General → Workflow permissions**, marca **Read and write permissions** y guarda.
5. Ve a **Actions → “Actualizar episodios y publicar en Pages” → Run workflow** para probarlo.
6. La web quedará en `https://peskitoymedio.github.io/`.

A partir de ahí no hay que hacer nada más: cuando publiques un episodio en iVoox, la siguiente pasada lo detectará y lo publicará.

### Notas

- El cron está en UTC y GitHub puede retrasar la ejecución unos minutos.
- Si el repositorio pasa más de 60 días sin actividad, GitHub puede desactivar el workflow programado. Se vuelve a activar desde la pestaña **Actions** o lanzándolo a mano.
- El workflow también se ejecuta al hacer push a `main`/`master`, para publicar cambios manuales.
- No uses la opción “Deploy from a branch” con este bot: los commits hechos con `GITHUB_TOKEN` no disparan un build de Pages. Por eso el workflow despliega con `actions/deploy-pages`.
- Si usas un dominio propio, configúralo en **Settings → Pages**; no hay que tocar el workflow.

## Estructura

```
index.html            Página principal
css/styles.css        Estilos
js/main.js            Interactividad, filtros, buscador y reproductor
js/episodes.js        Datos de los episodios (se regenera con actualizar.py)
img/episodes/         Portadas de los episodios
img/                  Logo y favicons
actualizar.py         Actualizador desde el feed de iVoox
actualizar.bat        Lanzador para Windows (doble clic)
feed.xml              Última copia descargada del feed
episodes-raw.json     Última copia de los datos crudos del feed
.github/workflows/    Workflow de GitHub Actions para actualizar y publicar
```

## Ver la web en local

```bash
python -m http.server 8123
```

Y abrir <http://localhost:8123/>.
