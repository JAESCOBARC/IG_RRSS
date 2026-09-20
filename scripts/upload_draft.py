#!/usr/bin/env python3
"""Sube un carrusel como BORRADOR a la app de aprobación.

Uso:
  python scripts/upload_draft.py CARPETA [--spec spec.json] [--keep]
  python scripts/upload_draft.py --recent      # lista los posts recientes (para no repetir temas)

CARPETA contiene slide-01.jpg, slide-02.jpg... y meta.yaml con:
  title, caption, hashtags (lista sin #) y, opcional, source_url.
--spec es el JSON con el que se generaron las slides; su texto se sube para que
se vea en el panel y se compruebe la restricción de CTA.

Configuración (variables de entorno o fichero .env en la raíz, ignorado por git):
  IG_APP_URL      https://tu-app.onrender.com
  IG_APP_API_KEY  la API_KEY de la app. Opcional en el entorno de nube de Claude, donde
                  se guarda como «credencial de API» y el proxy la añade a la petición.

Tras subirlo, las imágenes locales se borran (usa --keep para conservarlas).
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def slides_text(spec_path: Path) -> list[str]:
    texts = []
    for slide in json.loads(spec_path.read_text(encoding="utf-8")):
        parts = [run[0] for run in slide["runs"]]
        if slide.get("cta_text"):
            parts.append(slide["cta_text"])
        texts.append(" ".join(parts))
    return texts


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Sube un borrador a la app de aprobación")
    parser.add_argument("folder", type=Path, nargs="?")
    parser.add_argument("--recent", action="store_true", help="listar los posts recientes y salir")
    parser.add_argument("--spec", type=Path, help="JSON de las slides (para mostrar su texto)")
    parser.add_argument("--keep", action="store_true", help="no borrar las imágenes locales tras subir")
    args = parser.parse_args()

    load_env()
    base, key = os.environ.get("IG_APP_URL", "").rstrip("/"), os.environ.get("IG_APP_API_KEY", "")
    if not base:
        print("Falta IG_APP_URL (variable de entorno o .env).", file=sys.stderr)
        return 2
    # Sin clave local no se envía cabecera: en la nube la añade el proxy del entorno.
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    if args.recent:
        resp = requests.get(f"{base}/api/posts", headers=headers, params={"limit": 40}, timeout=120)
        if resp.status_code == 401:
            print("[FALLO] 401: la app no acepta la petición. Falta IG_APP_API_KEY (o la credencial "
                  "de API del entorno de nube no está bien configurada).", file=sys.stderr)
            return 1
        if resp.status_code != 200:
            print(f"[FALLO] {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            return 1
        for post in resp.json():
            print(f"{post['created_at'][:10]}  {post['status']:<10}  {post['title']}  |  {post.get('source_url') or ''}")
        return 0
    if not args.folder:
        parser.error("indica CARPETA o usa --recent")

    images = sorted(args.folder.glob("slide-*.jpg"))
    meta_path = args.folder / "meta.yaml"
    if not images or not meta_path.exists():
        print(f"{args.folder}: hacen falta slide-XX.jpg y meta.yaml.", file=sys.stderr)
        return 2
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}

    data = {
        "title": meta.get("title", ""),
        "caption": meta.get("caption", ""),
        "hashtags": json.dumps(meta.get("hashtags") or [], ensure_ascii=False),
        "source_url": meta.get("source_url", ""),
        "slides_text": json.dumps(slides_text(args.spec) if args.spec else [], ensure_ascii=False),
    }
    files = [("slides", (p.name, p.read_bytes(), "image/jpeg")) for p in images]
    resp = requests.post(f"{base}/api/drafts", headers=headers, data=data, files=files, timeout=180)
    try:
        body = resp.json()
    except ValueError:
        body = {"error": resp.text[:200]}
    if resp.status_code != 201:
        print(f"[FALLO] {resp.status_code}: {body.get('error')}", file=sys.stderr)
        return 1

    print(f"[SUBIDO] {len(images)} slide(s). Revísalo y apruébalo en: {body['url']}")
    if not args.keep:
        for path in (*images, meta_path):
            path.unlink(missing_ok=True)
        try:
            args.folder.rmdir()  # solo si ha quedado vacía
        except OSError:
            pass
        print("Imágenes locales borradas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
