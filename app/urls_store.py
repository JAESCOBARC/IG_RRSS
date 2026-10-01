"""URLs de trabajoenexcel.com que se promocionan, guardadas en la base de datos (se editan desde el panel).

La primera vez que se leen, se copian de url.txt; a partir de ahí manda la base de datos y url.txt
ya no se lee. Claude las pide por la API (/api/urls) para sortear los temas de la tanda semanal.
"""
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import db

URL_FILE = Path(__file__).with_name("url.txt")
KEY_SEEDED = "urls_seeded"
ALLOWED_HOSTS = ("trabajoenexcel.com", "www.trabajoenexcel.com")
MAX_LEN = 300


class UrlError(Exception):
    """URL no válida o repetida."""


def normalize(text: str) -> str:
    url = (text or "").strip()
    if not url or len(url) > MAX_LEN or any(c.isspace() for c in url):
        raise UrlError("Escribe una URL (sin espacios, máx. 300 caracteres).")
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "") not in ALLOWED_HOSTS:
        raise UrlError("La URL debe ser https y de trabajoenexcel.com (por ejemplo https://www.trabajoenexcel.com/test-nivel-excel.html).")
    return url


def _seed(conn) -> None:
    lines = URL_FILE.read_text(encoding="utf-8").splitlines() if URL_FILE.exists() else []
    for line in dict.fromkeys(l.strip() for l in lines):
        if line and not line.startswith("#"):
            db.execute(conn, ("INSERT INTO source_urls (id, url, created_at, created_by) VALUES (%s, %s, %s, 'url.txt') "
                              "ON CONFLICT DO NOTHING"), (uuid.uuid4().hex, line, db.now_precise()))
    db.kv_set(conn, KEY_SEEDED, db.now())


def list_urls(conn) -> list[dict]:
    if db.kv_get(conn, KEY_SEEDED) is None:
        _seed(conn)
    return db.query(conn, "SELECT id, url, created_at, created_by FROM source_urls ORDER BY created_at ASC, url ASC")


def add(conn, text: str, by: str) -> None:
    url = normalize(text)
    list_urls(conn)  # asegura la carga inicial
    if db.one(conn, "SELECT 1 AS x FROM source_urls WHERE url = %s", (url,)):
        raise UrlError("Esa URL ya está en la lista.")
    db.execute(conn, "INSERT INTO source_urls (id, url, created_at, created_by) VALUES (%s, %s, %s, %s)",
               (uuid.uuid4().hex, url, db.now_precise(), by))


def update(conn, url_id: str, text: str) -> None:
    url = normalize(text)
    list_urls(conn)
    clash = db.one(conn, "SELECT id FROM source_urls WHERE url = %s", (url,))
    if clash and clash["id"] != url_id:
        raise UrlError("Esa URL ya está en la lista.")
    if not db.query(conn, "UPDATE source_urls SET url = %s WHERE id = %s RETURNING id", (url, url_id)):
        raise UrlError("Esa URL ya no existe.")


def delete(conn, url_id: str) -> bool:
    list_urls(conn)
    return bool(db.query(conn, "DELETE FROM source_urls WHERE id = %s RETURNING id", (url_id,)))
