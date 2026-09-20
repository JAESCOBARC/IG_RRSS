#!/usr/bin/env python3
"""Convierte a JPG las imágenes slide-XX.png de queue/ (Instagram solo acepta JPEG).

Uso (en local, antes de hacer commit):
  python scripts/prepare.py                 # todas las carpetas de queue/
  python scripts/prepare.py queue/mi-post   # una carpeta concreta

Requiere Pillow: pip install pillow
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def convert(folder: Path) -> int:
    count = 0
    for png in sorted(folder.glob("slide*.png")):
        jpg = png.with_suffix(".jpg")
        with Image.open(png) as img:
            img.convert("RGB").save(jpg, "JPEG", quality=95)
        png.unlink()
        print(f"{png} -> {jpg.name}")
        count += 1
    return count


def main() -> None:
    targets = [Path(a) for a in sys.argv[1:]] or sorted(p for p in (ROOT / "queue").iterdir() if p.is_dir())
    total = sum(convert(t) for t in targets)
    print(f"{total} imagen(es) convertida(s).")


if __name__ == "__main__":
    main()
