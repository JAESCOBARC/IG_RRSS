#!/usr/bin/env python3
"""Publica en Instagram los posts aprobados de queue/.

Un post es una carpeta de queue/ con:
  - meta.yaml  (status, scheduled_date, caption, hashtags)
  - slide-01.jpg, slide-02.jpg, ...  (1 imagen = post simple, 2-10 = carrusel)

Se publican los posts con `status: approved` y `scheduled_date <= hoy`.
Tras cada intento se actualiza meta.yaml (published / failed). Un post fallido
NUNCA se reintenta solo, para no duplicar publicaciones.

Variables de entorno:
  IG_ACCESS_TOKEN     token de larga duración (obligatorio salvo --dry-run)
  IG_USER_ID          id de la cuenta de Instagram (obligatorio salvo --dry-run)
  GITHUB_REPOSITORY   "usuario/repo" (lo define GitHub Actions)
  GITHUB_REF_NAME     rama (lo define GitHub Actions; por defecto "main")
  IG_API_VERSION      versión de la Graph API (por defecto v23.0)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue"
API_VERSION = os.environ.get("IG_API_VERSION", "v23.0")
API = f"https://graph.instagram.com/{API_VERSION}"
IMAGE_EXTS = {".jpg", ".jpeg"}  # la API de contenido de Instagram solo admite JPEG
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
POLL_SECONDS = 3
POLL_ATTEMPTS = 40
RESULT_KEYS = ("published_at", "media_id", "permalink", "error")


class PostError(Exception):
    """Error de validación o de la API para un post concreto."""


# ---------------------------------------------------------------- lectura ----

def load_meta(folder: Path) -> dict:
    meta_path = folder / "meta.yaml"
    if not meta_path.exists():
        raise PostError("falta meta.yaml")
    data = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise PostError("meta.yaml no tiene formato clave: valor")
    return data


def parse_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise PostError(f"scheduled_date inválida: {value!r} (usa AAAA-MM-DD)")


def is_due(meta: dict, today: dt.date) -> bool:
    if str(meta.get("status", "")).strip().lower() != "approved":
        return False
    return parse_date(meta.get("scheduled_date")) <= today


def build_caption(meta: dict) -> str:
    caption = str(meta.get("caption") or "").strip()
    hashtags = meta.get("hashtags") or []
    if isinstance(hashtags, str):
        hashtags = hashtags.split()
    tags = [("#" + str(h).lstrip("#")) for h in hashtags if str(h).strip()]
    if len(tags) > MAX_HASHTAGS:
        raise PostError(f"demasiados hashtags ({len(tags)}); Instagram admite {MAX_HASHTAGS}")
    full = caption + ("\n\n" + " ".join(tags) if tags else "")
    if not full.strip():
        raise PostError("el caption está vacío")
    if len(full) > MAX_CAPTION:
        raise PostError(f"caption demasiado largo ({len(full)} > {MAX_CAPTION} caracteres)")
    return full


def find_images(folder: Path) -> list[Path]:
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.stem.lower().startswith("slide"))
    bad = [p.name for p in files if p.suffix.lower() not in IMAGE_EXTS]
    if bad:
        raise PostError(
            f"formato no soportado: {', '.join(bad)}. Instagram solo acepta JPEG; "
            "ejecuta `python scripts/prepare.py` para convertir los PNG a JPG"
        )
    if not files:
        raise PostError("no hay imágenes slide-XX.jpg en la carpeta")
    if len(files) > 10:
        raise PostError(f"{len(files)} imágenes; un carrusel admite como máximo 10")
    return files


def public_url(image: Path) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise PostError("GITHUB_REPOSITORY no definida; no puedo construir la URL pública de la imagen")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    rel = image.relative_to(ROOT).as_posix()
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{requests.utils.quote(rel)}"


# -------------------------------------------------------------------- API ----

def api_call(method: str, path: str, token: str, **params) -> dict:
    params["access_token"] = token
    resp = requests.request(method, f"{API}/{path}", params=params, timeout=60)
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:300]}
    if resp.status_code >= 400 or "error" in body:
        err = body.get("error", body)
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise PostError(f"API {resp.status_code} en {path}: {msg}")
    return body


def wait_until_ready(container_id: str, token: str) -> None:
    for _ in range(POLL_ATTEMPTS):
        status = api_call("GET", container_id, token, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise PostError(f"el contenedor {container_id} quedó en estado {status}")
        time.sleep(POLL_SECONDS)
    raise PostError(f"el contenedor {container_id} no terminó de procesarse a tiempo")


def publish_post(images: list[Path], caption: str, user_id: str, token: str) -> dict:
    if len(images) == 1:
        container = api_call("POST", f"{user_id}/media", token,
                             image_url=public_url(images[0]), caption=caption)["id"]
    else:
        children = []
        for img in images:
            child = api_call("POST", f"{user_id}/media", token,
                             image_url=public_url(img), is_carousel_item="true")["id"]
            children.append(child)
        for child in children:
            wait_until_ready(child, token)
        container = api_call("POST", f"{user_id}/media", token, media_type="CAROUSEL",
                             children=",".join(children), caption=caption)["id"]
    wait_until_ready(container, token)
    media_id = api_call("POST", f"{user_id}/media_publish", token, creation_id=container)["id"]
    permalink = ""
    try:
        permalink = api_call("GET", media_id, token, fields="permalink").get("permalink", "")
    except PostError:
        pass  # el post ya está publicado; el permalink es solo informativo
    return {"media_id": media_id, "permalink": permalink}


# ---------------------------------------------------------------- escritura --

def write_result(folder: Path, status: str, **fields) -> None:
    """Actualiza status y campos de resultado en meta.yaml sin tocar el resto (comentarios incl.)."""
    path = folder / "meta.yaml"
    keys = "|".join(("status",) + RESULT_KEYS)
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if not re.match(rf"^({keys})\s*:", ln)]
    lines.append(f"status: {status}")
    for key, value in fields.items():
        if value:
            lines.append(f"{key}: {json.dumps(str(value), ensure_ascii=False)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------- main ----

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="valida los posts pendientes sin llamar a la API ni modificar nada")
    parser.add_argument("--today", help="fecha de referencia AAAA-MM-DD (por defecto, hoy en UTC)")
    args = parser.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    user_id = os.environ.get("IG_USER_ID", "")
    if not args.dry_run and not (token and user_id):
        print("Faltan IG_ACCESS_TOKEN / IG_USER_ID en el entorno.", file=sys.stderr)
        return 2

    folders = sorted(p for p in QUEUE.iterdir() if p.is_dir()) if QUEUE.exists() else []
    published = failed = 0
    for folder in folders:
        try:
            meta = load_meta(folder)
            if not is_due(meta, today):
                continue
            caption = build_caption(meta)
            images = find_images(folder)
        except PostError as exc:
            print(f"[FALLO] {folder.name}: {exc}")
            if not args.dry_run:
                write_result(folder, "failed", error=exc)
            failed += 1
            continue

        if args.dry_run:
            print(f"[OK-DRY] {folder.name}: {len(images)} imagen(es), caption {len(caption)} caracteres")
            continue

        print(f"[PUBLICANDO] {folder.name} ({len(images)} imagen(es))")
        try:
            result = publish_post(images, caption, user_id, token)
        except (PostError, requests.RequestException) as exc:
            print(f"[FALLO] {folder.name}: {exc}")
            write_result(folder, "failed", error=exc)
            failed += 1
            continue
        write_result(folder, "published",
                     published_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                     **result)
        print(f"[PUBLICADO] {folder.name}: {result['permalink'] or result['media_id']}")
        published += 1

    print(f"Resumen: {published} publicado(s), {failed} fallido(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
