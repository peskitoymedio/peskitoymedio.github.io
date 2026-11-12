/* =========================================================
   Peskito y Medio · ficha de episodio
   Reproductor propio, cabecera, menú móvil y animaciones
   ========================================================= */
(() => {
  "use strict";

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  /* ---------- Cabecera y menú móvil ---------- */
  const header = $("#site-header");
  const nav = $("#nav");
  const navToggle = $("#nav-toggle");

  const onScroll = () => {
    if (!header) return;
    header.classList.toggle("is-scrolled", window.scrollY > 8);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const closeNav = () => {
    if (!nav || !navToggle) return;
    nav.classList.remove("is-open");
    navToggle.setAttribute("aria-expanded", "false");
    navToggle.setAttribute("aria-label", "Abrir menú");
    document.body.classList.remove("nav-open");
  };

  if (navToggle && nav) {
    navToggle.addEventListener("click", () => {
      const open = !nav.classList.contains("is-open");
      nav.classList.toggle("is-open", open);
      navToggle.setAttribute("aria-expanded", String(open));
      navToggle.setAttribute("aria-label", open ? "Cerrar menú" : "Abrir menú");
      document.body.classList.toggle("nav-open", open);
    });
  }

  if (nav) {
    nav.addEventListener("click", (event) => {
      if (event.target.closest("a")) closeNav();
    });
  }

  /* ---------- Animaciones de aparición ---------- */
  const revealEls = $$(".reveal");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if ("IntersectionObserver" in window && !reduceMotion) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach((el) => observer.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add("is-visible"));
  }

  /* ---------- Reproductor ---------- */
  const player = $("#player");
  const audio = $("#audio");
  const playerCover = $("#player-cover");
  const playerTitle = $("#player-title");
  const playerSub = $("#player-sub");
  const playerToggle = $("#player-toggle");
  const playerClose = $("#player-close");
  const progress = $("#player-progress");
  const currentEl = $("#player-current");
  const durationEl = $("#player-duration");
  const toggleIcon = playerToggle ? playerToggle.querySelector("i") : null;
  const audioSrc = player ? player.dataset.audio || "" : "";

  const triggeredIcons = () =>
    $$("[data-episode-play]").map((button) => button.querySelector("i")).filter(Boolean);

  const fmtTime = (seconds) => {
    if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
    const total = Math.floor(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) {
      return h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
    }
    return m + ":" + String(s).padStart(2, "0");
  };

  const setProgressFill = (pct) => {
    if (!progress) return;
    const safe = Math.max(0, Math.min(100, pct));
    progress.style.background =
      "linear-gradient(to right, #F07000 " + safe + "%, rgba(255,246,233,.18) " + safe + "%)";
  };

  const syncPlayIcons = (playing) => {
    triggeredIcons().forEach((icon) => {
      icon.className = playing ? "fa-solid fa-pause" : "fa-solid fa-play";
    });
    $$("[data-episode-play]").forEach((button) => {
      button.classList.toggle("is-playing", playing);
    });
  };

  const updateToggle = (playing) => {
    if (!toggleIcon) return;
    toggleIcon.className = playing ? "fa-solid fa-pause" : "fa-solid fa-play";
    playerToggle.setAttribute(
      "aria-label",
      playing ? "Pausar episodio" : "Reproducir episodio"
    );
  };

  const openPlayer = () => {
    if (!player) return;
    player.classList.add("is-open");
    player.setAttribute("aria-hidden", "false");
    document.body.classList.add("player-open");
  };

  const closePlayer = () => {
    if (!player || !audio) return;
    audio.pause();
    player.classList.remove("is-open");
    player.setAttribute("aria-hidden", "true");
    document.body.classList.remove("player-open");
  };

  const playCurrent = () => {
    if (!audio || !audioSrc) return;
    openPlayer();
    if (audio.paused) {
      if (!audio.src) audio.src = audioSrc;
      audio.play().catch(() => {});
    } else {
      audio.pause();
    }
  };

  $$("[data-episode-play]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      playCurrent();
    });
  });

  if (audio) {
    audio.addEventListener("play", () => {
      syncPlayIcons(true);
      updateToggle(true);
    });
    audio.addEventListener("pause", () => {
      syncPlayIcons(false);
      updateToggle(false);
    });
    audio.addEventListener("loadedmetadata", () => {
      if (durationEl) durationEl.textContent = fmtTime(audio.duration);
    });
    audio.addEventListener("timeupdate", () => {
      if (!progress) return;
      const duration = audio.duration || 0;
      const pct = duration ? (audio.currentTime / duration) * 100 : 0;
      progress.value = pct;
      setProgressFill(pct);
      if (currentEl) currentEl.textContent = fmtTime(audio.currentTime);
    });
    audio.addEventListener("ended", () => {
      syncPlayIcons(false);
      updateToggle(false);
      if (progress) progress.value = 0;
      setProgressFill(0);
      if (currentEl) currentEl.textContent = "0:00";
    });
    audio.addEventListener("error", () => {
      if (playerSub && audio.currentSrc) {
        playerSub.textContent =
          "No se pudo cargar el audio. Prueba a escucharlo en iVoox.";
      }
    });
  }

  if (playerToggle) {
    playerToggle.addEventListener("click", () => {
      if (!audio || !audio.src) return;
      if (audio.paused) {
        audio.play().catch(() => {});
      } else {
        audio.pause();
      }
    });
  }

  if (playerClose) playerClose.addEventListener("click", closePlayer);

  if (progress && audio) {
    const seek = () => {
      const duration = audio.duration || 0;
      if (!duration) return;
      const pct = Number(progress.value);
      audio.currentTime = (pct / 100) * duration;
      setProgressFill(pct);
      if (currentEl) currentEl.textContent = fmtTime(audio.currentTime);
    };
    progress.addEventListener("input", seek);
    progress.addEventListener("change", seek);
  }

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeNav();
    if (player && player.classList.contains("is-open")) closePlayer();
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 960) closeNav();
  });

  /* ---------- Año del footer ---------- */
  const year = $("#year");
  if (year) year.textContent = new Date().getFullYear();

  /* ---------- Estado inicial ---------- */
  syncPlayIcons(false);
  updateToggle(false);
  setProgressFill(0);
})();
