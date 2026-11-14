/* =========================================================
   Peskito y Medio · interacciones
   ========================================================= */
(() => {
  "use strict";

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  const PAGE_SIZE = 12;

  const TYPE_LABEL = {
    programa: "Programa",
    especial: "Especial",
    promo: "Promo",
    colaboracion: "Colaboración",
  };

  const state = {
    filter: "all",
    search: "",
    visible: PAGE_SIZE,
    currentId: null,
    isSeeking: false,
  };

  /* ---------- Utilidades ---------- */
  const escapeHtml = (value) =>
    String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const htmlToText = (html) =>
    String(html || "")
      .replace(/<br\s*\/?>/gi, " ")
      .replace(/<[^>]*>/g, " ")
      .replace(/&nbsp;/gi, " ")
      .replace(/&amp;/gi, "&")
      .replace(/&lt;/gi, "<")
      .replace(/&gt;/gi, ">")
      .replace(/&quot;/gi, '"')
      .replace(/&#0*39;/g, "'")
      .replace(/\s+/g, " ")
      .trim();

  const excerptFor = (ep, limit = 190) => {
    const text = htmlToText(ep.descHtml || ep.desc || "");
    if (text.length <= limit) return text;
    let cut = text.slice(0, limit);
    const lastSpace = cut.lastIndexOf(" ");
    if (lastSpace > 0) cut = cut.slice(0, lastSpace);
    return cut.replace(/[ .,-]+$/, "") + "…";
  };

  const canExpand = (ep) =>
    !!ep.descHtml && (htmlToText(ep.descHtml).length > 190 || /<a\b/i.test(ep.descHtml));

  const formatDate = (iso) => {
    const date = new Date(iso + "T00:00:00");
    return new Intl.DateTimeFormat("es-ES", {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(date);
  };

  const badgeFor = (ep) => {
    if (ep.n != null) return "PYM " + ep.n;
    if (ep.type === "promo") return "Promo";
    return ep.type === "colaboracion" ? "Colaboración" : "Especial";
  };

  const shortTitle = (ep) => ep.title.replace(/^PYM\s+\d+\.\s*/, "");

  const episodePage = (ep) =>
    ep.slug ? "episodios/" + encodeURIComponent(ep.slug) + ".html" : ep.link;

  /* ---------- Elementos ---------- */
  const grid = $("#episode-grid");
  const countEl = $("#episode-count");
  const loadMore = $("#load-more");
  const searchInput = $("#episode-search");
  const header = $("#site-header");
  const nav = $("#nav");
  const navToggle = $("#nav-toggle");

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
    $$("[data-play-id]").forEach((btn) => {
      const id = Number(btn.dataset.playId);
      const icon = btn.querySelector("i");
      if (!icon) return;
      const isCurrent = id === state.currentId;
      icon.className = isCurrent && playing ? "fa-solid fa-pause" : "fa-solid fa-play";
      btn.classList.toggle("is-playing", isCurrent && playing);
    });
  };

  const updateToggle = (playing) => {
    if (!toggleIcon) return;
    toggleIcon.className = playing ? "fa-solid fa-pause" : "fa-solid fa-play";
    playerToggle.setAttribute("aria-label", playing ? "Pausar episodio" : "Reproducir episodio");
  };

  const closePlayer = () => {
    if (!player) return;
    audio.pause();
    player.classList.remove("is-open");
    player.setAttribute("aria-hidden", "true");
    document.body.classList.remove("player-open");
  };

  const playEpisode = (rawId, start = 0) => {
    const id = Number(rawId);
    const ep = EPISODES.find((item) => item.id === id);
    if (!ep) return;
    const target = Math.max(0, Number(start) || 0);

    const seekAndPlay = () => {
      if (target > 0) {
        try {
          audio.currentTime = target;
        } catch (error) {
          /* Si el audio aún no admite saltos, se intentará al cargar los metadatos. */
        }
      }
      audio.play().catch(() => {});
    };

    if (state.currentId === ep.id) {
      if (target > 0) {
        if (audio.readyState >= 1) {
          seekAndPlay();
        } else {
          audio.addEventListener("loadedmetadata", seekAndPlay, { once: true });
        }
      } else if (audio.paused) {
        audio.play().catch(() => {});
      } else {
        audio.pause();
      }
      return;
    }

    state.currentId = ep.id;
    audio.src = ep.audio;
    playerCover.src = ep.img;
    playerCover.alt = "Portada de " + ep.title;
    playerTitle.textContent = ep.title;
    playerSub.textContent =
      "Peskito y Medio · " + TYPE_LABEL[ep.type] + " · " + ep.duration;
    progress.value = 0;
    setProgressFill(0);
    currentEl.textContent = "0:00";
    durationEl.textContent = ep.duration;

    player.classList.add("is-open");
    player.setAttribute("aria-hidden", "false");
    document.body.classList.add("player-open");

    audio.load();
    if (target > 0) {
      audio.addEventListener("loadedmetadata", seekAndPlay, { once: true });
    } else {
      const promise = audio.play();
      if (promise && promise.catch) promise.catch(() => {});
    }
  };

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
      durationEl.textContent = fmtTime(audio.duration);
    });
    audio.addEventListener("timeupdate", () => {
      if (state.isSeeking) return;
      const duration = audio.duration || 0;
      const pct = duration ? (audio.currentTime / duration) * 100 : 0;
      progress.value = pct;
      setProgressFill(pct);
      currentEl.textContent = fmtTime(audio.currentTime);
    });
    audio.addEventListener("ended", () => {
      syncPlayIcons(false);
      updateToggle(false);
      progress.value = 0;
      setProgressFill(0);
      currentEl.textContent = "0:00";
    });
    audio.addEventListener("error", () => {
      if (playerSub && audio.currentSrc) {
        playerSub.textContent = "No se pudo cargar el audio. Prueba a escucharlo en iVoox.";
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

  if (progress) {
    const seek = () => {
      const duration = audio.duration || 0;
      if (!duration) return;
      const pct = Number(progress.value);
      audio.currentTime = (pct / 100) * duration;
      setProgressFill(pct);
      currentEl.textContent = fmtTime(audio.currentTime);
    };
    progress.addEventListener("pointerdown", () => {
      state.isSeeking = true;
    });
    progress.addEventListener("input", seek);
    progress.addEventListener("change", () => {
      state.isSeeking = false;
      seek();
    });
    window.addEventListener("pointerup", () => {
      state.isSeeking = false;
    });
  }

  /* Delegación: cualquier botón con data-play-id */
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-play-id]");
    if (!trigger) return;
    event.preventDefault();
    playEpisode(trigger.dataset.playId);
  });

  /* Delegación: líneas de descripción con minutaje */
  document.addEventListener("click", (event) => {
    const line = event.target.closest("[data-desc-seek]");
    if (!line || event.target.closest("a")) return;
    const card = line.closest(".ep-card");
    if (!card) return;
    event.preventDefault();
    playEpisode(card.dataset.episodeId, Number(line.dataset.descSeek) || 0);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const line = event.target.closest("[data-desc-seek]");
    if (!line || event.target.closest("a")) return;
    const card = line.closest(".ep-card");
    if (!card) return;
    event.preventDefault();
    playEpisode(card.dataset.episodeId, Number(line.dataset.descSeek) || 0);
  });

  /* Delegación: mostrar u ocultar la descripción completa */
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-more-id]");
    if (!button) return;
    event.preventDefault();
    const episode = EPISODES.find((ep) => String(ep.id) === button.dataset.moreId);
    if (!episode) return;
    const wrap = button.closest(".ep-desc-wrap");
    const desc = wrap ? wrap.querySelector(".ep-desc") : null;
    if (!desc) return;

    if (button.getAttribute("aria-expanded") === "true") {
      desc.innerHTML = escapeHtml(excerptFor(episode));
      desc.classList.remove("ep-desc--full");
      button.textContent = "Leer más";
      button.setAttribute("aria-expanded", "false");
    } else {
      desc.innerHTML = episode.descHtml || escapeHtml(episode.desc || "");
      desc.classList.add("ep-desc--full");
      button.textContent = "Leer menos";
      button.setAttribute("aria-expanded", "true");
    }
  });

  /* ---------- Episodios ---------- */
  const filteredEpisodes = () => {
    const query = state.search.trim().toLowerCase();
    return EPISODES.filter((ep) => {
      if (state.filter !== "all" && ep.type !== state.filter) return false;
      if (!query) return true;
      const haystack = (
        ep.title + " " + htmlToText(ep.descHtml || ep.desc) + " " + TYPE_LABEL[ep.type]
      ).toLowerCase();
      return haystack.includes(query);
    });
  };

  const cardHTML = (ep, index) => {
    const title = escapeHtml(ep.title);
    const page = episodePage(ep);
    return (
      '<article class="ep-card" data-episode-id="' + ep.id + '" style="--i:' + (index % PAGE_SIZE) + '">' +
        '<div class="ep-cover">' +
          '<a class="ep-cover-link" href="' + page + '" aria-label="Ver la ficha de ' + title + '">' +
            '<img src="' + ep.img + '" alt="Portada del episodio: ' + title + '" loading="lazy" width="400" height="400">' +
          '</a>' +
          '<span class="ep-badge">' + badgeFor(ep) + '</span>' +
          '<button class="ep-play" type="button" data-play-id="' + ep.id + '" aria-label="Reproducir: ' + title + '">' +
            '<i class="fa-solid fa-play" aria-hidden="true"></i>' +
          '</button>' +
          '<span class="ep-duration"><i class="fa-regular fa-clock" aria-hidden="true"></i> ' + ep.duration + '</span>' +
        '</div>' +
        '<div class="ep-body">' +
          '<div class="ep-meta">' +
            '<span class="ep-type ep-type--' + ep.type + '">' + TYPE_LABEL[ep.type] + '</span>' +
            '<time datetime="' + ep.date + '">' + formatDate(ep.date) + '</time>' +
          '</div>' +
          '<h3 class="ep-title"><a class="ep-title-link" href="' + page + '">' + title + '</a></h3>' +
          '<div class="ep-desc-wrap">' +
            '<div class="ep-desc">' + escapeHtml(excerptFor(ep)) + '</div>' +
            (canExpand(ep)
              ? '<button class="ep-more" type="button" data-more-id="' + ep.id + '" aria-expanded="false">Leer más</button>'
              : '') +
          '</div>' +
          '<div class="ep-links">' +
            '<a class="ep-link" href="' + page + '">Ver el episodio ' +
              '<i class="fa-solid fa-arrow-right" aria-hidden="true"></i>' +
            '</a>' +
            '<a class="ep-link" href="' + ep.link + '" target="_blank" rel="noopener">iVoox ' +
              '<i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i>' +
            '</a>' +
          '</div>' +
        '</div>' +
      '</article>'
    );
  };

  const renderEpisodes = () => {
    if (!grid) return;
    const list = filteredEpisodes();
    const visible = list.slice(0, state.visible);

    grid.innerHTML = visible.length
      ? visible.map(cardHTML).join("")
      : '<div class="empty-state"><strong>No hay resultados</strong>Prueba con otra búsqueda o cambia el filtro. ¡Seguro que hay un Peskito para ti!</div>';

    if (countEl) {
      countEl.textContent = list.length
        ? "Mostrando " + visible.length + " de " + list.length + (list.length === 1 ? " episodio" : " episodios")
        : "0 episodios encontrados";
    }
    if (loadMore) loadMore.hidden = list.length <= state.visible;

    syncPlayIcons(audio ? !audio.paused : false);
  };

  const updateCounts = () => {
    const counts = { all: EPISODES.length, programa: 0, especial: 0, promo: 0, colaboracion: 0 };
    EPISODES.forEach((ep) => {
      counts[ep.type] = (counts[ep.type] || 0) + 1;
    });
    $$(".filter-count").forEach((el) => {
      const key = el.dataset.count;
      el.textContent = counts[key] != null ? counts[key] : 0;
    });
  };

  $$(".filter").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.filter = btn.dataset.filter || "all";
      state.visible = PAGE_SIZE;
      $$(".filter").forEach((other) => {
        other.classList.toggle("is-active", other === btn);
      });
      renderEpisodes();
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      state.search = searchInput.value;
      state.visible = PAGE_SIZE;
      renderEpisodes();
    });
  }

  if (loadMore) {
    loadMore.addEventListener("click", () => {
      state.visible += PAGE_SIZE;
      renderEpisodes();
    });
  }

  /* ---------- Cabecera ---------- */
  const onScroll = () => {
    if (!header) return;
    header.classList.toggle("is-scrolled", window.scrollY > 8);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* ---------- Menú móvil ---------- */
  const closeNav = () => {
    if (!nav || !navToggle) return;
    nav.classList.remove("is-open");
    navToggle.setAttribute("aria-expanded", "false");
    navToggle.setAttribute("aria-label", "Abrir menú");
    document.body.classList.remove("nav-open");
  };

  if (navToggle) {
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

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeNav();
    if (player && player.classList.contains("is-open")) closePlayer();
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 960) closeNav();
  });

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

  /* ---------- Datos del último episodio ---------- */
  const latest = EPISODES[0];
  if (latest) {
    const topbarLatest = $("#topbar-latest");
    if (topbarLatest) {
      topbarLatest.textContent = latest.n
        ? "PYM " + latest.n + " · " + shortTitle(latest)
        : latest.title;
    }

    const heroLatest = $("#hero-latest");
    if (heroLatest) {
      heroLatest.textContent = latest.n
        ? "PYM " + latest.n + " · " + shortTitle(latest)
        : latest.title;
      heroLatest.dataset.playId = latest.id;
      heroLatest.title = latest.title;
    }

    const heroPlay = $("#hero-play");
    if (heroPlay) heroPlay.dataset.playId = latest.id;
  }

  /* ---------- Año y total de episodios ---------- */
  const year = $("#year");
  if (year) year.textContent = new Date().getFullYear();

  const statEpisodes = $("#stat-episodes");
  if (statEpisodes) statEpisodes.textContent = EPISODES.length;

  /* ---------- Arranque ---------- */
  updateCounts();
  renderEpisodes();
  syncPlayIcons(false);
  updateToggle(false);
  setProgressFill(0);
})();
