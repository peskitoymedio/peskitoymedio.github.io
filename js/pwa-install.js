/* Aviso para instalar la PWA del juego de BSOs.
 *
 * Solo se muestra en navegadores que disparan `beforeinstallprompt`
 * (Chromium: Chrome, Edge, Samsung Internet...). En iOS Safari u otros
 * navegadores no compatibles no se crea ningún elemento. Tampoco aparece
 * cuando la web ya se está abriendo en modo app (PWA instalada).
 */
(function () {
  'use strict';

  var CLAVE_RECHAZO = 'pym-bso-install-rechazado';
  var DIAS_RECHAZO = 3;
  var deferred = null;
  var banner = null;
  var enlaces = [];

  function yaInstalada() {
    var mq = window.matchMedia;
    return !!(mq && (
      mq('(display-mode: standalone)').matches ||
      mq('(display-mode: fullscreen)').matches ||
      mq('(display-mode: minimal-ui)').matches
    )) || window.navigator.standalone === true;
  }

  function rechazadaRecientemente() {
    try {
      var t = Number(localStorage.getItem(CLAVE_RECHAZO) || 0);
      return !!t && (Date.now() - t) < DIAS_RECHAZO * 24 * 60 * 60 * 1000;
    } catch (e) {
      return false;
    }
  }

  function recordarRechazo() {
    try { localStorage.setItem(CLAVE_RECHAZO, String(Date.now())); } catch (e) {}
  }

  function inyectarEstilos() {
    if (document.getElementById('pwa-install-estilos')) return;
    var style = document.createElement('style');
    style.id = 'pwa-install-estilos';
    style.textContent =
      '.pwa-install{' +
        'position:fixed;left:50%;bottom:18px;transform:translateX(-50%);' +
        'z-index:1300;display:flex;align-items:center;gap:12px;' +
        'max-width:calc(100% - 32px);padding:12px 14px;' +
        'background:#0B1B2D;color:#fff6e9;border:3px solid #0B1B2D;' +
        'border-radius:16px;box-shadow:4px 4px 0 rgba(0,0,0,.28);' +
        'font:600 .92rem/1.3 system-ui,-apple-system,Segoe UI,sans-serif;' +
      '}' +
      '.pwa-install__texto{flex:1;min-width:0;}' +
      '.pwa-install__btn{' +
        'flex:none;font:800 .9rem/1 system-ui,sans-serif;' +
        'background:#ffc531;color:#0B1B2D;border:2px solid #0B1B2D;' +
        'border-radius:10px;padding:9px 14px;cursor:pointer;' +
      '}' +
      '.pwa-install__cerrar{' +
        'flex:none;width:30px;height:30px;border-radius:50%;' +
        'background:transparent;color:#fff6e9;border:2px solid rgba(255,246,233,.45);' +
        'font:700 1.1rem/1 system-ui,sans-serif;cursor:pointer;' +
      '}' +
      '.pwa-install-link{' +
        'display:inline-block;margin:10px 0 2px;padding:0;' +
        'font:600 .82rem/1.3 system-ui,-apple-system,Segoe UI,sans-serif;' +
        'color:#0B1B2D;background:none;border:0;cursor:pointer;opacity:.78;' +
        'text-decoration:underline;text-decoration-style:dotted;text-underline-offset:3px;' +
      '}' +
      '.pwa-install-link:hover,.pwa-install-link:focus-visible{opacity:1;}' +
      '.pwa-install-link[hidden]{display:none;}' +
      '@media (max-width:760px){' +
        '.pwa-install{bottom:56px;}' + /* por encima del enlace fijo "Volver" */
        'body.jugando .pwa-install{display:none!important;}' +
      '}';
    document.head.appendChild(style);
  }

  function ocultar() {
    if (banner) {
      banner.remove();
      banner = null;
    }
  }

  function actualizarEnlace() {
    var visible = !!deferred && !yaInstalada();
    for (var i = 0; i < enlaces.length; i++) enlaces[i].hidden = !visible;
  }

  function lanzarPrompt(registrarRechazo) {
    if (!deferred) return;
    var actual = deferred;
    deferred = null;
    ocultar();
    actualizarEnlace();
    try { actual.prompt(); } catch (e) { return; }
    actual.userChoice.then(function (choice) {
      if ((!choice || choice.outcome !== 'accepted') && registrarRechazo) recordarRechazo();
      ocultar();
      actualizarEnlace();
    });
  }

  function crear() {
    if (banner || yaInstalada() || rechazadaRecientemente() || !deferred) return;

    banner = document.createElement('aside');
    banner.className = 'pwa-install';
    banner.setAttribute('role', 'status');
    banner.setAttribute('aria-label', 'Instalar aplicación');
    banner.innerHTML =
      '<span class="pwa-install__texto">¿Juegas a menudo? Instálalo y se abre como una app.</span>' +
      '<button type="button" class="pwa-install__btn">Instalar</button>' +
      '<button type="button" class="pwa-install__cerrar" aria-label="No volver a mostrar">×</button>';
    document.body.appendChild(banner);

    banner.querySelector('.pwa-install__btn').addEventListener('click', function () {
      lanzarPrompt(true);
    });

    banner.querySelector('.pwa-install__cerrar').addEventListener('click', function () {
      recordarRechazo();
      deferred = null;
      ocultar();
      actualizarEnlace();
    });
  }

  window.addEventListener('beforeinstallprompt', function (e) {
    if (yaInstalada()) return;
    e.preventDefault();
    deferred = e;
    crear();
    actualizarEnlace();
  });

  window.addEventListener('appinstalled', function () {
    deferred = null;
    ocultar();
    actualizarEnlace();
  });

  inyectarEstilos();
  enlaces = document.querySelectorAll('.pwa-install-link');
  for (var i = 0; i < enlaces.length; i++) {
    enlaces[i].addEventListener('click', function (e) {
      e.preventDefault();
      // Ignora el rechazo del aviso: quien pulsa aquí lo hace a propósito.
      lanzarPrompt(false);
    });
  }

  // Si el evento llegó antes de que se cargara este script.
  if (yaInstalada()) ocultar();
})();
