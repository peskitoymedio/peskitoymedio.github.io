/**
 * Búsqueda de previews de bandas sonoras en iTunes.
 * Compartida por el juego (index.html) y por el laboratorio privado (lab-bso.html)
 * para que ambos escuchen exactamente el mismo fragmento: misma URL, mismos
 * parámetros (media=music, entity=song, limit=5, country=ES) y mismo criterio
 * de selección (primer resultado con previewUrl).
 *
 * En iOS Apple redirige itunes.apple.com/search a musics://..., así que el
 * navegador del iPhone no puede consultar la API en directo. El catálogo
 * pregenerado en previews.js (ver generar-previews.py) resuelve las búsquedas
 * del banco de películas sin salir de la web. Solo si no está en el catálogo
 * se usa la búsqueda JSONP original, que sigue sirviendo para el laboratorio
 * con textos nuevos y para abrir el juego desde file:// sin el catálogo.
 */
(function (w) {
  'use strict';

  var catalogo = null;
  var catalogoPromise = null;

  function cargarCatalogo() {
    if (catalogo) return Promise.resolve(catalogo);
    if (!catalogoPromise) {
      catalogoPromise = new Promise(function (resolve) {
        var s = document.createElement('script');
        // El laboratorio fija PYM_PREVIEWS_NO_CACHE para leer siempre el
        // catálogo recién generado: GitHub Pages sirve previews.js con
        // max-age=600 y una consulta regenerada quedaría invisible.
        var sufijo = (w.PYM_PREVIEWS_NO_CACHE && /^https?:$/.test(location.protocol))
          ? '?v=' + Date.now()
          : '';
        s.src = 'previews.js' + sufijo;
        s.onload = function () {
          var datos = w.APPLE_PREVIEWS;
          catalogo = (datos && datos.previews) || null;
          resolve(catalogo);
        };
        s.onerror = function () { resolve(null); };
        document.head.appendChild(s);
      });
    }
    return catalogoPromise;
  }

  function buscarJSONP(term) {
    return new Promise(function (resolve) {
      var cb = 'cb' + Math.random().toString(36).slice(2);
      var s = document.createElement('script');
      var t = setTimeout(function () { resolve(null); cleanup(); }, 8000);

      function cleanup() {
        delete w[cb];
        s.remove();
        clearTimeout(t);
      }

      w[cb] = function (d) {
        var results = (d && d.results) || [];
        var x = results.find(function (z) { return z.previewUrl; });
        cleanup();
        resolve(x ? {
          url: x.previewUrl,
          pista: x.trackName || '',
          artista: x.artistName || '',
          album: x.collectionName || ''
        } : null);
      };

      s.src = 'https://itunes.apple.com/search?media=music&entity=song&limit=5&country=ES&callback=' +
        cb + '&term=' + encodeURIComponent(term);
      s.onerror = function () { cleanup(); resolve(null); };
      document.body.appendChild(s);
    });
  }

  w.itunesPreview = function (term) {
    return cargarCatalogo().then(function (cat) {
      if (cat && cat[term]) return cat[term];
      return buscarJSONP(term);
    });
  };

  // Devuelve el preview ya guardado en previews.js, sin buscar en iTunes.
  w.itunesPreviewGuardado = function (term) {
    return cargarCatalogo().then(function (cat) {
      return (cat && cat[term]) || null;
    });
  };
})(window);
