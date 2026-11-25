#!/usr/bin/env python3
"""Genera previews.js con los previews de Apple para el juego de BSOs.

Apple redirige itunes.apple.com/search a musics:// cuando la petición viene de
un iPhone/iPad, por lo que el navegador no puede consultar la API en directo
desde iOS. Este script hace las búsquedas con un User-Agent de escritorio y
deja el resultado en un archivo JS estático que se sirve con la web.

Uso:
  python3 generar-previews.py                       # solo las que faltan
  python3 generar-previews.py --term "Jaws Main"    # regenera las que coincidan
  python3 generar-previews.py --forzar              # regenera todas
"""
import argparse
import concurrent.futures
import datetime
import json
import pathlib
import re
import socket
import time
import urllib.parse
import urllib.request

BASE = pathlib.Path(__file__).resolve().parent
PELICULAS = BASE / "peliculas.js"
SALIDA = BASE / "previews.js"

# User-Agent de escritorio: con un UA de iOS Apple responde 301 a musics://.
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
socket.setdefaulttimeout(15)
REINTENTOS = 2


def consultas():
    texto = PELICULAS.read_text(encoding="utf-8")
    bloque = re.search(r"window\.PELICULAS_BSO\s*=\s*(\[.*\])\s*;", texto, re.S)
    if not bloque:
        raise SystemExit("No se ha podido leer el array de películas.")
    return [p["consulta"] for p in json.loads(bloque.group(1))]


def previews_actuales():
    """Conserva lo ya generado. La clave de cada entrada es su consulta."""
    if not SALIDA.exists():
        return {}
    texto = SALIDA.read_text(encoding="utf-8")
    bloque = re.search(r"window\.APPLE_PREVIEWS\s*=\s*(.*);\s*$", texto, re.S)
    if not bloque:
        return {}
    try:
        datos = json.loads(bloque.group(1)).get("previews", {})
    except (ValueError, AttributeError):
        return {}
    resultado = {}
    for clave, entrada in datos.items():
        if not isinstance(entrada, dict):
            continue
        entrada = dict(entrada)
        entrada.pop("consulta", None)  # campo redundante de versiones anteriores
        resultado[clave] = entrada
    return resultado


def guardar(previews, total):
    # Solo se actualiza la fecha si cambian los datos. Si no, se conserva el
    # contenido exacto: así el workflow no crea un commit en cada push.
    actual = {}
    if SALIDA.exists():
        texto_actual = SALIDA.read_text(encoding="utf-8")
        bloque = re.search(r"window\.APPLE_PREVIEWS\s*=\s*(.*);\s*$", texto_actual, re.S)
        if bloque:
            try:
                actual = json.loads(bloque.group(1))
            except ValueError:
                actual = {}
    if (
        actual.get("generado")
        and actual.get("total") == total
        and actual.get("previews") == previews
    ):
        return False

    contenido = {
        "generado": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "total": total,
        "previews": previews,
    }
    SALIDA.write_text(
        "/* Generado por generar-previews.py. No editar a mano. */\n"
        "window.APPLE_PREVIEWS = "
        + json.dumps(contenido, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    return True


def buscar(term):
    params = urllib.parse.urlencode({
        "media": "music",
        "entity": "song",
        "limit": 5,
        "country": "ES",
        "term": term,
    })
    for intento in range(REINTENTOS):
        req = urllib.request.Request(
            "https://itunes.apple.com/search?" + params,
            headers={
                "User-Agent": UA,
                "Accept": "application/json",
                "X-Apple-Client": "web",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                datos = json.load(resp)
            item = next(
                (z for z in datos.get("results", []) if z.get("previewUrl")), None
            )
            if not item:
                return term, None
            return term, {
                "url": item["previewUrl"],
                "pista": item.get("trackName", ""),
                "artista": item.get("artistName", ""),
                "album": item.get("collectionName", ""),
            }
        except Exception:
            if intento == REINTENTOS - 1:
                return term, None
            time.sleep(2)
    return term, None


def main():
    ap = argparse.ArgumentParser(description="Genera previews.js para el juego de BSOs.")
    ap.add_argument("--term", action="append", default=[],
                    help="Regenera solo las consultas que contengan este texto (repetible).")
    ap.add_argument("--forzar", action="store_true",
                    help="Regenera todas las consultas, incluidas las ya guardadas.")
    args = ap.parse_args()

    terms = consultas()
    previews = previews_actuales()

    # Una consulta que ya no está en peliculas.js no debe quedar en el catálogo.
    for clave in list(previews):
        if clave not in terms:
            del previews[clave]

    if args.forzar:
        pendientes = terms
    elif args.term:
        pendientes = [t for t in terms
                      if any(b.lower() in t.lower() for b in args.term)]
    else:
        # Una consulta cambiada ya no está como clave: se regenera sola.
        pendientes = [t for t in terms if t not in previews]

    print(f"Catálogo: {len(previews)}/{len(terms)}. Buscando {len(pendientes)}…")
    if pendientes:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for i, (term, resultado) in enumerate(pool.map(buscar, pendientes), 1):
                if resultado:
                    previews[term] = resultado
                # Checkpoint: si Apple corta la conexión o se agota el tiempo,
                # lo ya encontrado no se pierde.
                if i % 20 == 0:
                    guardar(previews, len(terms))
                    print(f"  {i}/{len(pendientes)}")
    cambiado = guardar(previews, len(terms))
    estado = "Actualizado" if cambiado else "Sin cambios"
    print(f"{estado}: previews.js {len(previews)}/{len(terms)} previews")


if __name__ == "__main__":
    main()
