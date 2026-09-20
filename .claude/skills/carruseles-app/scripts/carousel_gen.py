"""
Generador de imágenes de Instagram para trabajoenexcel.com.
Dibuja con Pillow (wrap de texto medido con la fuente real, sin overflow) y guarda JPG,
el único formato que admite la API de Instagram. No necesita rsvg ni fuentes del
sistema: usa las de assets/fonts.

Uso:
    python carousel_gen.py slides.json /tmp/post [--format carrusel|publicacion|historia]

Formatos (--format, por defecto carrusel):
    carrusel     2-10 slides de 1080x1350 (4:5), con flecha de deslizar y numeración
    publicacion  1 imagen de 1080x1350 (4:5), sin flecha ni numeración
    historia     1 imagen de 1080x1920 (9:16), con márgenes de seguridad arriba y abajo
                 (~250 px que Instagram tapa con su interfaz) y sin flecha

Genera slide-01.jpg, slide-02.jpg... en la carpeta de salida.

slides.json: lista de objetos con esta forma:
{
  "runs": [["TEXTO BOLD EN MAYUSCULAS", "bold"], ["frase en italica verde", "italic"]],
  "slide_no": "01 / 06",      // opcional, solo carrusel; null en el slide de CTA
  "cta_text": "PLANTILLA DE SPRINT.",  // opcional, solo en el slide final / imagen única
  "swipe_hint": true,          // opcional, solo carrusel; false si hay cta_text
  "start_y": 520               // opcional, ajustar si el bloque de texto es largo
}

Requiere: pip install Pillow
"""
import argparse
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W = 1080
S = 2                # supersampling: se dibuja a 2x y se reduce (bordes suaves)
BG = "#F4EFE1"       # cream / hueso (trabajoenexcel.com)
DARK = "#182A20"     # texto principal
ACCENT = "#2F6B47"   # verde bosque de acento — ver references/style-guide.md
GREY = "#8A9088"

MARGIN = 90
MAX_W = W - 2 * MARGIN


def _layout(h, header_y, start_y, line_y, url_y, cta_y, arrows, numbering, limit):
    return {"H": h, "header_y": header_y, "start_y": start_y, "line_y": line_y, "url_y": url_y,
            "cta_y": cta_y, "arrows": arrows, "numbering": numbering, "limit": limit}


LAYOUTS = {
    "carrusel": _layout(1350, 90, 520, 1350 - 90, 1350 - 60, 1350 - 160, True, True, 1350 - 200),
    "publicacion": _layout(1350, 90, 520, 1350 - 90, 1350 - 60, 1350 - 160, False, False, 1350 - 200),
    # historia: Instagram tapa ~250 px arriba y abajo; nada importante fuera de y=250..1670
    "historia": _layout(1920, 300, 760, 1920 - 330, 1920 - 300, 1920 - 430, False, False, 1920 - 560),
}

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
BOLD_PATH = str(FONTS / "DejaVuSansCondensed-Bold.ttf")
REGULAR_PATH = str(FONTS / "DejaVuSansCondensed.ttf")
ITALIC_PATH = str(FONTS / "DejaVuSerifCondensed-BoldItalic.ttf")

_font_cache = {}
def get_font(path, size):
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]

def measure(text, path, size):
    return get_font(path, size).getlength(text)

def wrap(text, path, size, max_w):
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if measure(trial, path, size) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def draw_text(d, x, y, text, path, size, fill, spacing=0, anchor="l"):
    """Texto con baseline en y. anchor 'l' (izquierda) o 'r' (derecha)."""
    f = get_font(path, size * S)
    if not spacing:
        d.text((x * S, y * S), text, font=f, fill=fill, anchor="l" + "s" if anchor == "l" else "rs")
        return
    widths = [f.getlength(c) for c in text]
    total = sum(widths) + spacing * S * (len(text) - 1)
    cx = x * S if anchor == "l" else x * S - total
    for c, w in zip(text, widths):
        d.text((cx, y * S), c, font=f, fill=fill, anchor="ls")
        cx += w + spacing * S
    return cx  # posición donde terminaría el siguiente carácter

def draw_runs(d, runs, start_y, x=MARGIN):
    y = start_y
    for text, style in runs:
        if style == "bold":
            size, path, fill, lh = 84, BOLD_PATH, DARK, 98
        else:
            size, path, fill, lh = 88, ITALIC_PATH, ACCENT, 102
        for ln in wrap(text, path, size, MAX_W):
            draw_text(d, x, y, ln, path, size, fill)
            y += lh
    return y

def arrow_icon(d, cx, cy, color=ACCENT, r=42):
    d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], outline=color, width=3 * S)
    lw = int(3.5 * S)
    d.line([(cx - 16) * S, cy * S, (cx + 14) * S, cy * S], fill=color, width=lw)
    d.line([(cx + 2) * S, (cy - 12) * S, (cx + 16) * S, cy * S], fill=color, width=lw)
    d.line([(cx + 2) * S, (cy + 12) * S, (cx + 16) * S, cy * S], fill=color, width=lw)

def build_slide(runs, fmt="carrusel", header_left="TRABAJO EN EXCEL", header_right="SOCIAL AD",
                cta_text=None, footer="TRABAJOENEXCEL.COM", swipe_hint=True,
                slide_no=None, start_y=None):
    L = LAYOUTS[fmt]
    H = L["H"]
    if start_y is None:
        start_y = L["start_y"]
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)

    end_y = draw_runs(d, runs, start_y)

    # cabecera: marca con ® en superíndice + etiqueta a la derecha
    hy = L["header_y"]
    x_end = draw_text(d, MARGIN, hy, header_left, BOLD_PATH, 30, DARK, spacing=2)
    d.text((x_end, (hy - 14) * S), "®", font=get_font(BOLD_PATH, 18 * S), fill=DARK, anchor="ls")
    draw_text(d, W - MARGIN, hy, header_right, REGULAR_PATH, 24, GREY, spacing=3, anchor="r")

    # pie: línea, url y, según el formato, CTA / flecha / numeración
    line_y = L["line_y"]
    x2 = 380 if cta_text else 290
    d.rectangle([MARGIN * S, (line_y - 2) * S, x2 * S, (line_y + 2) * S], fill=ACCENT)
    draw_text(d, W - MARGIN, L["url_y"], footer, REGULAR_PATH, 22, GREY, spacing=2, anchor="r")
    if cta_text:
        draw_text(d, MARGIN, L["cta_y"], cta_text, BOLD_PATH, 40, ACCENT, spacing=1)
        if L["arrows"]:
            arrow_icon(d, W - 160, L["cta_y"] - 25)
    elif swipe_hint and L["arrows"]:
        arrow_icon(d, W - 160, L["cta_y"] - 25, r=36)
    if slide_no and L["numbering"]:
        draw_text(d, MARGIN, L["cta_y"], slide_no, REGULAR_PATH, 22, GREY, spacing=2)

    return img.resize((W, H), Image.LANCZOS), end_y

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Genera las imágenes JPG de un post de Instagram")
    parser.add_argument("spec")
    parser.add_argument("out_dir")
    parser.add_argument("--format", dest="fmt", choices=sorted(LAYOUTS), default="carrusel")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slides = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if args.fmt != "carrusel" and len(slides) != 1:
        sys.exit(f"El formato {args.fmt} lleva exactamente 1 imagen (el JSON tiene {len(slides)}).")
    H = LAYOUTS[args.fmt]["H"]
    for i, sdef in enumerate(slides, start=1):
        runs = [tuple(r) for r in sdef["runs"]]
        kwargs = {k: v for k, v in sdef.items() if k != "runs"}
        img, end_y = build_slide(runs, fmt=args.fmt, **kwargs)
        name = f"slide-{i:02d}.jpg"
        img.save(out / name, "JPEG", quality=95)
        overflow = " ⚠ POSIBLE OVERFLOW (ajusta start_y o acorta el texto)" if end_y > LAYOUTS[args.fmt]["limit"] else ""
        print(f"{name}  {img.width}x{H}  (texto termina en y={end_y}){overflow}")

if __name__ == "__main__":
    main()
