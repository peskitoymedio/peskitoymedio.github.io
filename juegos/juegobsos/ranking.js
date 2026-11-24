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

  async function enviar(datos) {
    datos = datos || {};
    if (!configurado) {
      return { ok: false, mensaje: "El ranking todavía no está disponible." };
    }
    const alias = normalizarAlias(datos && datos.alias);
    if (!alias) {
      return { ok: false, mensaje: "Escribe un alias para salir en el ranking." };
    }
    try {
      await rpc("registrar_puntuacion", {
        p_jugador_id: playerId(),
        p_alias: alias,
        p_puntos: Number(datos.puntos) || 0,
        p_aciertos: Number(datos.aciertos) || 0
      });
      escribir(ALIAS_KEY, alias);
      return { ok: true, mensaje: "Procesado. Consulta el ranking 🎵" };
    } catch (e) {
      return { ok: false, mensaje: "No se pudo enviar: " + e.message };
    }
  }

  async function cargar(periodo) {
    if (!configurado) throw new Error("El ranking todavía no está disponible.");
    return rpc("ranking", { p_periodo: periodo });
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
    enviar: enviar,
    cargar: cargar,
    initGameForm: initGameForm
  };
})();
