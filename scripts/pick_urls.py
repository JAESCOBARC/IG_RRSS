#!/usr/bin/env python3
"""Elige N URLs al azar (distintas entre sí) de url.txt.

Uso:  python scripts/pick_urls.py [N]      (por defecto N=3)
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    urls = list(dict.fromkeys(
        line.strip() for line in (ROOT / "url.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")))
    if not urls:
        print("url.txt no tiene ninguna URL.", file=sys.stderr)
        return 1
    for url in random.sample(urls, min(n, len(urls))):
        print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
