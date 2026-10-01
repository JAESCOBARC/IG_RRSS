#!/usr/bin/env python3
"""Elige N URLs al azar (distintas entre sí) de la lista de URLs a promocionar.

La lista vive en la app (panel → URLs) y se lee por la API. Si no se puede (sin IG_APP_URL o sin
conexión), usa app/url.txt, que es la lista inicial.

Uso:  python scripts/pick_urls.py [N]      (por defecto N=3)

Configuración (variables de entorno o .env en la raíz): IG_APP_URL e IG_APP_API_KEY, igual que
upload_draft.py. En la nube la clave la añade el proxy del entorno.
"""
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FALLBACK = ROOT / "app" / "url.txt"


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def from_app() -> list[str] | None:
    base, key = os.environ.get("IG_APP_URL", "").rstrip("/"), os.environ.get("IG_APP_API_KEY", "")
    if not base:
        return None
    try:
        import requests
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        resp = requests.get(f"{base}/api/urls", headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"[AVISO] La app respondió {resp.status_code} al pedir las URLs; uso app/url.txt.", file=sys.stderr)
            return None
        return [u for u in resp.json() if isinstance(u, str) and u.strip()]
    except Exception as exc:  # noqa: BLE001 - sin conexión: se usa la lista inicial
        print(f"[AVISO] No pude leer las URLs de la app ({type(exc).__name__}); uso app/url.txt.", file=sys.stderr)
        return None


def from_file() -> list[str]:
    return [line.strip() for line in FALLBACK.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")]


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    load_env()
    urls = from_app()
    if urls is None:
        urls = from_file()
    urls = list(dict.fromkeys(urls))
    if not urls:
        print("No hay ninguna URL a promocionar (revisa el panel → URLs).", file=sys.stderr)
        return 1
    for url in random.sample(urls, min(n, len(urls))):
        print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
