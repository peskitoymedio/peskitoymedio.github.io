/* Cliente del ranking online. Lo usan index.html y ranking.html.
 * Sin créditos en config.js no hace nada: el juego sigue funcionando. */
(function () {
  "use strict";

  const cfg = window.PYM_CONFIG || {};
  const base = String(cfg.supabaseUrl || "").replace(/\/+$/, "");
  const key = String(cfg.supabaseAnonKey || "");
  const configurado = !!(base && key);

  const ID_KEY = "pym-bso-jugador-id";
  const ALIAS_KEY = "pym-bso-alias";
  const LIMITE = 24;
  let tokenPartida = null;

  function leer(clave) {
    try { return localStorage.getItem(clave) || ""; } catch (e) { return ""; }
  }
  function escribir(clave, valor) {
    try { localStorage.setItem(clave, valor); } catch (e) {}
  }

  function playerId() {
    let id = leer(ID_KEY);
    if (!id) {
      id = (window.crypto && crypto.randomUUID)
        ? crypto.randomUUID()
        : "p-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
      escribir(ID_KEY, id);
    }
    return id;
  }

  function aliasGuardado() {
    return leer(ALIAS_KEY).slice(0, LIMITE);
  }

  function normalizarAlias(valor) {
    return String(valor || "").replace(/\s+/g, " ").trim().slice(0, LIMITE);
  }

  async function rpc(nombre, parametros) {
    const respuesta = await fetch(base + "/rest/v1/rpc/" + nombre, {
      method: "POST",
      headers: {
        apikey: key,
        Authorization: "Bearer " + key,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(parametros || {})
    });
    // PostgREST responde 204 sin cuerpo a las funciones que devuelven void.
    const texto = await respuesta.text();
    let datos = null;
    if (texto) {
      try { datos = JSON.parse(texto); } catch (e) { datos = null; }
    }
    if (!respuesta.ok) {
      const detalle = (datos && (datos.message || datos.details)) || texto || ("Error " + respuesta.status);
      throw new Error(detalle);
    }
    return datos;
  }

  // Se llama al pulsar «Dale al play». Si falla, el juego sigue funcionando.
  async function iniciarToken() {
    tokenPartida = null;
    if (!configurado) return null;
    try {
      tokenPartida = await rpc("emitir_token", {});
      return tokenPartida;
    } catch (e) {
      return null;
    }
  }

  // Se llama al terminar la décima respuesta, aunque no se envíe la puntuación.
  // No consume el token: el envío posterior sigue necesitándolo.
  async function partidaTerminada() {
    if (!configurado || !tokenPartida) return;
    try {
      await rpc("registrar_partida_terminada", { p_token: tokenPartida });
    } catch (e) {}
  }

  async function enviar(datos) {
    datos = datos || {};
    if (!configurado) {
      return { ok: false, mensaje: "El ranking todavía no está disponible." };
    }
    const alias = normalizarAlias(datos && datos.alias);
    if (!alias) {
      return { ok: false, mensaje: "Escribe un alias para salir en el ranking." };
    }
    const token = datos.token || tokenPartida;
    if (!token) {
      return { ok: false, mensaje: "Vuelve a pulsar «Dale al play» para abrir una partida." };
    }
    try {
      const id = await rpc("registrar_puntuacion", {
        p_jugador_id: playerId(),
        p_alias: alias,
        p_puntos: Number(datos.puntos) || 0,
        p_aciertos: Number(datos.aciertos) || 0,
        p_token: token,
        p_detalles: datos.detalles || []
      });
      tokenPartida = null;
      escribir(ALIAS_KEY, alias);
      // null = la partida no ha mejorado la marca de hoy y no entra en ranking.
      return {
        ok: true,
        partida: id == null ? null : Number(id),
        mensaje: id == null
          ? "No supera tu mejor marca de hoy; no hay nuevo puesto."
          : "¡Nueva marca guardada! Mira la tarjeta de abajo 👇"
      };
    } catch (e) {
      return { ok: false, mensaje: "No se pudo enviar: " + e.message };
    }
  }

  async function cargar(periodo) {
    if (!configurado) throw new Error("El ranking todavía no está disponible.");
    return rpc("ranking", { p_periodo: periodo });
  }

  async function puesto(alias, periodo) {
    if (!configurado) throw new Error("El ranking todavía no está disponible.");
    const filas = await rpc("puesto_de", {
      p_alias: normalizarAlias(alias),
      p_periodo: periodo || "diario"
    });
    return Array.isArray(filas) && filas.length ? filas[0] : null;
  }

  async function totalPartidas() {
    if (!configurado) throw new Error("El ranking todavía no está disponible.");
    return Number(await rpc("total_partidas", {})) || 0;
  }

  async function totalPartidasJugadas() {
    if (!configurado) throw new Error("El ranking todavía no está disponible.");
    return Number(await rpc("total_partidas_jugadas", {})) || 0;
  }

  async function detalles(id) {
    if (!configurado) throw new Error("El ranking todavía no está disponible.");
    return rpc("detalles_partida", { p_id: Number(id) });
  }

  function initGameForm() {
    const caja = document.getElementById("score-submit");
    if (!caja) return;
    if (!configurado) { caja.hidden = true; return; }
    caja.hidden = false;
    const input = document.getElementById("alias");
    const boton = document.getElementById("save-score");
    const mensaje = document.getElementById("save-msg");
    // Precargado con el último alias usado en este equipo; se puede cambiar.
    if (input) input.value = aliasGuardado();
    if (boton) boton.disabled = false;
    if (mensaje) mensaje.textContent = "";
  }

  window.PYMRanking = {
    configurado: configurado,
    playerId: playerId,
    iniciarToken: iniciarToken,
    partidaTerminada: partidaTerminada,
    enviar: enviar,
    cargar: cargar,
    puesto: puesto,
    totalPartidas: totalPartidas,
    totalPartidasJugadas: totalPartidasJugadas,
    aliasGuardado: aliasGuardado,
    detalles: detalles,
    initGameForm: initGameForm
  };
})();
