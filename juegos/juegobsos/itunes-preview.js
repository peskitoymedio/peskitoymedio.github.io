/**
 * Búsqueda de previews de bandas sonoras en iTunes.
 * Compartida por el juego (index.html) y por el laboratorio privado (lab-bso.html)
 * para que ambos escuchen exactamente el mismo fragmento: misma URL, mismos
 * parámetros (media=music, entity=song, limit=5, country=ES) y mismo criterio
 * de selección (primer resultado con previewUrl).
 *
 * Se usa JSONP en lugar de fetch() para que funcione también con file://.
 */
(function (w) {
  'use strict';

  w.itunesPreview = function (term) {
    return new Promise(function (resolve) {
      const cb = 'cb' + Math.random().toString(36).slice(2);
      const s = document.createElement('script');
      const t = setTimeout(function () { resolve(null); cleanup(); }, 8000);

      function cleanup() {
        delete w[cb];
        s.remove();
        clearTimeout(t);
      }

      w[cb] = function (d) {
        const results = (d && d.results) || [];
        const x = results.find(function (z) { return z.previewUrl; });
        cleanup();
        resolve(x ? {
          url: x.previewUrl,
          pista: x.trackName || '',
          artista: x.artistName || ''
        } : null);
      };

      s.src = 'https://itunes.apple.com/search?media=music&entity=song&limit=5&country=ES&callback=' +
        cb + '&term=' + encodeURIComponent(term);
      s.onerror = function () { cleanup(); resolve(null); };
      document.body.appendChild(s);
    });
  };
})(window);
