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
 * del banco de películas sin salir de la web. Si una consulta no aparece (puede
 * venir de una caché antigua de GitHub Pages), se recarga el catálogo una sola
 * vez sin caché antes de acudir a la búsqueda JSONP original; esa búsqueda
 * sigue sirviendo para el laboratorio con textos nuevos y para abrir el juego
 * desde file:// sin el catálogo.
 */
(function (w) {
  'use strict';

  var catalogo = null;
  var catalogoPromise = null;
  var catalogoFresco = false;
  var recargaPromise = null;

  // GitHub Pages sirve previews.js con max-age=600. El laboratorio fija
  // PYM_PREVIEWS_NO_CACHE para leer siempre la versión recién generada; el
  // juego solo pide una recarga cuando una consulta no aparece en el catálogo.
  function cargarCatalogo(fresco) {
    if (!fresco && catalogo) return Promise.resolve(catalogo);
    if (!fresco && catalogoPromise) return catalogoPromise;
    catalogoFresco = Boolean((fresco || w.PYM_PREVIEWS_NO_CACHE) &&
      /^https?:$/.test(location.protocol));
    catalogoPromise = new Promise(function (resolve) {
      var s = document.createElement('script');
      s.src = 'previews.js' + (catalogoFresco ? '?v=' + Date.now() : '');
      s.onload = function () {
        var datos = w.APPLE_PREVIEWS;
        catalogo = (datos && datos.previews) || null;
        resolve(catalogo);
      };
      s.onerror = function () { resolve(null); };
      document.head.appendChild(s);
    });
    return catalogoPromise;
  }

  function recargarCatalogo() {
    // Varias películas pueden fallar a la vez: todas esperan la misma recarga.
    if (!recargaPromise) {
      // Si ya se cargó sin caché (lab, o un miss anterior), no repetir la descarga.
      if (catalogoFresco) return Promise.resolve(catalogo);
      catalogo = null;
      catalogoPromise = null;
      recargaPromise = cargarCatalogo(true);
    }
    return recargaPromise;
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
      return recargarCatalogo().then(function (catFresco) {
        if (catFresco && catFresco[term]) return catFresco[term];
        return buscarJSONP(term);
      });
    });
  };

  // Devuelve el preview ya guardado en previews.js, sin buscar en iTunes.
  w.itunesPreviewGuardado = function (term) {
    return cargarCatalogo().then(function (cat) {
      return (cat && cat[term]) || null;
    });
  };
})(window);
