"""Panel de aprobación de posts de Instagram.

Flujo: Claude sube un borrador (POST /api/drafts) -> el usuario lo revisa en el panel y
lo aprueba (pasa a la cola) -> un aviso periódico (POST /api/cron/tick, desde GitHub
Actions) publica el post más antiguo de la cola en cada hueco de schedule.txt, sirviendo
el servidor las imágenes, y después BORRA los JPG. Solo se conserva el texto, el estado
y el enlace del post.
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from functools import wraps

from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

import db
import guards
import instagram
import schedule

DEV = os.environ.get("APP_ENV") == "dev"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
API_KEY = os.environ.get("API_KEY", "")
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
MAX_SLIDES = 10
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # límite de Instagram por imagen
TOKEN_REFRESH_DAYS = 20
STUCK_MINUTES = 10
TICK_STALE_HOURS = 2  # sin avisos del programador durante más de esto -> se avisa en el panel

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=60 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=not DEV,
    PERMANENT_SESSION_LIFETIME=dt.timedelta(days=30),
)
db.init_db()


# ----------------------------------------------------------------- seguridad ----

def safe_eq(a: str, b: str) -> bool:
    """Comparación en tiempo constante (admite texto no ASCII)."""
    return hmac.compare_digest(a.encode(), b.encode())


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def check_csrf():
    sent = request.form.get("csrf", "")
    if not sent or not safe_eq(sent, session.get("csrf", "")):
        abort(400, "Formulario caducado. Recarga la página e inténtalo de nuevo.")


app.jinja_env.globals["csrf_token"] = csrf_token


@app.template_filter("fmt")
def fmt_date(value):
    return f"{value[:10]} {value[11:16]} UTC" if value else ""


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("auth"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def api_key_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        sent = header[7:] if header.startswith("Bearer ") else ""
        if not API_KEY or not sent or not safe_eq(sent, API_KEY):
            return jsonify(error="no autorizado"), 401
        return fn(*args, **kwargs)
    return wrapper


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; img-src 'self' data:; style-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
    if request.endpoint not in ("static", "media"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


_attempts: dict[str, list[float]] = {}


def _too_many_attempts(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _attempts.get(ip, []) if now - t < 900]
    _attempts[ip] = recent
    return len(recent) >= 5


# ------------------------------------------------------------------ utilidades --

def build_caption(caption: str, hashtags: list[str]) -> str:
    tags = " ".join("#" + h for h in hashtags)
    return caption.strip() + ("\n\n" + tags if tags else "")


def post_view(row: dict) -> dict:
    row["hashtags"] = json.loads(row["hashtags"])
    row["slides_text"] = json.loads(row["slides_text"])
    row["caption_full"] = build_caption(row["caption"], row["hashtags"])
    return row


def is_stuck(post: dict) -> bool:
    if post["status"] != "publishing":
        return False
    updated = dt.datetime.fromisoformat(post["updated_at"])
    return dt.datetime.now(dt.timezone.utc) - updated > dt.timedelta(minutes=STUCK_MINUTES)


app.jinja_env.globals["is_stuck"] = is_stuck
app.jinja_env.globals["STATUS"] = {
    "draft": "Por aprobar", "approved": "En cola", "publishing": "Publicando…",
    "failed": "Falló", "published": "Publicado", "rejected": "Rechazado",
}


def redact(text: str, hidden: list[str]) -> str:
    for value in hidden:
        if value:
            text = text.replace(value, "***")
    return text


# --------------------------------------------------------------------- token ----

def _fp(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def get_token(conn) -> str:
    """Token vigente: el renovado guardado en la base de datos, salvo que se haya
    cambiado el de la variable de entorno (entonces manda el nuevo)."""
    env_token = os.environ.get("IG_ACCESS_TOKEN", "")
    stored = db.kv_get(conn, "ig_token")
    if stored and db.kv_get(conn, "ig_token_env_fp") == _fp(env_token):
        return stored
    return env_token


def maybe_refresh_token(conn) -> None:
    """Renueva el token si hace más de TOKEN_REFRESH_DAYS. Nunca falla hacia fuera."""
    try:
        now = dt.datetime.now(dt.timezone.utc)
        for key, days in (("ig_token_refreshed_at", TOKEN_REFRESH_DAYS), ("ig_token_tried_at", 0.25)):
            last = db.kv_get(conn, key)
            if last and now - dt.datetime.fromisoformat(last) < dt.timedelta(days=days):
                return
        token = get_token(conn)
        if not token:
            return
        db.kv_set(conn, "ig_token_tried_at", db.now())
        new_token, _ = instagram.refresh(token)
        db.kv_set(conn, "ig_token", new_token)
        db.kv_set(conn, "ig_token_env_fp", _fp(os.environ.get("IG_ACCESS_TOKEN", "")))
        db.kv_set(conn, "ig_token_refreshed_at", db.now())
    except Exception:
        pass  # se reintenta en el próximo inicio de sesión o publicación


# --------------------------------------------------------------------- acceso ---

@app.get("/healthz")
def healthz():
    return "ok"


@app.route("/login", methods=["GET", "POST"])
def login():
    if not ADMIN_PASSWORD:
        return "Servidor sin ADMIN_PASSWORD configurada.", 503
    if request.method == "POST":
        check_csrf()
        ip = request.remote_addr or "?"
        if _too_many_attempts(ip):
            flash("Demasiados intentos. Espera 15 minutos.", "error")
        elif safe_eq(request.form.get("password", ""), ADMIN_PASSWORD):
            session.clear()
            session["auth"] = True
            session.permanent = True
            with db.connect() as conn:
                maybe_refresh_token(conn)
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/") and not target.startswith("//") else url_for("index"))
        else:
            _attempts.setdefault(ip, []).append(time.time())
            flash("Contraseña incorrecta.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    check_csrf()
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------- panel ---

def _queue_context(conn) -> dict:
    """Programación, hora prevista de cada post aprobado y salud del programador."""
    approved = db.query(conn, "SELECT id FROM posts WHERE status = 'approved' ORDER BY approved_at ASC")
    last_slot = db.kv_get(conn, "last_slot")
    last_tick = db.kv_get(conn, "last_tick_at")
    ctx = {"eta": {}, "schedule_text": "", "schedule_error": None, "last_tick": last_tick,
           "tick_stale": (not last_tick) or utcnow() - dt.datetime.fromisoformat(last_tick)
           > dt.timedelta(hours=TICK_STALE_HOURS)}
    try:
        cfg = schedule.load()
        used = dt.datetime.fromisoformat(last_slot) if last_slot else None
        for row, slot in zip(approved, cfg.upcoming(utcnow(), used, len(approved))):
            ctx["eta"][row["id"]] = cfg.label(slot)
        ctx["schedule_text"] = f"{cfg.describe()} · hora de {cfg.tz_name}"
    except schedule.ScheduleError as exc:
        ctx["schedule_error"] = str(exc)
    return ctx


@app.get("/")
@login_required
def index():
    with db.connect() as conn:
        rows = db.query(conn, (
            "SELECT p.id, p.title, p.status, p.created_at, p.approved_at, p.published_at, p.permalink, p.updated_at, "
            "(SELECT COUNT(*) FROM images i WHERE i.post_id = p.id) AS n_images "
            "FROM posts p ORDER BY p.created_at DESC LIMIT 100"))
        refreshed = db.kv_get(conn, "ig_token_refreshed_at")
        queue = _queue_context(conn)
    groups = {s: [r for r in rows if r["status"] == s]
              for s in ("draft", "approved", "publishing", "failed", "published", "rejected")}
    groups["approved"].sort(key=lambda r: r["approved_at"] or "")
    return render_template("index.html", groups=groups, refreshed=refreshed, queue=queue)


def _load_post(conn, pid: str) -> dict:
    row = db.one(conn, "SELECT * FROM posts WHERE id = %s", (pid,))
    if not row:
        abort(404)
    return post_view(row)


@app.get("/post/<pid>")
@login_required
def post_page(pid):
    with db.connect() as conn:
        post = _load_post(conn, pid)
        n_images = db.one(conn, "SELECT COUNT(*) AS n FROM images WHERE post_id = %s", (pid,))["n"]
        queue = _queue_context(conn)
    violations = guards.check(post["caption_full"], *post["slides_text"])
    return render_template("post.html", post=post, n_images=n_images, violations=violations, queue=queue,
                           refresh=post["status"] == "publishing" and not is_stuck(post))


@app.get("/media/<pid>/<int:n>.jpg")
def media(pid, n):
    """Imagen de un borrador. Pública SOLO mientras se publica (Instagram las descarga);
    fuera de esa ventana solo la ve quien ha iniciado sesión."""
    with db.connect() as conn:
        row = db.one(conn, (
            "SELECT p.status, i.data FROM images i JOIN posts p ON p.id = i.post_id "
            "WHERE i.post_id = %s AND i.position = %s"), (pid, n))
    if not row or (not session.get("auth") and row["status"] != "publishing"):
        abort(404)
    return Response(bytes(row["data"]), mimetype="image/jpeg", headers={"Cache-Control": "private, no-store"})


def _set_status(conn, pid: str, allowed_from: tuple[str, ...], status: str, error=None) -> bool:
    marks = ", ".join("%s" for _ in allowed_from)
    rows = db.query(conn, (
        f"UPDATE posts SET status = %s, updated_at = %s, error = %s "
        f"WHERE id = %s AND status IN ({marks}) RETURNING id"),
        (status, db.now(), error, pid, *allowed_from))
    return bool(rows)


@app.post("/post/<pid>/approve")
@login_required
def approve(pid):
    """Autoriza el post: pasa a la cola. Se publica en el próximo hueco libre de schedule.txt."""
    check_csrf()
    if request.form.get("confirm") != "on":
        flash("Marca la casilla de confirmación para autorizar la publicación.", "error")
        return redirect(url_for("post_page", pid=pid))
    with db.connect() as conn:
        post = _load_post(conn, pid)
        n_images = db.one(conn, "SELECT COUNT(*) AS n FROM images WHERE post_id = %s", (pid,))["n"]
        if guards.check(post["caption_full"], *post["slides_text"]):
            flash("El contenido incumple la restricción de CTA. No se puede publicar.", "error")
            return redirect(url_for("post_page", pid=pid))
        if not n_images:
            flash("Este borrador no tiene imágenes.", "error")
            return redirect(url_for("post_page", pid=pid))
        if not (os.environ.get("IG_USER_ID") and get_token(conn)):
            flash("Faltan IG_USER_ID / IG_ACCESS_TOKEN en el servidor.", "error")
            return redirect(url_for("post_page", pid=pid))
        rows = db.query(conn, (
            "UPDATE posts SET status = 'approved', approved_at = %s, updated_at = %s "
            "WHERE id = %s AND status = 'draft' RETURNING id"), (db.now_precise(), db.now(), pid))
        if not rows:
            flash("Este post ya no está en borrador.", "error")
        else:
            flash("Autorizado. Está en la cola y se publicará en el próximo hueco libre.", "ok")
    return redirect(url_for("post_page", pid=pid))


@app.post("/post/<pid>/unqueue")
@login_required
def unqueue(pid):
    """Saca un post de la cola (vuelve a borrador) antes de que llegue su turno."""
    check_csrf()
    with db.connect() as conn:
        rows = db.query(conn, (
            "UPDATE posts SET status = 'draft', approved_at = NULL, updated_at = %s "
            "WHERE id = %s AND status = 'approved' RETURNING id"), (db.now(), pid))
    flash("Sacado de la cola." if rows else "Este post ya no está en la cola.", "ok" if rows else "error")
    return redirect(url_for("post_page", pid=pid))


def _start_publish(pid: str, base_url: str) -> None:
    threading.Thread(target=_publish_worker, args=(pid, base_url), daemon=False).start()


def _claim_slot(conn, slot_iso: str) -> bool:
    """Marca el hueco como usado. Atómico: solo un aviso del programador lo consigue."""
    db.execute(conn, ("INSERT INTO kv (key, value, updated_at) VALUES ('last_slot', '', %s) "
                      "ON CONFLICT (key) DO NOTHING"), (db.now(),))
    return bool(db.query(conn, (
        "UPDATE kv SET value = %s, updated_at = %s WHERE key = 'last_slot' AND value < %s RETURNING key"),
        (slot_iso, db.now(), slot_iso)))


@app.post("/api/cron/tick")
@api_key_required
def api_tick():
    """Aviso del programador (GitHub Actions, cada ~30 min). Si hay un hueco de schedule.txt
    vigente y sin usar, publica el post más antiguo de la cola (o deja el hueco vacío).
    `?force=1` publica ya el más antiguo sin gastar hueco: solo para pruebas manuales."""
    force = request.args.get("force") == "1"
    slot_iso = None
    with db.connect() as conn:
        db.kv_set(conn, "last_tick_at", utcnow().isoformat(timespec="seconds"))
        if not force:
            try:
                slot = schedule.load().due_slot(utcnow())
            except schedule.ScheduleError as exc:
                return jsonify(error=str(exc)), 500
            if slot is None:
                return jsonify(action="idle")
            slot_iso = slot.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
            if not _claim_slot(conn, slot_iso):
                return jsonify(action="slot-used", slot=slot_iso)
        rows = db.query(conn, (
            "UPDATE posts SET status = 'publishing', updated_at = %s, error = NULL "
            "WHERE id = (SELECT id FROM posts WHERE status = 'approved' ORDER BY approved_at ASC LIMIT 1) "
            "AND status = 'approved' RETURNING id"), (db.now(),))
    if not rows:
        return jsonify(action="empty-queue", slot=slot_iso)
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/") or request.url_root.rstrip("/")
    _start_publish(rows[0]["id"], base)
    return jsonify(action="publishing", post_id=rows[0]["id"], slot=slot_iso)


def _publish_worker(pid: str, base_url: str) -> None:
    hidden: list[str] = []
    try:
        with db.connect() as conn:
            maybe_refresh_token(conn)
            post = _load_post(conn, pid)
            n = db.one(conn, "SELECT COUNT(*) AS n FROM images WHERE post_id = %s", (pid,))["n"]
            token = get_token(conn)
        if guards.check(post["caption_full"], *post["slides_text"]):
            raise ValueError("el contenido incumple la restricción de CTA")
        if not n:
            raise ValueError("el post no tiene imágenes")
        user_id = os.environ.get("IG_USER_ID", "")
        hidden = [token, user_id]
        urls = [f"{base_url}/media/{pid}/{i}.jpg" for i in range(n)]
        result = instagram.publish(urls, post["caption_full"], user_id, token)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo deja el post en "failed"
        with db.connect() as conn:
            _set_status(conn, pid, ("publishing",), "failed", redact(str(exc), hidden)[:500])
        return
    with db.connect() as conn:
        db.execute(conn, (
            "UPDATE posts SET status = 'published', updated_at = %s, published_at = %s, "
            "media_id = %s, permalink = %s, error = NULL WHERE id = %s"),
            (db.now(), db.now(), result["media_id"], result["permalink"], pid))
        db.execute(conn, "DELETE FROM images WHERE post_id = %s", (pid,))  # no se guarda nada


@app.post("/post/<pid>/reject")
@login_required
def reject(pid):
    check_csrf()
    with db.connect() as conn:
        if _set_status(conn, pid, ("draft", "approved", "failed"), "rejected"):
            db.execute(conn, "DELETE FROM images WHERE post_id = %s", (pid,))
            flash("Post rechazado. Las imágenes se han borrado.", "ok")
        else:
            flash("Este post no se puede rechazar en su estado actual.", "error")
    return redirect(url_for("index"))


@app.post("/post/<pid>/reopen")
@login_required
def reopen(pid):
    """Un post fallido vuelve a borrador (conserva las imágenes) para revisarlo de nuevo."""
    check_csrf()
    with db.connect() as conn:
        if not _set_status(conn, pid, ("failed",), "draft"):
            flash("Solo se pueden reabrir posts fallidos.", "error")
    return redirect(url_for("post_page", pid=pid))


@app.post("/post/<pid>/unstick")
@login_required
def unstick(pid):
    check_csrf()
    with db.connect() as conn:
        post = _load_post(conn, pid)
        if is_stuck(post):
            _set_status(conn, pid, ("publishing",), "failed",
                        "Interrumpido. Comprueba en Instagram si llegó a publicarse antes de reintentar.")
        else:
            flash("El post sigue publicándose; espera un poco.", "error")
    return redirect(url_for("post_page", pid=pid))


@app.post("/post/<pid>/delete")
@login_required
def delete(pid):
    check_csrf()
    with db.connect() as conn:
        rows = db.query(conn, "DELETE FROM posts WHERE id = %s AND status <> 'publishing' RETURNING id", (pid,))
    flash("Post eliminado." if rows else "No se puede eliminar un post que se está publicando.", "ok" if rows else "error")
    return redirect(url_for("index"))


# ------------------------------------------------------------------------ API ---

def _bad(message: str, code: int = 422):
    return jsonify(error=message), code


@app.post("/api/drafts")
@api_key_required
def api_create_draft():
    title = (request.form.get("title") or "").strip()
    caption = (request.form.get("caption") or "").strip()
    source_url = (request.form.get("source_url") or "").strip()[:300]
    try:
        hashtags = json.loads(request.form.get("hashtags") or "[]")
        slides_text = json.loads(request.form.get("slides_text") or "[]")
    except ValueError:
        return _bad("hashtags y slides_text deben ser JSON")
    if not isinstance(hashtags, list) or not isinstance(slides_text, list):
        return _bad("hashtags y slides_text deben ser listas")
    if not title or len(title) > 120:
        return _bad("title es obligatorio (máx. 120 caracteres)")
    if not caption:
        return _bad("caption es obligatorio")

    tags = []
    for h in hashtags:
        h = str(h).strip().lstrip("#")
        if not re.fullmatch(r"\w+", h):
            return _bad(f"hashtag no válido: {h!r}")
        if h.lower() not in [t.lower() for t in tags]:
            tags.append(h)
    if len(tags) > MAX_HASHTAGS:
        return _bad(f"demasiados hashtags ({len(tags)}); el máximo es {MAX_HASHTAGS}")
    full = build_caption(caption, tags)
    if len(full) > MAX_CAPTION:
        return _bad(f"caption demasiado largo ({len(full)} > {MAX_CAPTION})")

    files = request.files.getlist("slides")
    if not 1 <= len(files) <= MAX_SLIDES:
        return _bad(f"hay que subir entre 1 y {MAX_SLIDES} imágenes")
    images = []
    for f in files:
        data = f.read()
        if not data.startswith(b"\xff\xd8\xff"):
            return _bad(f"{f.filename}: no es un JPEG (Instagram solo acepta JPEG)")
        if len(data) > MAX_IMAGE_BYTES:
            return _bad(f"{f.filename}: supera los 8 MB de Instagram")
        images.append(data)

    violations = guards.check(full, *[str(t) for t in slides_text])
    if violations:
        return _bad("contenido no permitido (CTA con enlace): " + "; ".join(violations))

    pid = uuid.uuid4().hex
    stamp = db.now()
    with db.connect() as conn:
        db.execute(conn, (
            "INSERT INTO posts (id, title, status, caption, hashtags, slides_text, source_url, created_at, updated_at) "
            "VALUES (%s, %s, 'draft', %s, %s, %s, %s, %s, %s)"),
            (pid, title, caption, json.dumps(tags, ensure_ascii=False),
             json.dumps([str(t) for t in slides_text], ensure_ascii=False), source_url or None, stamp, stamp))
        try:
            for i, data in enumerate(images):
                db.execute(conn, "INSERT INTO images (post_id, position, data) VALUES (%s, %s, %s)", (pid, i, data))
        except Exception:
            db.execute(conn, "DELETE FROM posts WHERE id = %s", (pid,))
            raise
    return jsonify(id=pid, url=url_for("post_page", pid=pid, _external=True)), 201


@app.get("/api/posts/<pid>")
@api_key_required
def api_post_status(pid):
    with db.connect() as conn:
        row = db.one(conn, "SELECT id, status, permalink, error, approved_at, published_at FROM posts WHERE id = %s", (pid,))
    return (jsonify(row), 200) if row else (jsonify(error="no existe"), 404)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
