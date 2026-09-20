"""Restricción de contenido: prohibidos los CTA que dependen de enviar un enlace.

Se aplica en el servidor al subir un borrador y otra vez al aprobarlo, para que
no dependa de que el generador se acuerde de la regla.
"""
import re

_PATTERNS = [
    (re.compile(r"(?i:comenta)\b.{0,60}?\b(?i:link|enlace)\b", re.S), "«Comenta … link»"),
    (re.compile(r"(?i:comenta)\s+[\"“«']?[A-ZÁÉÍÓÚÑ]{3,}"), "«Comenta PALABRA»"),
    (re.compile(r"(?i)\b(link|enlace)s?\s+(en|de)\s+(la\s+|mi\s+|nuestra\s+)?(bio|biograf[ií]a|descripci[oó]n|perfil)"),
     "«link en la bio/descripción»"),
    (re.compile(r"(?i)\b(te\s+)?(lo\s+)?(dejo|paso|mando|env[ií]o|comparto)\s+(el|un)\s+(link|enlace)"),
     "«te dejo/paso el link»"),
    (re.compile(r"(?i)\bpor\s+(dm|md|mensaje\s+(privado|directo))\b"), "«por DM»"),
]


def check(*texts: str) -> list[str]:
    """Devuelve una lista de incumplimientos (vacía si el texto es válido)."""
    found = []
    for text in texts:
        for pattern, label in _PATTERNS:
            m = pattern.search(text or "")
            if m:
                snippet = " ".join(m.group(0).split())[:60]
                found.append(f"{label}: «{snippet}»")
    return list(dict.fromkeys(found))
