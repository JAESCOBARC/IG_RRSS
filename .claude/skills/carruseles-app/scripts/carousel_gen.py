"""
Generador de imágenes de Instagram para trabajoenexcel.com.
Dibuja con Pillow (wrap de texto medido con la fuente real, sin overflow) y guarda JPG,
el único formato que admite la API de Instagram. No necesita rsvg ni fuentes del
sistema: usa Inter Tight de assets/fonts.

Estilo «dark editorial»: titular enorme en Black con tracking apretado, una frase de acento
en lima, párrafo opcional en gris y botones en píldora. Ver references/style-guide.md.

Uso:
    python carousel_gen.py slides.json /tmp/post [--format carrusel|publicacion|historia]

Formatos (--format, por defecto carrusel):
    carrusel     2-10 slides de 1080x1350 (4:5). Portada y CTA final en negro; las intermedias
                 alternan verde tinta y negro (o el tema que indique "theme")
    publicacion  1 imagen de 1080x1350 (4:5), negro
    historia     1 imagen de 1080x1920 (9:16), lima con letra negra, con márgenes de seguridad
                 arriba y abajo (~250 px que Instagram tapa con su interfaz)

Genera slide-01.jpg, slide-02.jpg... en la carpeta de salida.

slides.json: lista de objetos con esta forma:
{
  "runs": [["Titular en blanco", "bold"], ["frase de acento", "italic"]],
  "body": "Párrafo de apoyo en gris",   // opcional
  "slide_no": "01 / 06",      // opcional, solo carrusel; null en el slide de CTA
  "cta_text": "Haz el test gratis",     // opcional, solo en el slide final / imagen única
  "swipe_hint": true,          // opcional, solo carrusel; false si hay cta_text
  "theme": "negro|tinta|lima", // opcional, solo carrusel: fuerza el fondo de esa slide
  "start_y": 220               // opcional, fija el inicio del titular
}
"italic" ya no es cursiva: es el color de acento (lima; en la historia, blanco sobre píldora negra).

Requiere: pip install Pillow
"""
import argparse
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W = 1080
S = 2                # supersampling: se dibuja a 2x y se reduce (bordes suaves)
BLACK = "#0A0A0A"
INK = "#1A2410"      # negro con matiz verde, familia del lima
LIME = "#D4FF3F"
WHITE = "#F5F5F5"
GREY = "#C7C7C7"
LINE = "#5F5F5F"

THEMES = {
    "negro": {"bg": BLACK, "text": WHITE, "accent": LIME, "grey": GREY, "pill_bg": LIME,
              "pill_fg": BLACK, "outline": LINE, "outline_fg": WHITE, "mark": None},
    "tinta": {"bg": INK, "text": WHITE, "accent": LIME, "grey": GREY, "pill_bg": LIME,
              "pill_fg": BLACK, "outline": LINE, "outline_fg": WHITE, "mark": None},
    # sobre lima el acento va en blanco sobre una píldora negra (el lima no se vería)
    "lima": {"bg": LIME, "text": BLACK, "accent": WHITE, "grey": "#2B3410", "pill_bg": BLACK,
             "pill_fg": LIME, "outline": BLACK, "outline_fg": BLACK, "mark": BLACK},
}

MARGIN = 60
MAX_W = W - 2 * MARGIN
TRACK = -0.02        # tracking del titular (fracción del tamaño)
MAX_SIZE, MIN_SIZE = 168, 84


def _layout(h, header_y, start_y, pills_y, limit):
    return {"H": h, "header_y": header_y, "start_y": start_y, "pills_y": pills_y, "limit": limit}


LAYOUTS = {
    "carrusel": _layout(1350, 100, 190, 1350 - 120, 1350 - 120 - 40),
    "publicacion": _layout(1350, 100, 190, 1350 - 120, 1350 - 120 - 40),
    # historia: Instagram tapa ~250 px arriba y abajo; nada importante fuera de y=250..1670
    "historia": _layout(1920, 300, 400, 1920 - 340, 1920 - 340 - 40),
}

FONT_PATH = str(Path(__file__).resolve().parent.parent / "assets" / "fonts" / "InterTight-Variable.ttf")
BLACK_W, SEMIBOLD_W, REGULAR_W = 900, 600, 400

_font_cache = {}
def get_font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        f = ImageFont.truetype(FONT_PATH, size)
        f.set_variation_by_axes([weight])
        _font_cache[key] = f
    return _font_cache[key]

def measure(text, weight, size, track=0.0):
    return get_font(weight, size).getlength(text) + track * size * max(len(text) - 1, 0)

def wrap(text, weight, size, max_w, track=0.0):
    lines, cur = [], ""
    for w in text.split(" "):
        trial = (cur + " " + w).strip()
        if measure(trial, weight, size, track) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def draw_text(d, x, y, text, weight, size, fill, track=0.0, anchor="l"):
    """Texto con baseline en y (coordenadas finales; se escala por S). Devuelve el ancho."""
    f = get_font(weight, size * S)
    total = measure(text, weight, size * S, track)
    cx = x * S if anchor == "l" else x * S - total
    if not track:
        d.text((cx, y * S), text, font=f, fill=fill, anchor="ls")
    else:
        for i, c in enumerate(text):
            off = f.getlength(text[:i]) + track * size * S * i
            d.text((cx + off, y * S), c, font=f, fill=fill, anchor="ls")
    return total / S

def pill(d, x, y, text, size, fg, bg=None, outline=None, arrow=True):
    """Píldora con texto semibold, borde superior en y. Devuelve su ancho."""
    label = text + ("  →" if arrow else "")
    h, pad = 56 + 8, 40
    w = measure(label, SEMIBOLD_W, size) + 2 * pad
    box = [x * S, y * S, (x + w) * S, (y + h) * S]
    d.rounded_rectangle(box, radius=h * S // 2, fill=bg, outline=outline, width=2 * S if outline else 0)
    draw_text(d, x + pad, y + h / 2 + size * 0.36, label, SEMIBOLD_W, size, fg)
    return w

def body_lines(body, size):
    return wrap(body, REGULAR_W, size, MAX_W - 60) if body else []

def fit_title(runs, avail_h, lh_mult):
    """Mayor tamaño (MIN..MAX) con el que el titular cabe en avail_h y ninguna palabra desborda.
    Si una palabra sola (p. ej. una fórmula) es más ancha que la página, baja de MIN hasta que quepa."""
    def lay(size):
        return [(ln, st) for t, st in runs for ln in wrap(t, BLACK_W, size, MAX_W, TRACK)]
    for size in range(MAX_SIZE, 39, -2):
        lines = lay(size)
        if any(measure(ln, BLACK_W, size, TRACK) > MAX_W for ln, _ in lines):
            continue
        if size < MIN_SIZE or len(lines) * size * lh_mult <= avail_h:
            return size, lines
    return 40, lay(40)

def build_slide(runs, fmt="carrusel", theme=None, body=None, cta_text=None, swipe_hint=True,
                slide_no=None, start_y=None, header_left="TRABAJO EN EXCEL", footer="trabajoenexcel.com"):
    L = LAYOUTS[fmt]
    T = THEMES[theme]
    H = L["H"]
    img = Image.new("RGB", (W * S, H * S), T["bg"])
    d = ImageDraw.Draw(img)

    # cabecera: marca a la izquierda, numeración a la derecha
    hy = L["header_y"]
    draw_text(d, MARGIN, hy, header_left, SEMIBOLD_W, 26, T["text"], track=0.08)
    if slide_no and fmt == "carrusel":
        draw_text(d, W - MARGIN, hy, slide_no, REGULAR_W, 26, T["grey"], track=0.06, anchor="r")

    y0 = start_y if start_y is not None else L["start_y"]
    bsize = 38
    blines = body_lines(body, bsize)
    body_h = (len(blines) * int(bsize * 1.5) + 50) if blines else 0
    lh_mult = 1.08 if T["mark"] else 0.98
    avail = L["pills_y"] - 70 - y0 - body_h
    size, lines = fit_title(runs, avail, lh_mult)
    lh = size * lh_mult

    y = y0 + size * 0.9       # baseline de la primera línea (cap-height de Inter ≈ 0.73 em)
    for ln, style in lines:
        if style == "bold":
            draw_text(d, MARGIN, y, ln, BLACK_W, size, T["text"], track=TRACK)
        elif T["mark"]:
            w = measure(ln, BLACK_W, size, TRACK)
            pad = size * 0.16
            d.rounded_rectangle([(MARGIN - pad) * S, (y - size * 0.84) * S, (MARGIN + w + pad) * S,
                                 (y + size * 0.2) * S], radius=int(size * 0.3 * S), fill=T["mark"])
            draw_text(d, MARGIN, y, ln, BLACK_W, size, T["accent"], track=TRACK)
        else:
            draw_text(d, MARGIN, y, ln, BLACK_W, size, T["accent"], track=TRACK)
        y += lh
    end_y = y - lh + size * 0.25

    by = end_y + 70
    for ln in blines:
        draw_text(d, MARGIN, by, ln, REGULAR_W, bsize, T["grey"])
        by += int(bsize * 1.5)
    end_y = max(end_y, by - int(bsize * 1.5) + 12)

    # botones: CTA lima (o negro sobre lima) + web; en slides intermedias, «Desliza»
    py = L["pills_y"]
    if cta_text:
        w = pill(d, MARGIN, py, cta_text, 26, T["pill_fg"], bg=T["pill_bg"])
        pill(d, MARGIN + w + 20, py, footer, 26, T["outline_fg"], outline=T["outline"], arrow=False)
    elif swipe_hint and fmt == "carrusel":
        pill(d, MARGIN, py, "Desliza", 26, T["outline_fg"], outline=T["outline"])
    else:
        pill(d, MARGIN, py, footer, 26, T["outline_fg"], outline=T["outline"], arrow=False)

    return img.resize((W, H), Image.LANCZOS), end_y


def pick_theme(fmt, i, n, sdef):
    if sdef.get("theme"):
        return sdef["theme"]
    if fmt == "historia":
        return "lima"
    if fmt == "publicacion" or i == 1 or i == n or sdef.get("cta_text"):
        return "negro"
    return "tinta" if i % 2 == 0 else "negro"   # intermedias: tinta en 2, 4...; negro en 3, 5...


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
        kwargs = {k: v for k, v in sdef.items() if k not in ("runs", "theme")}
        theme = pick_theme(args.fmt, i, len(slides), sdef)
        img, end_y = build_slide(runs, fmt=args.fmt, theme=theme, **kwargs)
        name = f"slide-{i:02d}.jpg"
        img.save(out / name, "JPEG", quality=95)
        overflow = " ⚠ POSIBLE OVERFLOW (acorta el texto)" if end_y > LAYOUTS[args.fmt]["limit"] else ""
        print(f"{name}  {img.width}x{H}  tema={theme}  (texto termina en y={end_y:.0f}){overflow}")

if __name__ == "__main__":
    main()
