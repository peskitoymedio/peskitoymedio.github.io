#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Actualiza la web de Peskito y Medio con los episodios nuevos del feed del podcast.

Uso:
    python actualizar.py              # actualiza la web
    python actualizar.py --dry-run    # solo comprueba, sin escribir nada
    python actualizar.py --feed RUTA  # usa otro feed local o URL (para pruebas)

Qué hace:
  - Descarga el feed oficial del podcast desde Feedburner.
  - Detecta los episodios que aún no están en js/episodes.js.
  - Descarga su portada en img/episodes/ (con nombre estable por ID de iVoox).
  - Guarda la descripción completa en HTML (sin imágenes) y un resumen recortado.
  - Lee los capítulos Podlove (psc:chapters) y descarga sus imágenes si las hay.
  - Añade los episodios y regenera js/episodes.js.
  - Genera una página HTML por episodio en episodios/ con datos estructurados
    PodcastEpisode, además del archivo completo en episodios/index.html.
  - Sincroniza sitemap.xml con la portada, el archivo y todas las páginas.
  - Guarda feed.xml y episodes-raw.json como copia de referencia.

No necesita dependencias externas: solo Python 3.9 o superior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FEED_URL = "https://feeds.feedburner.com/PeskitoYMedio"
EPISODES_JS = ROOT / "js" / "episodes.js"
IMG_DIR = ROOT / "img" / "episodes"
CHAPTER_IMG_DIR = ROOT / "img" / "chapters"
EPISODES_DIR = ROOT / "episodios"
RAW_JSON = ROOT / "episodes-raw.json"
FEED_XML = ROOT / "feed.xml"
SITEMAP_XML = ROOT / "sitemap.xml"
SITE_URL = "https://peskitoymedio.github.io/"
FALLBACK_IMG = "img/logo-800.jpg"
GENERATED_MARKER = "<!-- Página generada automáticamente por actualizar.py. No editar a mano. -->"

TYPE_LABEL = {
    "programa": "Programa",
    "especial": "Especial",
    "promo": "Promo",
    "colaboracion": "Colaboración",
}

MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

PROMO_HTML_PREFIX = re.compile(
    r"^\s*(?:<a\b[^>]*>\s*)?¡Vótame en los Premios iVoox.*?!\s*(?:</a>)?\s*(?:<br\s*/?>\s*)*",
    re.IGNORECASE | re.DOTALL,
)

# Minutajes dentro de una descripción: 01:15, 1:02:30…
DESCRIPTION_TIMESTAMP_RE = re.compile(r"(?<![\d:])(\d{1,2}:\d{2}(?::\d{2})?)(?![\d:])")
DESCRIPTION_LINE_BREAK_RE = re.compile(r"(<br\s*/?>)", re.IGNORECASE)

# Texto promocional que algunos episodios repiten al final de la descripción.
_DESCRIPTION_ANCHOR_OR_URL = r"(?:<a\b[^>]*>.*?</a>|https?://[^\s<]+)"
_TRAILING_DESCRIPTION_PATTERNS = (
    r"Enlace al programa en iVoox\s*:\s*" + _DESCRIPTION_ANCHOR_OR_URL,
    r"S[íi]guenos en nuestras redes sociales\s*:\s*" + _DESCRIPTION_ANCHOR_OR_URL,
    r"(?:<a\b[^>]*>\s*)?Suscr[íi]bete en iVoox(?:\s*</a>)?"
    r"(?:\s*y\s*dale\s+a\s*(?:<a\b[^>]*>\s*)?Me gusta(?:\s*</a>)?)?[.!]?",
)
TRAILING_DESCRIPTION_BOILERPLATE = re.compile(
    r"(?:(?:\s|<br\s*/?>)*)(?:"
    + "|".join(_TRAILING_DESCRIPTION_PATTERNS)
    + r")(?:(?:\s|<br\s*/?>)*)$",
    re.IGNORECASE | re.DOTALL,
)

# Expresión regular para detectar URLs en texto plano
URL_RE = re.compile(r"https?://[^\s<\"\']+", re.IGNORECASE)

# Invitación al canal de Telegram que aparece en mitad del bloque final.
TELEGRAM_DESCRIPTION_BLOCK = re.compile(
    r"Te recordamos que si quieres[^<]*(?:<a\b[^>]*>[^<]*</a>|https?://[^\s<]+)",
    re.IGNORECASE,
)

# Etiquetas que se conservan en las descripciones completas. Todo lo demás
# (imágenes, scripts, iframes…) se descarta.
ALLOWED_DESCRIPTION_TAGS = {
    "a", "b", "blockquote", "br", "em", "h3", "h4", "i", "li",
    "ol", "p", "span", "strong", "u", "ul",
}
VOID_DESCRIPTION_TAGS = {"br"}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def local_name(tag: str) -> str:
    """Devuelve el nombre de una etiqueta XML sin su namespace."""
    return tag.rsplit("}", 1)[-1].lower()


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Referer": "https://www.ivoox.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def child_attr(element: ET.Element, name: str, attribute: str) -> str:
    for child in element:
        if local_name(child.tag) == name:
            return (child.get(attribute) or "").strip()
    return ""


def chapter_seconds(value: str) -> int:
    """Convierte un minutaje Podlove ('HH:MM:SS', 'MM:SS' o segundos) a segundos."""
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return 0
    parts = raw.split(":")
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return 0
    if not numbers:
        return 0
    total = 0.0
    for number in numbers:
        total = total * 60 + number
    return max(0, int(total))


def chapter_time_label(value: str) -> str:
    """Minutaje compacto para mostrar: 00:00, 06:50 o 1:32:25."""
    total = chapter_seconds(value)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return str(hours) + ":" + f"{minutes:02d}" + ":" + f"{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def parse_chapters(item: ET.Element) -> list[dict]:
    """Lee los capítulos Podlove (psc:chapters) de un episodio del feed."""
    chapters: list[dict] = []
    for container in item:
        if container.tag != "{http://podlove.org/simple-chapters}chapters":
            continue
        for chapter in container:
            if local_name(chapter.tag) != "chapter":
                continue
            start = (chapter.get("start") or "").strip()
            title = (chapter.get("title") or "").strip()
            if not start or not title:
                continue
            entry = {"start": start, "title": title}
            href = (chapter.get("href") or "").strip()
            image = (chapter.get("image") or "").strip()
            if re.match(r"^https?://", href, re.IGNORECASE):
                entry["href"] = href
            if re.match(r"^https?://", image, re.IGNORECASE):
                entry["image"] = image
            chapters.append(entry)
    return chapters


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------

def parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    episodes: list[dict] = []

    for item in root.iter():
        if local_name(item.tag) != "item":
            continue

        title = child_text(item, "title")
        link = child_text(item, "link")
        pub_date = child_text(item, "pubdate")
        duration = child_text(item, "duration") or "00:00"
        description = child_text(item, "description") or child_text(item, "encoded")

        image = child_attr(item, "image", "href")
        if not image:
            for child in item:
                if local_name(child.tag) == "image":
                    image = child_text(child, "url")
                    break

        audio = ""
        social_uri = ""
        for child in item:
            if local_name(child.tag) == "enclosure":
                audio = (child.get("url") or "").strip()
            elif local_name(child.tag) == "socialinteract":
                social_uri = (child.get("uri") or "").strip()

        try:
            iso_date = parsedate_to_datetime(pub_date).date().isoformat()
        except (TypeError, ValueError):
            iso_date = pub_date[:10]

        episodes.append(
            {
                "title": title,
                "link": link,
                "date": pub_date,
                "duration": duration,
                "image": image,
                "audio": audio,
                "socialUri": social_uri,
                "chapters": parse_chapters(item),
                "desc": description,
                "_iso": iso_date,
            }
        )

    return episodes


def episode_key(link: str, audio: str) -> str:
    """ID estable del episodio (el número de audio de iVoox)."""
    for value in (link, audio):
        match = re.search(r"(?:rf_|_mf_)(\d+)", value or "")
        if match:
            return match.group(1)
    return hashlib.sha1(((link or "") + "|" + (audio or "")).encode("utf-8")).hexdigest()[:12]


class _DescriptionHTMLParser(HTMLParser):
    """Reconstruye una descripción conservando solo etiquetas y enlaces seguros."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_DESCRIPTION_TAGS:
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        if tag == "a":
            href = ""
            for name, value in attrs:
                if name.lower() == "href":
                    href = (value or "").strip()
                    break
            if not re.match(r"^(?:https?://|mailto:)", href, re.IGNORECASE):
                return
            self.parts.append(
                '<a href="' + escape(href, quote=True) + '" target="_blank" rel="noopener">'
            )
            self.stack.append("a")
            return
        self.parts.append("<" + tag + ">")
        self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_DESCRIPTION_TAGS and tag.lower() in self.stack:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in VOID_DESCRIPTION_TAGS or tag not in ALLOWED_DESCRIPTION_TAGS:
            return
        if tag not in self.stack:
            return
        while self.stack:
            open_tag = self.stack.pop()
            self.parts.append("</" + open_tag + ">")
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        if "a" in self.stack:
            self.parts.append(escape(data, quote=False))
            return

        last_idx = 0
        for match in URL_RE.finditer(data):
            start, end = match.span()
            if start > last_idx:
                self.parts.append(escape(data[last_idx:start], quote=False))

            url = match.group(0)
            trailing = ""
            while url and url[-1] in ".,;:?!)]":
                if url[-1] == ")" and "(" in url:
                    break
                trailing = url[-1] + trailing
                url = url[:-1]

            if url:
                self.parts.append(
                    '<a href="'
                    + escape(url, quote=True)
                    + '" target="_blank" rel="noopener">'
                    + escape(url, quote=False)
                    + "</a>"
                )
            if trailing:
                self.parts.append(escape(trailing, quote=False))

            last_idx = end - len(trailing)

        if last_idx < len(data):
            self.parts.append(escape(data[last_idx:], quote=False))

    def result(self) -> str:
        while self.stack:
            self.parts.append("</" + self.stack.pop() + ">")
        return "".join(self.parts)


def sanitize_description_html(raw: str) -> str:
    """Devuelve el HTML de la descripción sin imágenes ni contenido peligroso."""
    parser = _DescriptionHTMLParser()
    parser.feed(raw or "")
    parser.close()
    return parser.result()


def clean_description_html(raw: str) -> str:
    """Descripción completa en HTML, sin imágenes, promo ni autopromoción final."""
    html = sanitize_description_html(raw)
    html = html.replace("\r\n", "\n").replace("\r", "\n")
    html = PROMO_HTML_PREFIX.sub("", html)
    html = TELEGRAM_DESCRIPTION_BLOCK.sub("", html)
    html = strip_trailing_description_boilerplate(html)
    html = re.sub(r"^(?:\s|<br\s*/?>)+", "", html, flags=re.IGNORECASE)
    html = re.sub(r"(?:\s|<br\s*/?>)+$", "", html, flags=re.IGNORECASE)
    html = re.sub(r"(?:<br\s*/?>\s*){3,}", "<br><br>", html, flags=re.IGNORECASE)
    html = linkify_timestamp_lines(html)
    return html.strip()


def strip_trailing_description_boilerplate(html: str) -> str:
    """Elimina el bloque final de autopromoción (iVoox, redes y suscripción)."""
    previous = None
    while previous != html:
        previous = html
        html = TRAILING_DESCRIPTION_BOILERPLATE.sub("", html)
    return html


def timestamp_line_html(line: str) -> str:
    """Convierte una línea con minutaje en un control para saltar al audio."""
    match = DESCRIPTION_TIMESTAMP_RE.search(line)
    if not match:
        return line

    stamp = match.group(1)
    seconds = chapter_seconds(stamp)
    label = chapter_time_label(stamp)
    before = line[:match.start()]
    after = line[match.end():]
    text = plain_text_html(line)
    aria = "Escuchar desde " + label + (": " + text if text else "")
    role_attrs = "" if re.search(r"<a\b", line, re.IGNORECASE) else ' role="button" tabindex="0"'

    return (
        '<span class="ep-desc-line"'
        + role_attrs
        + ' data-desc-seek="'
        + str(seconds)
        + '" aria-label="'
        + attr(aria)
        + '">'
        + '<span class="ep-desc-line-text">'
        + before
        + '<span class="ep-desc-line-time"><i class="fa-solid fa-play" aria-hidden="true"></i>'
        + escape(label)
        + "</span>"
        + after
        + "</span>"
        + '<i class="fa-solid fa-headphones ep-desc-line-icon" aria-hidden="true"></i>'
        + "</span>"
    )


def linkify_timestamp_lines(html: str) -> str:
    """Hace clicables las líneas de la descripción que contienen un minutaje."""
    if not DESCRIPTION_TIMESTAMP_RE.search(html):
        return html

    result: list[str] = []
    for part in DESCRIPTION_LINE_BREAK_RE.split(html):
        if DESCRIPTION_LINE_BREAK_RE.fullmatch(part):
            result.append(part)
            continue
        if not DESCRIPTION_TIMESTAMP_RE.search(part):
            result.append(part)
            continue

        rendered: list[str] = []
        for line in part.split("\n"):
            if DESCRIPTION_TIMESTAMP_RE.search(line):
                rendered.append(timestamp_line_html(line.strip()))
            else:
                rendered.append(line)
        result.append("\n".join(rendered))

    cleaned = "".join(result)
    card_end = (
        r'(<i class="fa-solid fa-headphones ep-desc-line-icon" aria-hidden="true"></i></span>)'
    )
    card_start = r'(<span class="ep-desc-line")'
    # Las tarjetas ya son bloques: los <br> y saltos que las rodean solo añaden aire.
    cleaned = re.sub(card_end + r"(?:\s|<br\s*/?>)+", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:\s|<br\s*/?>)+" + card_start, r"\1", cleaned, flags=re.IGNORECASE)
    return cleaned


def plain_text_html(html: str) -> str:
    """Convierte HTML en texto plano de una sola línea (sin etiquetas)."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def summarize_html(html: str, limit: int = 190) -> str:
    """Convierte el HTML en texto plano y lo recorta con puntos suspensivos."""
    text = plain_text_html(html)

    if len(text) > limit:
        cut = text[:limit]
        last_space = cut.rfind(" ")
        if last_space > 0:
            cut = cut[:last_space]
        text = cut.rstrip(" .,-") + "…"

    return text


def classify(title: str) -> str:
    if re.match(r"^promo\b", title, re.IGNORECASE):
        return "promo"
    if not re.match(r"^PYM\b", title, re.IGNORECASE):
        return "colaboracion"
    # Solo es un especial si la palabra aparece con la E mayúscula. Así títulos
    # como "Todo es especial hoy" no se clasifican como especial por error.
    if re.search(r"\bEspecial\b", title):
        return "especial"
    # "Star Wars Special" también identifica a los especiales de Star Wars.
    if re.search(r"\bStar Wars Special\b", title):
        return "especial"
    return "programa"


def episode_number(title: str):
    match = re.match(r"^PYM\s+(\d+)", title, re.IGNORECASE)
    return int(match.group(1)) if match else None


def social_uri_for(episode: dict) -> str:
    """URL de conversación del episodio en X (feed o hashtag por número)."""
    uri = str(episode.get("socialUri") or "").strip()
    if uri:
        return uri
    number = episode.get("n")
    if number is not None:
        return "https://x.com/search?q=%23PYM" + str(number)
    return ""


# ---------------------------------------------------------------------------
# Slugs y URLs de las páginas de episodio
# ---------------------------------------------------------------------------

def slugify(text: str, limit: int = 90) -> str:
    """Convierte un título en un slug ASCII, estable y legible."""
    value = unescape(text or "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")

    if len(value) > limit:
        value = value[:limit].rsplit("-", 1)[0].rstrip("-")

    return value


def build_slug(episode: dict) -> str:
    base = slugify(episode.get("title", ""))
    if not base:
        base = "episodio-" + str(episode.get("id", "x"))
    return base


def ensure_slugs(episodes: list[dict]) -> int:
    """Asigna un slug único y estable a cada episodio que aún no lo tenga.

    Primero se reservan todos los slugs existentes para no cambiar la URL de un
    episodio antiguo cuando uno nuevo genere el mismo slug.
    """
    used: set[str] = set()
    pending: list[dict] = []

    for episode in episodes:
        slug = str(episode.get("slug") or "").strip()
        if slug and slug not in used:
            used.add(slug)
        else:
            pending.append(episode)

    changed = 0
    for episode in pending:
        base = build_slug(episode)
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = base + "-" + str(suffix)
            suffix += 1

        episode["slug"] = candidate
        used.add(candidate)
        changed += 1

    return changed


def episode_url(episode: dict) -> str:
    return SITE_URL + "episodios/" + episode["slug"] + ".html"


def episode_path(episode: dict) -> Path:
    return EPISODES_DIR / (episode["slug"] + ".html")


def absolute_url(path: str) -> str:
    return SITE_URL + str(path or "").lstrip("/")


def iso_duration(value: str) -> str:
    """Convierte '01:24:12', '84:12' o '00:00' a formato ISO 8601 (PT1H24M12S)."""
    parts = [part.strip() for part in str(value or "").split(":")]
    if not parts or not all(part.isdigit() for part in parts if part):
        return ""
    try:
        numbers = [int(part) for part in parts if part != ""]
    except ValueError:
        return ""
    if not numbers:
        return ""
    while len(numbers) < 3:
        numbers.insert(0, 0)
    hours, minutes, seconds = numbers[-3:]
    return "PT" + str(hours) + "H" + str(minutes) + "M" + str(seconds) + "S"


def format_date_es(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return value or ""
    return str(parsed.day) + " de " + MONTHS_ES[parsed.month - 1] + " de " + str(parsed.year)


def episode_badge(episode: dict) -> str:
    if episode.get("n") is not None:
        return "PYM " + str(episode["n"])
    if episode.get("type") == "promo":
        return "Promo"
    return "Colaboración" if episode.get("type") == "colaboracion" else "Especial"


def short_title(episode: dict) -> str:
    return re.sub(r"^PYM\s+\d+\.\s*", "", episode.get("title", ""))


def xml_text(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def attr(value: str) -> str:
    return escape(str(value or ""), quote=True)


def json_ld(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return (
        '<script type="application/ld+json">\n'
        + payload
        + "\n  </script>"
    )


# ---------------------------------------------------------------------------
# Datos actuales
# ---------------------------------------------------------------------------

def load_existing() -> list[dict]:
    if not EPISODES_JS.exists():
        return []

    text = EPISODES_JS.read_text(encoding="utf-8-sig")
    match = re.search(r"const\s+EPISODES\s*=\s*(\[.*\])\s*;", text, re.DOTALL)
    if not match:
        raise RuntimeError(
            "No se pudo leer js/episodes.js. ¿Se ha modificado su estructura?"
        )
    return json.loads(match.group(1))


def write_episodes(episodes: list[dict]) -> None:
    clean = []
    for episode in episodes:
        clean.append(
            {
                "id": episode["id"],
                "n": episode["n"],
                "type": episode["type"],
                "title": episode["title"],
                "date": episode["date"],
                "duration": episode["duration"],
                "link": episode["link"],
                "img": episode["img"],
                "audio": episode["audio"],
                "socialUri": episode.get("socialUri", ""),
                "chapters": episode.get("chapters", []),
                "desc": episode["desc"],
                "descHtml": episode.get("descHtml", ""),
                "slug": episode.get("slug", ""),
            }
        )

    body = json.dumps(clean, ensure_ascii=False, indent=4)
    EPISODES_JS.write_text(
        "/* Datos reales generados desde el feed oficial de Peskito y Medio (iVoox) */\n"
        "const EPISODES = " + body + ";\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------

def latest_episode_date(episodes: list[dict]) -> str:
    """Fecha ISO del episodio más reciente."""
    dates = [
        episode.get("date", "")
        for episode in episodes
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", episode.get("date", ""))
    ]
    return max(dates) if dates else ""


def build_sitemap(episodes: list[dict], lastmod: str) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    def add(location: str, modified: str, changefreq: str, priority: str) -> None:
        lines.extend(
            [
                "  <url>",
                "    <loc>" + xml_text(location) + "</loc>",
                "    <lastmod>" + xml_text(modified) + "</lastmod>",
                "    <changefreq>" + changefreq + "</changefreq>",
                "    <priority>" + priority + "</priority>",
                "  </url>",
            ]
        )

    add(SITE_URL, lastmod, "weekly", "1.0")
    add(SITE_URL + "episodios/", lastmod, "weekly", "0.8")
    for episode in episodes:
        if not episode.get("slug"):
            continue
        add(
            episode_url(episode),
            episode.get("date") or lastmod,
            "monthly",
            "0.6",
        )

    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def sync_sitemap(episodes: list[dict], dry_run: bool = False) -> None:
    lastmod = latest_episode_date(episodes)
    if not lastmod:
        return

    new = build_sitemap(episodes, lastmod)
    old = SITEMAP_XML.read_text(encoding="utf-8") if SITEMAP_XML.exists() else ""

    if new == old:
        return
    if not dry_run:
        try:
            SITEMAP_XML.write_text(new, encoding="utf-8")
        except OSError as error:
            print("AVISO: no se pudo actualizar sitemap.xml.")
            print("  " + str(error))
            return

    if dry_run:
        print("Sitemap que se actualizaría: " + str(len(episodes) + 2) + " URLs")
    else:
        print("Sitemap actualizado: " + str(len(episodes) + 2) + " URLs")


# ---------------------------------------------------------------------------
# Páginas de episodio y archivo
# ---------------------------------------------------------------------------

def write_if_changed(path: Path, content: str, dry_run: bool = False) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True


def cover_url(episode: dict, prefix: str) -> str:
    image = str(episode.get("img") or FALLBACK_IMG).lstrip("/")
    return prefix + image


def meta_description(episode: dict, limit: int = 158) -> str:
    text = re.sub(r"\s+", " ", str(episode.get("desc") or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip(" .,-") + "…"


def site_header(prefix: str, cta_html: str) -> str:
    return f"""  <header class="site-header" id="site-header">
    <div class="container nav-inner">
      <a class="brand" href="{prefix}index.html" aria-label="Peskito y Medio, ir al inicio">
        <span class="brand-badge"><img src="{prefix}img/logo-800.jpg" alt="" width="46" height="46"></span>
        <span class="brand-text">
          <span class="brand-name">Peskito</span>
          <span class="brand-sub">y Medio</span>
        </span>
      </a>

      <nav class="nav" id="nav" aria-label="Navegación principal">
        <a href="{prefix}index.html#sobre">El podcast</a>
        <a href="{prefix}index.html#presentacion">Presentación</a>
        <a href="{prefix}episodios/">Episodios</a>
        <a href="{prefix}index.html#equipo">Equipo</a>
        <a href="{prefix}index.html#reconocimientos">Reconocimientos</a>
        <a href="{prefix}index.html#escuchanos">Escúchanos</a>
      </nav>

      {cta_html}

      <button class="nav-toggle" id="nav-toggle" type="button" aria-expanded="false" aria-controls="nav" aria-label="Abrir menú">
        <span></span><span></span><span></span>
      </button>
    </div>
  </header>"""


def site_footer(prefix: str) -> str:
    year = str(date.today().year)
    return f"""  <footer class="site-footer">
    <div class="container footer-grid">
      <div class="footer-brand">
        <a class="brand brand--footer" href="{prefix}index.html" aria-label="Peskito y Medio, ir al inicio">
          <span class="brand-badge"><img src="{prefix}img/logo-800.jpg" alt="" width="46" height="46"></span>
          <span class="brand-text">
            <span class="brand-name">Peskito</span>
            <span class="brand-sub">y Medio</span>
          </span>
        </a>
        <p>Tu podcast friki. Series, cómics, juegos de mesa, doramas, bandas sonoras y muchas risas entre amig@s.</p>
        <div class="footer-social" aria-label="Redes sociales">
          <a href="https://www.instagram.com/peskitoymedio" target="_blank" rel="noopener" aria-label="Instagram"><i class="fa-brands fa-instagram" aria-hidden="true"></i></a>
          <a href="https://x.com/peskito3" target="_blank" rel="noopener" aria-label="X / Twitter"><i class="fa-brands fa-x-twitter" aria-hidden="true"></i></a>
          <a href="https://facebook.com/PeskitoYMedio" target="_blank" rel="noopener" aria-label="Facebook"><i class="fa-brands fa-facebook-f" aria-hidden="true"></i></a>
          <a href="https://mastodon.social/@PeskitoyMedio" target="_blank" rel="noopener" aria-label="Mastodon"><i class="fa-brands fa-mastodon" aria-hidden="true"></i></a>
          <a href="https://vm.tiktok.com/ZMFQnXacU/" target="_blank" rel="noopener" aria-label="TikTok"><i class="fa-brands fa-tiktok" aria-hidden="true"></i></a>
          <a href="https://t.me/peskiters3" target="_blank" rel="noopener" aria-label="Telegram"><i class="fa-brands fa-telegram" aria-hidden="true"></i></a>
        </div>
      </div>

      <div class="footer-col">
        <h3>Explora</h3>
        <a href="{prefix}index.html#sobre">El podcast</a>
        <a href="{prefix}episodios/">Todos los episodios</a>
        <a href="{prefix}index.html#equipo">Equipo</a>
        <a href="{prefix}index.html#reconocimientos">Reconocimientos</a>
        <a href="{prefix}index.html#escuchanos">Escúchanos</a>
      </div>

      <div class="footer-col">
        <h3>Escúchanos</h3>
        <a href="https://www.ivoox.com/podcast-peskito-medio-tu-podcast-friki_sq_f1661614_1.html" target="_blank" rel="noopener">iVoox</a>
        <a href="https://open.spotify.com/show/3dxYih3F7UfO4Oeser3W0I" target="_blank" rel="noopener">Spotify</a>
        <a href="https://itunes.apple.com/es/podcast/peskito-y-medio/id1453280178" target="_blank" rel="noopener">Apple Podcasts</a>
        <a href="https://youtube.com/channel/UCXAHPVKfZA6GyViUag-nBgw" target="_blank" rel="noopener">YouTube</a>
        <a href="https://feeds.feedburner.com/PeskitoYMedio" target="_blank" rel="noopener">RSS</a>
      </div>

      <div class="footer-col">
        <h3>Contacto</h3>
        <a href="mailto:peskitoymedio@gmail.com">peskitoymedio@gmail.com</a>
        <a href="https://t.me/peskiters3" target="_blank" rel="noopener">Grupo de peskiters</a>
        <a href="https://x.com/peskito3" target="_blank" rel="noopener">@peskito3</a>
        <a href="https://t.me/frikinews" target="_blank" rel="noopener">Canal de noticias frikis en Telegram</a>
      </div>
    </div>

    <div class="container footer-bottom">
      <p>© <span id="year">{year}</span> Peskito y Medio · Tu Podcast Friki. Hecho con ukelele, risas y mucho cariño.</p>
      <p class="footer-credits">Datos y portadas: <a href="https://www.ivoox.com/podcast-peskito-medio-tu-podcast-friki_sq_f1661614_1.html" target="_blank" rel="noopener">iVoox</a> · Web estática hecha por un peskito.</p>
    </div>
  </footer>"""


def topbar(prefix: str, latest: dict | None, current: bool = False) -> str:
    if current:
        link = prefix + "index.html#episodios"
        label = "Peskito y Medio"
        detail = "Tu podcast friki"
    elif latest:
        link = prefix + "episodios/" + latest["slug"] + ".html"
        label = "Último programa:"
        detail = episode_badge(latest) + " · " + short_title(latest)
    else:
        link = prefix + "index.html#episodios"
        label = "Peskito y Medio"
        detail = "Tu podcast friki"

    return f"""  <div class="topbar">
    <div class="container topbar-inner">
      <a class="topbar-item topbar-latest" href="{attr(link)}">
        <span class="topbar-dot" aria-hidden="true"></span>
        <span class="topbar-latest-label">{escape(label)}</span>
        <strong>{escape(detail)}</strong>
      </a>
    </div>
  </div>"""


def player_html(episode: dict) -> str:
    audio = str(episode.get("audio") or "")
    subtitle = (
        "Peskito y Medio · "
        + TYPE_LABEL.get(episode.get("type", ""), "Episodio")
        + " · "
        + str(episode.get("duration") or "")
    )
    return f"""  <div class="mini-player" id="player" aria-hidden="true"
       data-audio="{attr(audio)}"
       data-title="{attr(episode.get('title', ''))}"
       data-image="{attr(cover_url(episode, '../'))}"
       data-subtitle="{attr(subtitle)}"
       data-cover-alt="{attr('Portada de ' + episode.get('title', ''))}">
    <div class="player-inner">
      <img class="player-cover" id="player-cover" src="{cover_url(episode, '../')}" alt="" width="56" height="56">
      <div class="player-info">
        <strong class="player-title" id="player-title">{escape(episode.get('title', ''))}</strong>
        <span class="player-sub" id="player-sub">{escape(subtitle)}</span>
      </div>
      <div class="player-progress-wrap">
        <input class="player-progress" id="player-progress" type="range" min="0" max="100" step="0.1" value="0" aria-label="Progreso del episodio">
        <div class="player-time">
          <span id="player-current">0:00</span>
          <span id="player-duration">{escape(episode.get('duration', '0:00'))}</span>
        </div>
      </div>
      <button class="player-btn" id="player-toggle" type="button" aria-label="Reproducir o pausar">
        <i class="fa-solid fa-play" aria-hidden="true"></i>
      </button>
      <button class="player-close" id="player-close" type="button" aria-label="Cerrar reproductor">
        <i class="fa-solid fa-xmark" aria-hidden="true"></i>
      </button>
      <audio id="audio" preload="metadata" src="{attr(audio)}"></audio>
    </div>
  </div>"""


def episode_card(episode: dict, index: int = 0, with_search_text: bool = False) -> str:
    title = escape(episode.get("title", ""), quote=True)
    link = episode["slug"] + ".html"
    badge = escape(episode_badge(episode))
    type_name = episode.get("type", "programa")
    type_label = TYPE_LABEL.get(type_name, "Episodio")
    image = cover_url(episode, "../")
    search_text = ""
    if with_search_text:
        search_text = (
            '\n          <div class="ep-search-text" hidden>'
            + escape(plain_text_html(episode.get("descHtml") or episode.get("desc", "")))
            + "</div>"
        )
    return f"""      <article class="ep-card" style="--i:{index % 12}" data-type="{attr(type_name)}">
        <div class="ep-cover">
          <a class="ep-cover-link" href="{link}" aria-label="Ver la ficha de {title}">
            <img src="{attr(image)}" alt="Portada del episodio: {title}" loading="lazy" width="400" height="400">
          </a>
          <span class="ep-badge">{badge}</span>
          <span class="ep-duration"><i class="fa-regular fa-clock" aria-hidden="true"></i> {escape(episode.get('duration', ''))}</span>
        </div>
        <div class="ep-body">
          <div class="ep-meta">
            <span class="ep-type ep-type--{attr(type_name)}">{escape(type_label)}</span>
            <time datetime="{attr(episode.get('date', ''))}">{escape(format_date_es(episode.get('date', '')))}</time>
          </div>
          <h3 class="ep-title"><a class="ep-title-link" href="{link}">{escape(episode.get('title', ''))}</a></h3>
          <p class="ep-desc">{escape(episode.get('desc', ''))}</p>{search_text}
          <a class="ep-link" href="{link}">Ver el episodio <i class="fa-solid fa-arrow-right" aria-hidden="true"></i></a>
        </div>
      </article>"""


def related_episodes(episodes: list[dict], current: dict, limit: int = 3) -> list[dict]:
    others = [episode for episode in episodes if episode.get("slug") != current.get("slug")]
    chosen = [episode for episode in others if episode.get("type") == current.get("type")][:limit]
    for episode in others:
        if len(chosen) >= limit:
            break
        if episode not in chosen:
            chosen.append(episode)
    return chosen[:limit]


def chapters_html(episode: dict) -> str:
    """Sección de capítulos Podlove con enlace al minuto correspondiente."""
    chapters = episode.get("chapters") or []
    if not chapters:
        return ""

    items: list[str] = []
    for chapter in chapters:
        title = str(chapter.get("title") or "")
        start = str(chapter.get("start") or "")
        seconds = chapter_seconds(start)
        label = chapter_time_label(start)
        href = str(chapter.get("href") or "")
        media = local_chapter_image(episode, chapter) or str(chapter.get("image") or "")

        extra_parts: list[str] = []
        if media:
            thumb_src = "../" + media if media.startswith("img/") else media
            thumb = (
                '<img src="'
                + attr(thumb_src)
                + '" alt="'
                + attr("Imagen de la sección: " + title)
                + '" loading="lazy" width="72" height="72">'
            )
            if href:
                extra_parts.append(
                    '<a class="ep-chapter-thumb" href="'
                    + attr(href)
                    + '" target="_blank" rel="noopener" aria-label="'
                    + attr("Abrir el enlace de " + title)
                    + '">'
                    + thumb
                    + "</a>"
                )
            else:
                extra_parts.append('<span class="ep-chapter-thumb">' + thumb + "</span>")
        if href:
            extra_parts.append(
                '<a class="ep-chapter-link" href="'
                + attr(href)
                + '" target="_blank" rel="noopener">Ver enlace '
                + '<i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i></a>'
            )

        extra = ""
        if extra_parts:
            extra = (
                '\n              <div class="ep-chapter-extra">'
                + "".join(extra_parts)
                + "</div>"
            )

        items.append(
            f"""            <li class="ep-chapter-item">
              <button class="ep-chapter" type="button" data-chapter-start="{seconds}"
                      aria-label="{attr('Escuchar desde ' + label + ': ' + title)}">
                <span class="ep-chapter-time"><i class="fa-solid fa-play" aria-hidden="true"></i> {escape(label)}</span>
                <span class="ep-chapter-title">{escape(title)}</span>
                <i class="fa-solid fa-headphones ep-chapter-icon" aria-hidden="true"></i>
              </button>{extra}
            </li>"""
        )

    count = len(chapters)
    count_label = str(count) + (" sección" if count == 1 else " secciones")
    return f"""          <section class="ep-chapters" aria-labelledby="chapters-title">
            <div class="ep-chapters-head">
              <h2 id="chapters-title"><i class="fa-solid fa-list-ul" aria-hidden="true"></i> Secciones</h2>
              <span class="ep-chapters-count">{count_label}</span>
            </div>
            <p class="ep-chapters-hint">Pincha en una sección para escucharla desde ese minuto.</p>
            <ol class="ep-chapters-list">
{chr(10).join(items)}
            </ol>
          </section>"""


def build_episode_page(episode: dict, episodes: list[dict], latest: dict | None) -> str:
    url = episode_url(episode)
    image = absolute_url(episode.get("img") or FALLBACK_IMG)
    description = meta_description(episode)
    title = episode.get("title", "")
    badge = episode_badge(episode)
    type_name = episode.get("type", "programa")
    type_label = TYPE_LABEL.get(type_name, "Episodio")
    date_es = format_date_es(episode.get("date", ""))
    duration_iso = iso_duration(episode.get("duration", ""))
    social_uri = social_uri_for(episode)

    index = next(
        (position for position, item in enumerate(episodes) if item.get("slug") == episode.get("slug")),
        -1,
    )
    newer = episodes[index - 1] if index > 0 else None
    older = episodes[index + 1] if 0 <= index < len(episodes) - 1 else None

    episode_ld = {
        "@context": "https://schema.org",
        "@type": "PodcastEpisode",
        "@id": url + "#episode",
        "url": url,
        "name": title,
        "description": description,
        "datePublished": episode.get("date", ""),
        "inLanguage": "es-ES",
        "image": image,
    }
    if episode.get("n") is not None:
        episode_ld["episodeNumber"] = episode["n"]
    if duration_iso:
        episode_ld["duration"] = duration_iso
    if episode.get("audio"):
        episode_ld["associatedMedia"] = {
            "@type": "MediaObject",
            "contentUrl": episode["audio"],
            "encodingFormat": "audio/mpeg",
        }
    episode_ld["partOfSeries"] = {
        "@type": "PodcastSeries",
        "@id": SITE_URL + "#podcast",
        "name": "Peskito y Medio - Tu Podcast Friki",
        "url": SITE_URL,
        "webFeed": "https://feeds.feedburner.com/PeskitoYMedio",
    }
    episode_ld["author"] = {
        "@type": "Organization",
        "name": "Peskito y Medio",
        "url": SITE_URL,
    }

    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Inicio", "item": SITE_URL},
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Episodios",
                "item": SITE_URL + "episodios/",
            },
            {"@type": "ListItem", "position": 3, "name": title, "item": url},
        ],
    }

    notes = episode.get("descHtml") or "<p>" + escape(episode.get("desc", "")) + "</p>"
    ivoox_cta = (
        '<div class="ep-notes-cta">'
        '<a class="btn btn-primary btn-sm ep-notes-ivoox" href="'
        + attr(episode.get("link") or "#")
        + '" target="_blank" rel="noopener">'
        '<i class="fa-solid fa-headphones" aria-hidden="true"></i> '
        "Episodio en iVoox "
        '<i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i>'
        "</a></div>"
    )

    pager = ""
    if newer or older:
        parts = []
        if older:
            parts.append(
                f"""        <a class="ep-pager-link" href="{older['slug']}.html">
          <span><i class="fa-solid fa-arrow-left" aria-hidden="true"></i> Episodio anterior</span>
          <strong>{escape(older.get('title', ''))}</strong>
        </a>"""
            )
        else:
            parts.append('        <span class="ep-pager-empty" aria-hidden="true"></span>')
        if newer:
            parts.append(
                f"""        <a class="ep-pager-link ep-pager-link--next" href="{newer['slug']}.html">
          <span>Episodio siguiente <i class="fa-solid fa-arrow-right" aria-hidden="true"></i></span>
          <strong>{escape(newer.get('title', ''))}</strong>
        </a>"""
            )
        pager = (
            '      <nav class="ep-pager" aria-label="Navegación entre episodios">\n'
            '        <div class="container ep-pager-grid">\n'
            + "\n".join(parts)
            + "\n        </div>\n      </nav>"
        )

    related = related_episodes(episodes, episode)
    related_html = ""
    if related:
        cards = "\n".join(episode_card(item, position) for position, item in enumerate(related))
        related_html = f"""    <section class="ep-related" aria-labelledby="related-title">
      <div class="container">
        <div class="section-head reveal">
          <div>
            <span class="section-kicker">Sigue escuchando</span>
            <h2 id="related-title">Más <span class="marker marker--orange">Peskito</span></h2>
          </div>
          <a class="btn btn-ghost" href="index.html">Ver todo el archivo <i class="fa-solid fa-arrow-right" aria-hidden="true"></i></a>
        </div>
        <div class="episode-grid">
{cards}
        </div>
      </div>
    </section>"""

    facts_social = ""
    if social_uri:
        facts_social = f"""          <a class="ep-facts-link ep-facts-link--x" href="{attr(social_uri)}" target="_blank" rel="noopener">
            Comenta en X <i class="fa-brands fa-x-twitter" aria-hidden="true"></i>
          </a>"""

    facts_telegram = """          <a class="ep-facts-link ep-facts-link--telegram" href="https://t.me/peskiters3" target="_blank" rel="noopener">
            Comenta en Telegram <i class="fa-brands fa-telegram" aria-hidden="true"></i>
          </a>"""

    chapters = chapters_html(episode)

    cta = (
        '<button class="btn btn-primary btn-sm nav-cta" type="button" data-episode-play>'
        '<i class="fa-solid fa-play" aria-hidden="true"></i> Dale al play</button>'
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} · Peskito y Medio</title>
  <meta name="description" content="{attr(description)}">
  <meta name="author" content="Peskito y Medio">
  <meta name="theme-color" content="#0B1B2D">
  <link rel="canonical" href="{attr(url)}">
  <link rel="icon" type="image/png" href="../img/favicon.png">
  <link rel="apple-touch-icon" href="../img/apple-touch-icon.png">
  <link rel="sitemap" type="application/xml" title="Sitemap" href="../sitemap.xml">
  <link rel="alternate" type="application/rss+xml" title="Peskito y Medio · RSS" href="https://feeds.feedburner.com/PeskitoYMedio">

  <!-- Open Graph -->
  <meta property="og:type" content="article">
  <meta property="og:locale" content="es_ES">
  <meta property="og:site_name" content="Peskito y Medio">
  <meta property="og:title" content="{attr(title)}">
  <meta property="og:description" content="{attr(description)}">
  <meta property="og:url" content="{attr(url)}">
  <meta property="og:image" content="{attr(image)}">
  <meta property="og:image:alt" content="{attr('Portada del episodio: ' + title)}">
  <meta property="article:published_time" content="{attr(episode.get('date', ''))}">
  <meta property="article:section" content="{attr(type_label)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@peskito3">
  <meta name="twitter:title" content="{attr(title)}">
  <meta name="twitter:description" content="{attr(description)}">
  <meta name="twitter:image" content="{attr(image)}">

  <!-- Fuentes e iconos -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="preconnect" href="https://cdnjs.cloudflare.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Bangers&family=Outfit:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" referrerpolicy="no-referrer">
  <link rel="stylesheet" href="../css/styles.css">
  <link rel="stylesheet" href="../css/episodio.css">

  <!-- Datos estructurados -->
  {json_ld(episode_ld)}
  {json_ld(breadcrumb_ld)}
</head>
<body>
  {GENERATED_MARKER}
  <a class="skip-link" href="#main">Saltar al contenido</a>

{topbar("../", latest, current=True)}

{site_header("../", cta)}

  <main id="main">
    <div class="container">
      <nav class="ep-breadcrumb" aria-label="Migas de pan">
        <ol>
          <li><a href="../index.html">Inicio</a></li>
          <li><a href="index.html">Episodios</a></li>
          <li aria-current="page">{escape(badge)}</li>
        </ol>
      </nav>
    </div>

    <section class="ep-detail" aria-labelledby="episode-title">
      <div class="ep-detail-bg" aria-hidden="true"></div>
      <div class="container ep-detail-grid">
        <figure class="ep-detail-cover reveal">
          <img src="{attr(cover_url(episode, '../'))}" alt="{attr('Portada del episodio: ' + title)}" width="600" height="600">
        </figure>

        <div class="ep-detail-copy">
          <span class="eyebrow"><i class="fa-solid fa-microphone-lines" aria-hidden="true"></i> Archivo peskiter</span>
          <h1 class="ep-detail-title" id="episode-title">{escape(title)}</h1>

          <div class="ep-detail-meta">
            <span class="ep-type ep-type--{attr(type_name)}">{escape(type_label)}</span>
            <time datetime="{attr(episode.get('date', ''))}"><i class="fa-regular fa-calendar" aria-hidden="true"></i> {escape(date_es)}</time>
            <span><i class="fa-regular fa-clock" aria-hidden="true"></i> {escape(episode.get('duration', ''))}</span>
          </div>

          <div class="ep-detail-actions">
            <button class="btn btn-primary btn-lg" type="button" data-episode-play>
              <span class="btn-play-icon"><i class="fa-solid fa-play" aria-hidden="true"></i></span>
              Escuchar aquí
            </button>
            <a class="btn btn-ghost btn-lg" href="{attr(episode.get('link', '#'))}" target="_blank" rel="noopener">
              Escuchar en iVoox <i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i>
            </a>
          </div>
        </div>
      </div>
    </section>

    <section class="ep-notes-section">
      <div class="container ep-notes-layout">
        <article class="ep-notes reveal">
          <span class="section-kicker">Notas del episodio</span>
          <h2>De qué va este <span class="marker marker--teal">Peskito</span></h2>
          <div class="ep-notes-body">
            {notes}
          </div>
          {ivoox_cta}
        </article>

        <aside class="ep-sidebar reveal{' ep-sidebar--chapters' if chapters else ''}" aria-label="Información del episodio">
          <div class="ep-facts">
            <h2 id="facts-title">Ficha rápida</h2>
            <dl>
              <div><dt>Programa</dt><dd>{escape(badge)}</dd></div>
              <div><dt>Tipo</dt><dd>{escape(type_label)}</dd></div>
              <div><dt>Publicado</dt><dd>{escape(date_es)}</dd></div>
              <div><dt>Duración</dt><dd>{escape(episode.get('duration', ''))}</dd></div>
            </dl>
            <a class="ep-facts-link" href="{attr(episode.get('link', '#'))}" target="_blank" rel="noopener">
              Comenta en iVoox <i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i>
            </a>
{facts_social}
{facts_telegram}
            <a class="ep-facts-link ep-facts-link--soft" href="index.html">
              Ver todos los episodios <i class="fa-solid fa-arrow-right" aria-hidden="true"></i>
            </a>
          </div>
{chapters}
        </aside>
      </div>
    </section>

{pager}

{related_html}
  </main>

{site_footer("../")}

{player_html(episode)}

  <script src="../js/episode.js"></script>
</body>
</html>
"""


def build_archive_page(episodes: list[dict], latest: dict | None) -> str:
    url = SITE_URL + "episodios/"
    description = (
        "Archivo completo de Peskito y Medio: todos los episodios, especiales, "
        "colaboraciones y promos del podcast friki. Escucha cada programa y sus notas."
    )

    cards = "\n".join(
        episode_card(episode, index, with_search_text=True)
        for index, episode in enumerate(episodes)
    )
    type_counts = {"all": len(episodes)}
    for episode in episodes:
        type_name = episode.get("type", "programa")
        type_counts[type_name] = type_counts.get(type_name, 0) + 1

    collection_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "@id": url + "#archive",
        "url": url,
        "name": "Todos los episodios de Peskito y Medio",
        "description": description,
        "inLanguage": "es-ES",
        "isPartOf": {
            "@type": "WebSite",
            "@id": SITE_URL + "#website",
            "name": "Peskito y Medio",
            "url": SITE_URL,
        },
        "mainEntity": {
            "@type": "ItemList",
            "name": "Episodios de Peskito y Medio",
            "numberOfItems": len(episodes),
            "itemListOrder": "https://schema.org/ItemListOrderDescending",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": position,
                    "url": episode_url(episode),
                }
                for position, episode in enumerate(episodes, start=1)
            ],
        },
    }

    breadcrumb_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Inicio", "item": SITE_URL},
            {"@type": "ListItem", "position": 2, "name": "Episodios", "item": url},
        ],
    }

    cta = (
        '<a class="btn btn-primary btn-sm nav-cta" href="../index.html#episodios">'
        '<i class="fa-solid fa-play" aria-hidden="true"></i> Dale al play</a>'
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Todos los episodios · Peskito y Medio</title>
  <meta name="description" content="{attr(description)}">
  <meta name="author" content="Peskito y Medio">
  <meta name="theme-color" content="#0B1B2D">
  <link rel="canonical" href="{attr(url)}">
  <link rel="icon" type="image/png" href="../img/favicon.png">
  <link rel="apple-touch-icon" href="../img/apple-touch-icon.png">
  <link rel="sitemap" type="application/xml" title="Sitemap" href="../sitemap.xml">
  <link rel="alternate" type="application/rss+xml" title="Peskito y Medio · RSS" href="https://feeds.feedburner.com/PeskitoYMedio">

  <meta property="og:type" content="website">
  <meta property="og:locale" content="es_ES">
  <meta property="og:site_name" content="Peskito y Medio">
  <meta property="og:title" content="Todos los episodios · Peskito y Medio">
  <meta property="og:description" content="{attr(description)}">
  <meta property="og:url" content="{attr(url)}">
  <meta property="og:image" content="{attr(absolute_url('img/logo-800.jpg'))}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@peskito3">
  <meta name="twitter:title" content="Todos los episodios · Peskito y Medio">
  <meta name="twitter:description" content="{attr(description)}">

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="preconnect" href="https://cdnjs.cloudflare.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Bangers&family=Outfit:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" referrerpolicy="no-referrer">
  <link rel="stylesheet" href="../css/styles.css">
  <link rel="stylesheet" href="../css/episodio.css">

  {json_ld(collection_ld)}
  {json_ld(breadcrumb_ld)}
</head>
<body>
  {GENERATED_MARKER}
  <a class="skip-link" href="#main">Saltar al contenido</a>

{topbar("../", latest)}

{site_header("../", cta)}

  <main id="main">
    <div class="container">
      <nav class="ep-breadcrumb" aria-label="Migas de pan">
        <ol>
          <li><a href="../index.html">Inicio</a></li>
          <li aria-current="page">Episodios</li>
        </ol>
      </nav>
    </div>

    <section class="archive-intro">
      <div class="container">
        <span class="eyebrow"><i class="fa-solid fa-box-archive" aria-hidden="true"></i> Archivo peskiter</span>
        <h1>Todos los <span class="marker marker--orange">episodios</span></h1>
        <p>Aquí tienes el archivo completo de Peskito y Medio: programas, especiales, colaboraciones y promos. Cada episodio tiene su ficha con sus notas, su ficha rápida y su reproductor. Elige uno y dale al play.</p>
        <p class="archive-intro-meta"><strong>{len(episodes)}</strong> episodios publicados · del más reciente al más antiguo</p>
      </div>
    </section>

    <section class="episodes" id="episodios">
      <div class="episodes-bg" aria-hidden="true"></div>
      <div class="container">
        <div class="episode-controls reveal">
          <div class="filters" role="group" aria-label="Filtrar episodios">
            <button class="filter is-active" type="button" data-filter="all">Todos <span class="filter-count" data-count="all">{type_counts.get('all', 0)}</span></button>
            <button class="filter" type="button" data-filter="programa">Programas normales <span class="filter-count" data-count="programa">{type_counts.get('programa', 0)}</span></button>
            <button class="filter" type="button" data-filter="especial">Especiales <span class="filter-count" data-count="especial">{type_counts.get('especial', 0)}</span></button>
            <button class="filter" type="button" data-filter="promo">Promos <span class="filter-count" data-count="promo">{type_counts.get('promo', 0)}</span></button>
            <button class="filter" type="button" data-filter="colaboracion">Colaboraciones <span class="filter-count" data-count="colaboracion">{type_counts.get('colaboracion', 0)}</span></button>
          </div>
          <label class="search">
            <i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i>
            <span class="sr-only">Buscar episodios</span>
            <input type="search" id="archive-search" placeholder="Buscar por título o tema…" autocomplete="off">
          </label>
        </div>

        <p class="episode-count" id="archive-count" aria-live="polite">Mostrando {len(episodes)} de {len(episodes)} episodios</p>

        <div class="episode-grid" id="archive-grid">
{cards}
          <div class="empty-state" id="archive-empty" hidden><strong>No hay resultados</strong>Prueba con otra búsqueda o cambia el filtro. ¡Seguro que hay un Peskito para ti!</div>
        </div>
      </div>
    </section>
  </main>

{site_footer("../")}

  <script src="../js/episode.js"></script>
</body>
</html>
"""


def cleanup_stale_pages(expected: set[str], dry_run: bool = False) -> int:
    """Elimina solo páginas generadas que ya no corresponden a ningún episodio."""
    if not EPISODES_DIR.exists():
        return 0

    removed = 0
    for path in EPISODES_DIR.glob("*.html"):
        if path.name in expected:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if GENERATED_MARKER not in content:
            continue
        if not dry_run:
            try:
                path.unlink()
            except OSError:
                continue
        removed += 1
    return removed


def generate_site(episodes: list[dict], dry_run: bool = False) -> tuple[int, int]:
    """Genera las páginas de episodio y el archivo. Devuelve (escritas, eliminadas)."""
    ordered = sorted(episodes, key=lambda item: item.get("date", ""), reverse=True)
    latest = ordered[0] if ordered else None

    written = 0
    expected = {"index.html"}
    for episode in ordered:
        if not episode.get("slug"):
            continue
        expected.add(episode["slug"] + ".html")
        if write_if_changed(episode_path(episode), build_episode_page(episode, ordered, latest), dry_run):
            written += 1

    if write_if_changed(
        EPISODES_DIR / "index.html",
        build_archive_page(ordered, latest),
        dry_run,
    ):
        written += 1

    removed = cleanup_stale_pages(expected, dry_run)

    if dry_run:
        if written or removed:
            print(
                "Páginas que se generarían: "
                + str(written)
                + (" · se eliminarían " + str(removed) if removed else "")
            )
    else:
        print(
            "Páginas de episodio actualizadas: "
            + str(written)
            + (" · eliminadas " + str(removed) if removed else "")
        )

    return written, removed


# ---------------------------------------------------------------------------
# Portadas
# ---------------------------------------------------------------------------

def optimize_cover(path: Path, max_size: int = 600) -> str | None:
    """Reduce la portada si hay Pillow o ffmpeg disponibles. Devuelve el método usado."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((max_size, max_size), Image.LANCZOS)
            image.save(path, "JPEG", quality=84, optimize=True, progressive=True)
        return "Pillow"
    except ImportError:
        pass
    except Exception:
        pass

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        temporary = path.with_suffix(".tmp.jpg")
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(path),
                    "-vf",
                    "scale=" + str(max_size) + ":" + str(max_size)
                    + ":force_original_aspect_ratio=decrease",
                    "-q:v",
                    "3",
                    str(temporary),
                ],
                check=True,
                timeout=120,
            )
            temporary.replace(path)
            return "ffmpeg"
        except (subprocess.SubprocessError, OSError):
            temporary.unlink(missing_ok=True)

    return None


def download_cover(url: str, destination: Path) -> str | None:
    """Descarga la portada. Devuelve el método de optimización o None si no había que descargar."""
    if destination.exists() and destination.stat().st_size > 1000:
        return None
    if not url:
        return None

    data = fetch_bytes(url)
    if len(data) < 1000:
        raise ValueError("la imagen descargada es demasiado pequeña")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)

    return optimize_cover(destination) or "sin optimizar"


# ---------------------------------------------------------------------------
# Imágenes de los capítulos
# ---------------------------------------------------------------------------

def chapter_image_name(episode: dict, chapter: dict) -> str:
    """Nombre estable y local para la imagen de un capítulo."""
    extension = Path(urllib.parse.urlparse(str(chapter.get("image") or "")).path).suffix.lower()
    if extension in {".jpeg"}:
        extension = ".jpg"
    if extension not in {".jpg", ".png", ".gif", ".webp", ".avif"}:
        extension = ".jpg"
    key = episode_key(episode.get("link", ""), episode.get("audio", ""))
    return (
        "ch-"
        + key
        + "-"
        + str(chapter_seconds(chapter.get("start", "")))
        + extension
    )


def local_chapter_image(episode: dict, chapter: dict) -> str:
    """Ruta local de la imagen del capítulo si ya se ha descargado."""
    name = chapter_image_name(episode, chapter)
    if (CHAPTER_IMG_DIR / name).exists():
        return "img/chapters/" + name
    return ""


def sync_chapter_images(episodes: list[dict], dry_run: bool = False) -> int:
    """Descarga las imágenes asociadas a capítulos para servirlas desde el sitio."""
    if dry_run:
        return 0

    downloaded = 0
    for episode in episodes:
        for chapter in episode.get("chapters") or []:
            image = str(chapter.get("image") or "")
            if not re.match(r"^https?://", image, re.IGNORECASE):
                continue

            destination = CHAPTER_IMG_DIR / chapter_image_name(episode, chapter)
            if destination.exists() and destination.stat().st_size > 1000:
                continue

            try:
                data = fetch_bytes(image)
                if len(data) < 1000:
                    raise ValueError("la imagen descargada es demasiado pequeña")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                optimize_cover(destination, max_size=360)
                downloaded += 1
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
                print("  AVISO: no se pudo descargar la imagen del capítulo «" + chapter.get("title", "") + "»")
                print("         " + str(error))

    return downloaded



# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Añade a la web los episodios nuevos del feed de Peskito y Medio."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="muestra los episodios nuevos sin descargar ni escribir nada",
    )
    parser.add_argument(
        "--feed",
        default=FEED_URL,
        help="URL o ruta de un feed alternativo (para pruebas)",
    )
    args = parser.parse_args()

    try:
        if re.match(r"^https?://", args.feed, re.IGNORECASE):
            xml_bytes = fetch_bytes(args.feed)
        else:
            xml_bytes = Path(args.feed).read_bytes()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        print("ERROR: no se pudo descargar el feed.")
        print("  " + str(error))
        print("Comprueba tu conexión a internet y vuelve a intentarlo.")
        return 1

    feed_episodes = parse_feed(xml_bytes)
    if not feed_episodes:
        print("ERROR: el feed no contiene episodios.")
        return 1

    try:
        existing = load_existing()
    except (RuntimeError, json.JSONDecodeError) as error:
        print("ERROR: " + str(error))
        return 1

    # Reclasificar el archivo existente con las reglas actuales
    reclassified = 0
    for episode in existing:
        expected = classify(episode.get("title", ""))
        if episode.get("type") != expected:
            episode["type"] = expected
            reclassified += 1

    # Refrescar las descripciones completas con el contenido actual del feed
    feed_by_key = {
        episode_key(item["link"], item["audio"]): item for item in feed_episodes
    }
    descriptions_updated = 0
    social_updated = 0
    chapters_updated = 0
    for episode in existing:
        item = feed_by_key.get(
            episode_key(episode.get("link", ""), episode.get("audio", ""))
        )
        if not item:
            continue
        desc_html = clean_description_html(item["desc"])
        desc_text = summarize_html(desc_html)
        if episode.get("descHtml") != desc_html or episode.get("desc") != desc_text:
            episode["descHtml"] = desc_html
            episode["desc"] = desc_text
            descriptions_updated += 1
        social_uri = item.get("socialUri", "")
        if (episode.get("socialUri") or "") != social_uri:
            episode["socialUri"] = social_uri
            social_updated += 1
        chapters = item.get("chapters", [])
        if (episode.get("chapters") or []) != chapters:
            episode["chapters"] = chapters
            chapters_updated += 1

    slugs_updated = ensure_slugs(existing)

    known_keys = {
        episode_key(episode.get("link", ""), episode.get("audio", ""))
        for episode in existing
    }
    next_id = max((episode.get("id", 0) for episode in existing), default=0) + 1

    new_episodes: list[tuple[str, dict]] = []
    for item in feed_episodes:
        key = episode_key(item["link"], item["audio"])
        if key in known_keys:
            continue

        desc_html = clean_description_html(item["desc"])
        new_episodes.append(
            (
                key,
                {
                    "id": next_id,
                    "n": episode_number(item["title"]),
                    "type": classify(item["title"]),
                    "title": item["title"],
                    "date": item["_iso"],
                    "duration": item["duration"],
                    "link": item["link"],
                    "img": "img/episodes/ep-" + key + ".jpg",
                    "audio": item["audio"],
                    "socialUri": item.get("socialUri", ""),
                    "chapters": item.get("chapters", []),
                    "desc": summarize_html(desc_html),
                    "descHtml": desc_html,
                    "_image_url": item["image"],
                },
            )
        )
        known_keys.add(key)
        next_id += 1

    if not new_episodes:
        changed = (
            reclassified
            + descriptions_updated
            + social_updated
            + chapters_updated
            + slugs_updated
        )
        if changed and args.dry_run:
            if reclassified:
                print(
                    "Episodios que se reclasificarían con las reglas actuales: "
                    + str(reclassified)
                )
            if descriptions_updated:
                print(
                    "Descripciones que se actualizarían desde el feed: "
                    + str(descriptions_updated)
                )
            if social_updated:
                print(
                    "Enlaces sociales que se actualizarían desde el feed: "
                    + str(social_updated)
                )
            if chapters_updated:
                print(
                    "Capítulos que se actualizarían desde el feed: "
                    + str(chapters_updated)
                )
            if slugs_updated:
                print("Páginas de episodio a las que se asignaría slug: " + str(slugs_updated))
        elif changed:
            try:
                write_episodes(existing)
            except OSError as error:
                print("ERROR: no se pudo escribir js/episodes.js.")
                print("  " + str(error))
                return 1
            if reclassified:
                print(
                    "Episodios reclasificados con las reglas actuales: "
                    + str(reclassified)
                )
            if descriptions_updated:
                print(
                    "Descripciones actualizadas desde el feed: "
                    + str(descriptions_updated)
                )
            if social_updated:
                print(
                    "Enlaces sociales actualizados desde el feed: "
                    + str(social_updated)
                )
            if chapters_updated:
                print("Capítulos actualizados desde el feed: " + str(chapters_updated))
            if slugs_updated:
                print("Slugs asignados: " + str(slugs_updated))
        chapter_images = sync_chapter_images(existing, args.dry_run)
        if chapter_images:
            print("Imágenes de capítulos descargadas: " + str(chapter_images))
        generate_site(existing, args.dry_run)
        sync_sitemap(existing, args.dry_run)
        print("Todo al día: no hay episodios nuevos en el feed.")
        print("Episodios en la web: " + str(len(existing)))
        return 0

    print("Episodios nuevos detectados: " + str(len(new_episodes)))
    for key, episode in new_episodes:
        number = "PYM " + str(episode["n"]) if episode["n"] else "Sin número"
        print("  + " + number + " · " + episode["title"])
        print("    " + episode["date"] + " · " + episode["type"] + " · " + episode["duration"])

    if args.dry_run:
        print("")
        print("Simulación: no se ha descargado ni modificado ningún archivo.")
        return 0

    # Descargar portadas nuevas
    downloaded = 0
    for key, episode in new_episodes:
        destination = IMG_DIR / ("ep-" + key + ".jpg")
        try:
            method = download_cover(episode["_image_url"], destination)
            if method:
                downloaded += 1
                size_kb = round(destination.stat().st_size / 1024)
                detail = "" if method == "sin optimizar" else " (optimizada con " + method + ")"
                print(
                    "  Portada descargada: "
                    + destination.relative_to(ROOT).as_posix()
                    + detail
                    + " · "
                    + str(size_kb)
                    + " KB"
                )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            print("  AVISO: no se pudo descargar la portada de " + episode["title"])
            print("         " + str(error))
            episode["img"] = FALLBACK_IMG

    # Quitar campos auxiliares y ordenar por fecha (más reciente primero)
    for _, episode in new_episodes:
        episode.pop("_image_url", None)

    merged = [episode for _, episode in new_episodes] + existing
    merged.sort(key=lambda episode: episode.get("date", ""), reverse=True)
    ensure_slugs(merged)

    try:
        write_episodes(merged)
    except OSError as error:
        print("ERROR: no se pudo escribir js/episodes.js.")
        print("  " + str(error))
        return 1

    FEED_XML.write_bytes(xml_bytes)

    raw = []
    for item in feed_episodes:
        raw.append(
            {
                "title": item["title"],
                "link": item["link"],
                "date": item["date"],
                "duration": item["duration"],
                "image": item["image"],
                "audio": item["audio"],
                "chapters": item.get("chapters", []),
                "desc": item["desc"],
            }
        )
    RAW_JSON.write_text(
        json.dumps(raw, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    chapter_images = sync_chapter_images(merged, args.dry_run)
    if chapter_images:
        print("Imágenes de capítulos descargadas: " + str(chapter_images))

    sync_sitemap(merged, args.dry_run)
    generate_site(merged, args.dry_run)

    print("")
    print("Listo. La web ya tiene " + str(len(merged)) + " episodios.")
    print("Portadas nuevas descargadas: " + str(downloaded))
    if descriptions_updated:
        print("Descripciones actualizadas desde el feed: " + str(descriptions_updated))
    if social_updated:
        print("Enlaces sociales actualizados desde el feed: " + str(social_updated))
    if chapters_updated:
        print("Capítulos actualizados desde el feed: " + str(chapters_updated))
    print("Archivos actualizados: js/episodes.js, episodios/ y sitemap.xml")
    print("")
    print("El workflow de GitHub Actions publicará los cambios automáticamente.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main())
