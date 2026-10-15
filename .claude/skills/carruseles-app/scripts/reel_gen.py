"""
Generador de Reels (vídeo animado de hasta 30 s) para trabajoenexcel.com.
Mismo estilo «dark editorial» que carousel_gen.py (reutiliza su fuente, colores y layout):
cada escena es un titular que entra línea a línea, un párrafo opcional y, en la última, los
botones. Una barra lima de progreso recorre la parte alta del vídeo. Lleva una pista de música
ORIGINAL sintetizada aquí mismo (acordes, bajo, bombo suave y hi-hat): no hay samples ni
terceros, así que está libre de derechos. `--no-music` deja el vídeo con pista silenciosa.

Uso:
    python reel_gen.py escenas.json /tmp/reel

Escribe /tmp/reel/video.mp4 y, FUERA de la carpeta, /tmp/reel.preview.jpg (un fotograma por
escena con el texto ya asentado, para revisarlo con Read). H.264 + AAC, 1080x1920, 30 fps, faststart). Instagram exige
3-90 s; esta app limita a 30 s (el generador se niega a pasar de 30).

escenas.json: lista de 2-8 escenas (suman 6-30 s):
{
  "runs": [["Titular en blanco", "bold"], ["frase de acento", "italic"]],
  "body": "Párrafo de apoyo en gris",  // opcional
  "cta_text": "Haz el test gratis",    // opcional; normalmente solo en la última escena
  "theme": "negro|tinta|lima",         // opcional (por defecto alterna negro/tinta; la última, lima)
  "seconds": 4                         // opcional (por defecto 4; entre 2 y 10)
}

Requiere: pip install pillow numpy imageio-ffmpeg   (imageio-ffmpeg trae su propio ffmpeg)
"""
import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carousel_gen as cg  # noqa: E402

W, H, FPS = 1080, 1920, 30
MAX_SECONDS, MIN_SECONDS = 30.0, 6.0
DEFAULT_SCENE, MIN_SCENE, MAX_SCENE = 4.0, 2.0, 10.0
LINE_DELAY, ANIM, RISE = 0.17, 0.45, 56   # s entre líneas, s de cada entrada, px que suben
L = cg.LAYOUTS["historia"]                # márgenes de seguridad de Instagram (~250 px)
S = cg.S


SR = 44100
# Cuatro progresiones (Am-F-C-G, etc.): notas de la tríada en Hz y fundamental del bajo
CHORDS = [((220.00, 261.63, 329.63), 55.00), ((174.61, 220.00, 261.63), 43.65),
          ((261.63, 329.63, 392.00), 65.41), ((196.00, 246.94, 293.66), 49.00)]


def make_music(seconds, path, bpm=96):
    """Pista original (lo-fi suave) de `seconds` s en WAV estéreo. Solo numpy: sin samples."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    beat = 60.0 / bpm
    bar = 4 * beat
    left, right = np.zeros(n), np.zeros(n)
    rng = np.random.default_rng(7)

    for b in range(int(seconds / bar) + 1):
        triad, root = CHORDS[b % len(CHORDS)]
        i0, i1 = int(b * bar * SR), min(int((b + 1) * bar * SR), n)
        if i0 >= n:
            break
        tt = t[i0:i1] - b * bar
        env = np.minimum(tt / 0.25, 1) * np.minimum((bar - tt) / 0.35, 1)   # pad: ataque y cola
        for f in triad:                                                    # leve desafine L/R
            left[i0:i1] += 0.05 * env * np.sin(2 * np.pi * f * 1.002 * tt)
            right[i0:i1] += 0.05 * env * np.sin(2 * np.pi * f * 0.998 * tt)
        for k in range(4):                                                 # bajo en cada negra
            j0, j1 = i0 + int(k * beat * SR), min(i0 + int((k + 1) * beat * SR), n)
            if j0 >= n:
                break
            bt = t[j0:j1] - t[j0]
            note = 0.20 * np.exp(-bt * 3.0) * np.sin(2 * np.pi * root * bt)
            left[j0:j1] += note
            right[j0:j1] += note
            if k in (0, 2):                                                # bombo suave
                kick = 0.28 * np.exp(-bt * 14) * np.sin(2 * np.pi * (45 + 70 * np.exp(-bt * 30)) * bt)
                left[j0:j1] += kick
                right[j0:j1] += kick
            h0 = j0 + int(beat * SR / 2)                                   # hi-hat a contratiempo
            h1 = min(h0 + int(0.06 * SR), n)
            if h0 < n:
                hat = rng.standard_normal(h1 - h0) * np.exp(-np.arange(h1 - h0) / SR * 70)
                hat = 0.035 * np.diff(hat, prepend=0)                      # paso alto simple
                left[h0:h1] += hat
                right[h0:h1] += hat

    fade = np.minimum(t / 0.6, 1) * np.minimum((seconds - t) / 1.5, 1).clip(0, 1)
    stereo = np.stack([left * fade, right * fade], axis=1)
    stereo *= 0.55 / max(np.abs(stereo).max(), 1e-9)                       # nivel moderado (~ -5 dBFS)
    pcm = (stereo * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def sprite(draw_fn, y_top, height):
    """Dibuja con `draw_fn(d, dy)` una franja RGBA de ancho W; devuelve (rgb, alpha, y_top)."""
    layer = Image.new("RGBA", (W * S, height * S), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer), y_top)
    layer = layer.resize((W, height), Image.LANCZOS)
    return layer.convert("RGB"), layer.getchannel("A"), y_top


def build_scene(sdef, theme_name):
    """Devuelve (fondo RGB sin texto, [(sprite, inicio_s)], fin_de_las_entradas_s)."""
    T = cg.THEMES[theme_name]
    runs = [tuple(r) for r in sdef["runs"]]
    body, cta = sdef.get("body"), sdef.get("cta_text")

    bg = Image.new("RGB", (W * cg.S, H * cg.S), T["bg"])
    cg.draw_text(ImageDraw.Draw(bg), cg.MARGIN, L["header_y"], "TRABAJO EN EXCEL",
                 cg.SEMIBOLD_W, 26, T["text"], track=0.08)
    bg = bg.resize((W, H), Image.LANCZOS)

    y0, bsize = L["start_y"], 38
    blines = cg.body_lines(body, bsize)
    body_h = (len(blines) * int(bsize * 1.5) + 50) if blines else 0
    lh_mult = 1.08 if T["mark"] else 0.98
    size, lines = cg.fit_title(runs, L["pills_y"] - 70 - y0 - body_h, lh_mult)
    lh = size * lh_mult

    sprites, t, y = [], 0.15, y0 + size * 0.9
    for ln, style in lines:
        band_top, band_h = int(y - size), int(size * 1.4)

        def draw_line(d, top, ln=ln, style=style, y=y, size=size):
            base = y - top
            if style == "bold":
                cg.draw_text(d, cg.MARGIN, base, ln, cg.BLACK_W, size, T["text"], track=cg.TRACK)
                return
            if T["mark"]:
                w = cg.measure(ln, cg.BLACK_W, size, cg.TRACK)
                pad = size * 0.16
                d.rounded_rectangle([(cg.MARGIN - pad) * S, (base - size * 0.84) * S,
                                     (cg.MARGIN + w + pad) * S, (base + size * 0.2) * S],
                                    radius=int(size * 0.3 * S), fill=T["mark"])
            cg.draw_text(d, cg.MARGIN, base, ln, cg.BLACK_W, size, T["accent"], track=cg.TRACK)

        sprites.append((sprite(draw_line, band_top, band_h), t))
        t += LINE_DELAY
        y += lh
    end_y = y - lh + size * 0.25

    by = end_y + 70
    for ln in blines:
        def draw_body(d, top, ln=ln, by=by):
            cg.draw_text(d, cg.MARGIN, by - top, ln, cg.REGULAR_W, bsize, T["grey"])
        sprites.append((sprite(draw_body, int(by - bsize), int(bsize * 1.6)), t))
        t += LINE_DELAY
        by += int(bsize * 1.5)

    py = L["pills_y"]
    if cta:
        def draw_pills(d, top):
            w = cg.pill(d, cg.MARGIN, py - top, cta, 26, T["pill_fg"], bg=T["pill_bg"])
            cg.pill(d, cg.MARGIN + w + 20, py - top, "trabajoenexcel.com", 26,
                    T["outline_fg"], outline=T["outline"], arrow=False)
    else:
        def draw_pills(d, top):
            cg.pill(d, cg.MARGIN, py - top, "trabajoenexcel.com", 26, T["outline_fg"],
                    outline=T["outline"], arrow=False)
    sprites.append((sprite(draw_pills, py - 4, 90), t + 0.1))
    return bg, sprites, t + 0.1 + ANIM, end_y


def render_frame(bg, sprites, t):
    frame = bg.copy()
    for (rgb, alpha, y_top), start in sprites:
        a = ease((t - start) / ANIM)
        if a <= 0:
            continue
        mask = alpha.point(lambda v, a=a: int(v * a)) if a < 1 else alpha
        frame.paste(rgb, (0, int(y_top + RISE * (1 - a))), mask)
    return frame


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Genera un Reel (vídeo MP4) para Instagram")
    parser.add_argument("spec")
    parser.add_argument("out_dir")
    parser.add_argument("--no-music", action="store_true", help="pista de audio silenciosa")
    args = parser.parse_args()

    scenes = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if not 2 <= len(scenes) <= 8:
        sys.exit(f"Un Reel lleva entre 2 y 8 escenas (el JSON tiene {len(scenes)}).")
    durations = [float(s.get("seconds", DEFAULT_SCENE)) for s in scenes]
    if any(not MIN_SCENE <= d <= MAX_SCENE for d in durations):
        sys.exit(f"Cada escena dura entre {MIN_SCENE:g} y {MAX_SCENE:g} s.")
    total = sum(durations)
    if not MIN_SECONDS <= total <= MAX_SECONDS:
        sys.exit(f"El Reel dura {total:g} s; debe estar entre {MIN_SECONDS:g} y {MAX_SECONDS:g} s.")

    import imageio_ffmpeg
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "video.mp4"
    music_file = out / "_music.wav"
    if args.no_music:
        audio = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    else:
        make_music(total, music_file)
        audio = ["-i", str(music_file)]
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           *audio,
           "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "20",
           "-preset", "medium", "-c:a", "aac", "-b:a", "128k", "-t", f"{total:g}",
           "-movflags", "+faststart", str(target)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    elapsed, n_frames, shots = 0.0, 0, []
    try:
        for i, (sdef, dur) in enumerate(zip(scenes, durations), start=1):
            theme = sdef.get("theme") or ("lima" if i == len(scenes) else ("negro" if i % 2 else "tinta"))
            bg, sprites, settled, end_y = build_scene(sdef, theme)
            warn = " ⚠ POSIBLE OVERFLOW (acorta el texto)" if end_y > L["limit"] else ""
            bar = cg.THEMES[theme]["accent"] if theme != "lima" else cg.BLACK
            late = " ⚠ el texto aún está entrando cuando acaba la escena" if settled > dur else ""
            print(f"escena {i}: {dur:g} s  tema={theme}  (texto termina en y={end_y:.0f}){warn}{late}")
            for f in range(int(round(dur * FPS))):
                frame = render_frame(bg, sprites, f / FPS)
                x = int(W * min((elapsed + f / FPS) / total, 1.0))
                if x:
                    ImageDraw.Draw(frame).rectangle([0, 250, x, 256], fill=bar)
                proc.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
                if f == int(round(dur * FPS)) - 1:
                    shots.append(frame.resize((270, 480), Image.LANCZOS))
                n_frames += 1
            elapsed += dur
    finally:
        proc.stdin.close()
        code = proc.wait()
    music_file.unlink(missing_ok=True)
    sheet = Image.new("RGB", (270 * len(shots) + 10 * (len(shots) - 1), 480), "#888888")
    for k, shot in enumerate(shots):
        sheet.paste(shot, (k * 280, 0))
    preview = out.parent / f"{out.name}.preview.jpg"
    sheet.save(preview, "JPEG", quality=88)
    if code:
        sys.exit(f"ffmpeg falló (código {code}).")
    print(f"Vista previa: {preview}")
    print(f"video.mp4  {W}x{H}  {n_frames / FPS:.1f} s  {target.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
