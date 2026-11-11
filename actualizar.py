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
  - Añade los episodios y regenera js/episodes.js.
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
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FEED_URL = "https://feeds.feedburner.com/PeskitoYMedio"
EPISODES_JS = ROOT / "js" / "episodes.js"
IMG_DIR = ROOT / "img" / "episodes"
RAW_JSON = ROOT / "episodes-raw.json"
FEED_XML = ROOT / "feed.xml"
FALLBACK_IMG = "img/logo-800.jpg"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

PROMO_HTML_PREFIX = re.compile(
    r"^\s*(?:<a\b[^>]*>\s*)?¡Vótame en los Premios iVoox.*?!\s*(?:</a>)?\s*(?:<br\s*/?>\s*)*",
    re.IGNORECASE | re.DOTALL,
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
        for child in item:
            if local_name(child.tag) == "enclosure":
                audio = (child.get("url") or "").strip()
                break

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
        self.parts.append(escape(data, quote=False))

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
    """Descripción completa en HTML, sin imágenes ni la promo de los premios."""
    html = sanitize_description_html(raw)
    html = PROMO_HTML_PREFIX.sub("", html)
    html = re.sub(r"^(?:\s|<br\s*/?>)+", "", html, flags=re.IGNORECASE)
    html = re.sub(r"(?:\s|<br\s*/?>)+$", "", html, flags=re.IGNORECASE)
    html = re.sub(r"(?:<br\s*/?>\s*){3,}", "<br><br>", html, flags=re.IGNORECASE)
    return html.strip()


def summarize_html(html: str, limit: int = 190) -> str:
    """Convierte el HTML en texto plano y lo recorta con puntos suspensivos."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

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
    if "especial" in title.lower():
        return "especial"
    return "programa"


def episode_number(title: str):
    match = re.match(r"^PYM\s+(\d+)", title, re.IGNORECASE)
    return int(match.group(1)) if match else None


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
                "desc": episode["desc"],
                "descHtml": episode.get("descHtml", ""),
            }
        )

    body = json.dumps(clean, ensure_ascii=False, indent=4)
    EPISODES_JS.write_text(
        "/* Datos reales generados desde el feed oficial de Peskito y Medio (iVoox) */\n"
        "const EPISODES = " + body + ";\n",
        encoding="utf-8",
    )


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
                    "desc": summarize_html(desc_html),
                    "descHtml": desc_html,
                    "_image_url": item["image"],
                },
            )
        )
        known_keys.add(key)
        next_id += 1

    if not new_episodes:
        changed = reclassified + descriptions_updated
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
                "desc": item["desc"],
            }
        )
    RAW_JSON.write_text(
        json.dumps(raw, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    print("")
    print("Listo. La web ya tiene " + str(len(merged)) + " episodios.")
    print("Portadas nuevas descargadas: " + str(downloaded))
    if descriptions_updated:
        print("Descripciones actualizadas desde el feed: " + str(descriptions_updated))
    print("Archivo actualizado: js/episodes.js")
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
