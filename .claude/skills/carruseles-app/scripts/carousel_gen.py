"""
Generador de carruseles de Instagram para trabajoenexcel.com.
Dibuja slides 1080x1350 con Pillow (wrap de texto medido con la fuente real,
sin overflow) y los guarda como JPG, el único formato que admite la API de
Instagram. No necesita rsvg ni fuentes del sistema: usa las de assets/fonts.

Uso:
    python carousel_gen.py slides.json queue/AAAA-MM-DD-tema

Genera slide-01.jpg, slide-02.jpg... en la carpeta de salida.

slides.json: lista de objetos con esta forma:
{
  "runs": [["TEXTO BOLD EN MAYUSCULAS", "bold"], ["frase en italica verde", "italic"]],
  "slide_no": "01 / 06",      // opcional, null en el slide de CTA
  "cta_text": "PLANTILLA DE SPRINT.",  // opcional, solo en el slide final
  "swipe_hint": true,          // opcional, default true; false si hay cta_text
  "start_y": 520               // opcional, ajustar si el bloque de texto es largo
}

Requiere: pip install Pillow
"""
import sys, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
S = 2                # supersampling: se dibuja a 2x y se reduce (bordes suaves)
BG = "#F4EFE1"       # cream / hueso (trabajoenexcel.com)
DARK = "#182A20"     # texto principal
ACCENT = "#2F6B47"   # verde bosque de acento — ver references/style-guide.md
GREY = "#8A9088"

MARGIN = 90
MAX_W = W - 2 * MARGIN

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

def build_slide(runs, header_left="TRABAJO EN EXCEL", header_right="SOCIAL AD",
                cta_text=None, footer="TRABAJOENEXCEL.COM", swipe_hint=True,
                slide_no=None, start_y=520):
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)

    end_y = draw_runs(d, runs, start_y)

    # cabecera: marca con ® en superíndice + etiqueta a la derecha
    x_end = draw_text(d, MARGIN, 90, header_left, BOLD_PATH, 30, DARK, spacing=2)
    d.text((x_end, 76 * S), "®", font=get_font(BOLD_PATH, 18 * S), fill=DARK, anchor="ls")
    draw_text(d, W - MARGIN, 90, header_right, REGULAR_PATH, 24, GREY, spacing=3, anchor="r")

    # pie: línea, url y, según el slide, CTA / flecha / numeración
    line_y = H - 90
    x2 = 380 if cta_text else 290
    d.rectangle([MARGIN * S, (line_y - 2) * S, x2 * S, (line_y + 2) * S], fill=ACCENT)
    draw_text(d, W - MARGIN, H - 60, footer, REGULAR_PATH, 22, GREY, spacing=2, anchor="r")
    if cta_text:
        draw_text(d, MARGIN, H - 160, cta_text, BOLD_PATH, 40, ACCENT, spacing=1)
        arrow_icon(d, W - 160, H - 185)
    elif swipe_hint:
        arrow_icon(d, W - 160, H - 185, r=36)
    if slide_no:
        draw_text(d, MARGIN, H - 160, slide_no, REGULAR_PATH, 22, GREY, spacing=2)

    return img.resize((W, H), Image.LANCZOS), end_y

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    spec_path, out_dir = sys.argv[1], sys.argv[2]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slides = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    for i, sdef in enumerate(slides, start=1):
        runs = [tuple(r) for r in sdef["runs"]]
        kwargs = {k: v for k, v in sdef.items() if k != "runs"}
        img, end_y = build_slide(runs, **kwargs)
        name = f"slide-{i:02d}.jpg"
        img.save(out / name, "JPEG", quality=95)
        overflow = " ⚠ POSIBLE OVERFLOW (ajusta start_y o acorta el texto)" if end_y > H - 200 else ""
        print(f"{name}  (texto termina en y={end_y}){overflow}")

if __name__ == "__main__":
    main()
