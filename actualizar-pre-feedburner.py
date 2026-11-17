#!/usr/bin/env python3
"""Añade el último episodio del feed de iVoox a util/pre-feedburner.xml.

El feed de iVoox publica items mínimos. Este script toma el más reciente,
comprueba que no esté ya en pre-feedburner.xml y lo reescribe con la
estructura enriquecida que consume Feedburner: descripción en HTML,
itunes:summary, capítulos Podlove, personas, socialInteract y el bloque
final de autopromoción. Las transcripciones no se añaden.

Uso:
    python actualizar-pre-feedburner.py
    python actualizar-pre-feedburner.py --dry-run
    python actualizar-pre-feedburner.py --feed RUTA_O_URL --file RUTA
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED_URL = "https://feeds.ivoox.com/feed_fg_f1661614_filtro_1.xml"
ROOT = Path(__file__).resolve().parent
PRE_FEED = ROOT / "util" / "pre-feedburner.xml"

PERSONAS = [
    ("https://twitter.com/alecrombie", "https://i.imgur.com/1OSzVcU.jpg", "Alecrombie"),
    ("https://twitter.com/JoyNoonaRaider", "https://i.imgur.com/C3SVUmL.jpg", "Joy"),
    ("https://twitter.com/MildrePeski3", "https://i.imgur.com/n1qtzqS.jpg", "Mildre"),
    ("https://twitter.com/sp_malcolm", "https://i.imgur.com/87MTZhR.jpg", "Malcolm"),
    ("https://twitter.com/PheebsMcM", "https://i.imgur.com/RNMlgWk.jpg", "Phoebe"),
    ("https://twitter.com/SeidonMF", "https://i.imgur.com/OYkX7oL.jpg", "Seidon McFly"),
]

SECCIONES_FIJAS = {
    "introduccion",
    "seccion del cm",
    "tomas extras",
}

URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
MINUTO_RE = re.compile(r"^(\d{1,3}:\d{2}(?::\d{2})?)\s*[-–—]\s*(.*)$")
ID_RE = re.compile(r"(?:rf_|mf_)(\d+)")
ENTIDAD_RE = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);")


# ---------------------------------------------------------------------------
# Utilidades XML
# ---------------------------------------------------------------------------

def local_name(tag: str) -> str:
    """Nombre de etiqueta sin espacio de nombres, en minúsculas."""
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if local_name(child.tag) == name.lower():
            return (child.text or "").strip()
    return ""


def child_attr(element: ET.Element, name: str, attribute: str) -> str:
    for child in element:
        if local_name(child.tag) == name.lower():
            return (child.get(attribute) or "").strip()
    return ""


def cdata(text: str) -> str:
    """Envuelve texto en CDATA sin romperlo si contiene ']]>'."""
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def attr(value: str) -> str:
    """Escapa un valor para usarlo entre comillas dobles en un atributo."""
    return html.escape(value, quote=True)


def texto(value: str) -> str:
    """Escapa texto plano, conservando las entidades HTML ya presentes."""
    partes: list[str] = []
    posicion = 0
    for match in ENTIDAD_RE.finditer(value):
        partes.append(html.escape(value[posicion:match.start()], quote=False))
        partes.append(match.group(0))
        posicion = match.end()
    partes.append(html.escape(value[posicion:], quote=False))
    return "".join(partes)


def sin_acentos(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


# ---------------------------------------------------------------------------
# Feed de iVoox
# ---------------------------------------------------------------------------

def leer_feed(origen: str) -> bytes:
    if origen.startswith(("http://", "https://")):
        request = urllib.request.Request(
            origen,
            headers={"User-Agent": "Mozilla/5.0 (compatible; pre-feedburner/1.0)"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    return Path(origen).read_bytes()


def fecha_publicacion(item: ET.Element) -> datetime:
    raw = child_text(item, "pubdate")
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        fecha = parsedate_to_datetime(raw)
        return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def ultimo_item(xml_bytes: bytes) -> ET.Element:
    root = ET.fromstring(xml_bytes)
    items = [element for element in root.iter() if local_name(element.tag) == "item"]
    if not items:
        raise ValueError("El feed de iVoox no contiene ningún <item>.")
    return max(items, key=fecha_publicacion)


def id_episodio(item: ET.Element) -> str:
    for valor in (child_text(item, "link"), child_attr(item, "enclosure", "url"), child_text(item, "guid")):
        match = ID_RE.search(valor)
        if match:
            return match.group(1)
    guid = child_text(item, "guid")
    match = re.search(r"(\d+)\s*$", guid)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# Transformación del item
# ---------------------------------------------------------------------------

def con_enlaces(linea: str) -> str:
    """Convierte URLs en <a> y escapa el resto del texto plano."""
    partes: list[str] = []
    posicion = 0
    for match in URL_RE.finditer(linea):
        partes.append(texto(linea[posicion:match.start()]))
        url = match.group(0).rstrip(".,;:!?)")
        partes.append(
            '<a href="' + attr(url) + '">' + texto(url) + "</a>"
        )
        posicion = match.start() + len(url)
    partes.append(texto(linea[posicion:]))
    return "".join(partes)


def normalizar_linea(linea: str) -> str:
    """Corrige el espaciado del guion en las líneas con minutaje."""
    match = MINUTO_RE.match(linea)
    if match:
        return match.group(1) + " - " + match.group(2)
    return linea


def lineas_descripcion(item: ET.Element) -> list[str]:
    descripcion = child_text(item, "description") or child_text(item, "encoded")
    descripcion = descripcion.replace("\r\n", "\n").replace("\r", "\n").strip()
    return descripcion.split("\n") if descripcion else []


def pie_final(episode_id: str) -> str:
    corto = "https://go.ivoox.com/rf/" + episode_id
    return "\n".join(
        [
            f'Enlace al programa en iVoox: <a href="{corto}">{corto}</a>',
            "<br>",
            'S&iacute;guenos en nuestras redes sociales: '
            '<a href="https://linktr.ee/peskitoymedio">https://linktr.ee/peskitoymedio</a>',
            "<br><br>",
            '<a href="https://www.ivoox.com/ajx-suscribirse_jh_661614_1.html">Suscríbete en iVoox</a> '
            f'y dale a <a href="https://www.ivoox.com/ajx-mis-audios-favoritos_ve_{episode_id}_like_1.html">Me gusta</a>',
        ]
    )


def descripcion_html(item: ET.Element, episode_id: str) -> str:
    imagen = child_attr(item, "image", "href").replace("static-2.ivoox.com", "static-1.ivoox.com")
    lineas: list[str] = []
    if imagen:
        lineas.append(f'<img src="{attr(imagen)}" style="width:95%;"/>')
        lineas.append("<br>")

    for linea in lineas_descripcion(item):
        normalizada = normalizar_linea(linea)
        if normalizada.lstrip().startswith("Te recordamos") and lineas:
            lineas.append("<br>")
        lineas.append(con_enlaces(normalizada) + "<br>")

    lineas.extend(["<br>", "<br>"])
    return "\n".join(lineas) + "\n" + pie_final(episode_id)


def capitulos(item: ET.Element) -> list[tuple[str, str]]:
    resultado: list[tuple[str, str]] = []
    for linea in lineas_descripcion(item):
        match = MINUTO_RE.match(linea)
        if not match:
            continue
        titulo = match.group(2).strip()
        if sin_acentos(titulo).rstrip(". ") in SECCIONES_FIJAS:
            titulo = titulo.rstrip(". ")
        if titulo:
            resultado.append((match.group(1), titulo))
    return resultado


def hashtag(item: ET.Element) -> str:
    numero = child_text(item, "episode")
    if not numero:
        match = re.search(r"\bPYM\s*(\d+)", child_text(item, "title"), re.IGNORECASE)
        numero = match.group(1) if match else ""
    return "PYM" + numero if numero else ""


def construir_item(item: ET.Element) -> str:
    titulo = child_text(item, "title")
    episode_id = id_episodio(item)
    if not episode_id:
        raise ValueError("No se ha podido determinar el ID de iVoox del episodio.")

    descripcion = descripcion_html(item, episode_id)
    salida = [
        "<item>",
        f"<title>{cdata(titulo)}</title>",
        f"<link>{texto(child_text(item, 'link'))}</link>",
    ]

    enclosure = item_enclosure(item)
    if enclosure:
        salida.append(enclosure)

    salida.extend(
        [
            f"<description>{cdata(descripcion)}</description>",
            f"<pubDate>{texto(child_text(item, 'pubdate'))}</pubDate>",
        ]
    )

    duracion = child_text(item, "duration")
    if duracion:
        salida.append(f"<itunes:duration>{texto(duracion)}</itunes:duration>")

    guid = child_text(item, "guid")
    if guid:
        salida.append(f"<guid>{texto(guid)}</guid>")

    for etiqueta in ("season", "episode", "episodeType"):
        valor = child_text(item, etiqueta)
        if valor:
            salida.append(f"<itunes:{etiqueta}>{texto(valor)}</itunes:{etiqueta}>")

    imagen = child_attr(item, "image", "href")
    if imagen:
        salida.append(f'<itunes:image href="{attr(imagen)}"/>')

    salida.append(f"<itunes:summary>{cdata(descripcion)}</itunes:summary>")

    capitulos_item = capitulos(item)
    if capitulos_item:
        salida.append('\t<psc:chapters version="1.2" xmlns:psc="http://podlove.org/simple-chapters">')
        for start, titulo_capitulo in capitulos_item:
            salida.append(f'\t\t<psc:chapter start="{attr(start)}" title="{attr(titulo_capitulo)}"/>')
        salida.append("\t</psc:chapters>")

    for href, img, nombre in PERSONAS:
        salida.append(f'\t<podcast:person href="{href}" img="{img}">{nombre}</podcast:person>')

    etiqueta = hashtag(item)
    if etiqueta:
        salida.append(
            '\t<podcast:socialInteract '
            f'uri="https://x.com/search?q=%23{etiqueta}" '
            'protocol="twitter" accountId="@peskito3" accountUrl="https://x.com/peskito3"/>'
        )

    salida.append("</item>")
    return "\n".join(salida)


def item_enclosure(item: ET.Element) -> str:
    for child in item:
        if local_name(child.tag) != "enclosure":
            continue
        atributos = " ".join(
            f'{attr(clave)}="{attr(valor)}"' for clave, valor in child.attrib.items()
        )
        return f"<enclosure {atributos}/>"
    return ""


# ---------------------------------------------------------------------------
# pre-feedburner.xml
# ---------------------------------------------------------------------------

def ya_existe(contenido: str, episode_id: str, guid: str) -> bool:
    for bloque in re.findall(r"<item\b.*?</item>", contenido, re.DOTALL):
        if guid and f"<guid>{guid}</guid>" in bloque:
            return True
        if episode_id and re.search(r"(?:rf_|mf_)" + re.escape(episode_id) + r"\b", bloque):
            return True
    return False


def insertar_item(contenido: str, item_xml: str) -> str:
    posicion = contenido.find("<item")
    if posicion == -1:
        posicion = contenido.find("</channel>")
        if posicion == -1:
            raise ValueError("No se ha encontrado <channel> en pre-feedburner.xml.")
    prefijo = contenido[:posicion]
    if prefijo and not prefijo.endswith("\n"):
        prefijo += "\n"
    return prefijo + item_xml + "\n" + contenido[posicion:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", default=FEED_URL, help="URL o fichero del feed de iVoox")
    parser.add_argument("--file", default=str(PRE_FEED), help="Ruta de pre-feedburner.xml")
    parser.add_argument("--dry-run", action="store_true", help="Muestra el item sin escribir el fichero")
    argumentos = parser.parse_args()

    try:
        ultimo = ultimo_item(leer_feed(argumentos.feed))
        episode_id = id_episodio(ultimo)
        guid = child_text(ultimo, "guid")
        item_xml = construir_item(ultimo)
    except (OSError, ValueError, ET.ParseError) as error:
        print("Error al procesar el feed de iVoox: " + str(error), file=sys.stderr)
        return 1

    ruta = Path(argumentos.file)
    try:
        original = ruta.read_bytes().decode("utf-8")
    except OSError as error:
        print("Error al leer " + str(ruta) + ": " + str(error), file=sys.stderr)
        return 1

    if ya_existe(original, episode_id, guid):
        print("El último episodio de iVoox (ID " + episode_id + ") ya está en " + str(ruta) + ". No hay cambios.")
        return 0

    if argumentos.dry_run:
        print(item_xml)
        return 0

    salto = "\r\n" if "\r\n" in original else "\n"
    normalizado = original.replace("\r\n", "\n")
    actualizado = insertar_item(normalizado, item_xml)
    if salto == "\r\n":
        actualizado = actualizado.replace("\n", "\r\n")
    ruta.write_bytes(actualizado.encode("utf-8"))
    print("Añadido el episodio " + child_text(ultimo, "title") + " (ID " + episode_id + ") a " + str(ruta) + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
