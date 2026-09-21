"""Pruebas de la app de aprobación (SQLite + Instagram simulado).

Ejecutar desde app/:  python -m unittest -v
"""
import datetime as dt
import io
import json
import os
import sqlite3
import tempfile
import time
import unittest

_TMP = tempfile.mkdtemp()
_CARRUSEL_ONLY = os.path.join(_TMP, "solo_carrusel.txt")
with open(_CARRUSEL_ONLY, "w", encoding="utf-8") as _f:
    _f.write("martes 15:30 carrusel\njueves 19:00 carrusel\n")
os.environ.update(
    APP_ENV="dev", ADMIN_PASSWORD="clave-de-prueba", API_KEY="api-key-de-prueba",
    SECRET_KEY="secreto", SQLITE_PATH=os.path.join(_TMP, "test.db"), DATABASE_URL="",
    IG_USER_ID="17841400000000000", IG_ACCESS_TOKEN="IGAA-TOKEN-SECRETO-DE-PRUEBA",
)

import db  # noqa: E402
import guards  # noqa: E402
import instagram  # noqa: E402
import schedule  # noqa: E402
import server  # noqa: E402
from PIL import Image  # noqa: E402

API = {"Authorization": "Bearer api-key-de-prueba"}

# Huecos por defecto: martes 15:30 y jueves 19:00 (Europe/Madrid). En septiembre rige el
# horario de verano (UTC+2) y en diciembre el de invierno (UTC+1).
MON = "2026-09-21T10:00:00+00:00"
TUE_SLOT = "2026-09-22T13:30:00+00:00"       # martes 15:30 en Madrid
TUE_LATER = "2026-09-22T13:45:00+00:00"
TUE_TOO_LATE = "2026-09-22T15:31:00+00:00"   # 121 min después: fuera de tolerancia
THU_SLOT = "2026-09-24T17:00:00+00:00"       # jueves 19:00 en Madrid
TUE_WINTER = "2026-12-01T14:30:00+00:00"     # martes 15:30 en Madrid (invierno)


def at(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso)


def jpeg(color="#F4EFE1", size=(108, 135)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


FEED = (108, 135)    # 4:5
STORY = (108, 192)   # 9:16


def draft_form(kind="carrusel", n=None, size=None, **over):
    """Formulario de subida válido para cada tipo (se puede forzar nº de imágenes y tamaño)."""
    data = {"title": "Prueba", "caption": "Excel para tu día a día.\nHaz el test gratis en trabajoenexcel.com.",
            "hashtags": json.dumps(["excel", "#productividad"]),
            "slides_text": json.dumps(["TU EQUIPO HACE SPRINTS. Pero no hace Scrum."])}
    if kind != "carrusel":
        data["kind"] = kind
    if kind == "historia":
        data["caption"], data["hashtags"] = "", "[]"
    data.update(over)
    n = n or (2 if kind == "carrusel" else 1)
    size = size or (STORY if kind == "historia" else FEED)
    data["slides"] = [(io.BytesIO(jpeg(("#F4EFE1", "#2F6B47", "#182A20")[i % 3], size)), f"slide-{i + 1:02d}.jpg")
                      for i in range(n)]
    return data


class Base(unittest.TestCase):
    def setUp(self):
        with db.connect() as conn:
            db.execute(conn, "DELETE FROM images")
            db.execute(conn, "DELETE FROM posts")
            db.execute(conn, "DELETE FROM kv")
            db.execute(conn, "DELETE FROM users")
            db.execute(conn, "DELETE FROM schedule_slots")
        server._attempts.clear()  # el límite de intentos de login es global: que no pase de una prueba a otra
        self.client = server.app.test_client()
        self._publish, self._refresh, self._utcnow = instagram.publish, instagram.refresh, server.utcnow
        self._schedule_file = schedule.SCHEDULE_FILE  # el de verdad (app/schedule.txt)
        schedule.SCHEDULE_FILE = _CARRUSEL_ONLY
        instagram.refresh = lambda token: (_ for _ in ()).throw(instagram.IGError("no toca"))

    def tearDown(self):
        instagram.publish, instagram.refresh, server.utcnow = self._publish, self._refresh, self._utcnow
        schedule.SCHEDULE_FILE = self._schedule_file

    # ayudas
    def upload(self, kind="carrusel", **over):
        return self.client.post("/api/drafts", headers=API, data=draft_form(kind, **over),
                                content_type="multipart/form-data")

    def draft(self, kind="carrusel", **over) -> str:
        r = self.upload(kind, **over)
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()["id"]

    def login(self, client=None):
        client = client or self.client
        client.get("/login")
        with client.session_transaction() as s:
            token = s["csrf"]
        return client.post("/login", data={"username": "admin", "password": "clave-de-prueba", "csrf": token})

    def csrf(self, client=None):
        """Token CSRF vigente: se genera al pintar cualquier página."""
        client = client or self.client
        client.get("/")
        with client.session_transaction() as s:
            return s["csrf"]

    def approve(self, pid, confirm=True):
        self.login()
        data = {"csrf": self.csrf()}
        if confirm:
            data["confirm"] = "on"
        return self.client.post(f"/post/{pid}/approve", data=data)

    def tick(self, when, force=False, headers=API, kind=None):
        server.utcnow = lambda: at(when)
        url = "/api/cron/tick" + ("?force=1" if force else "") + (f"{'&' if force else '?'}kind={kind}" if kind else "")
        return self.client.post(url, headers=headers)

    def status(self, pid):
        with db.connect() as conn:
            return db.one(conn, "SELECT * FROM posts WHERE id = %s", (pid,))

    def n_images(self, pid):
        with db.connect() as conn:
            return db.one(conn, "SELECT COUNT(*) AS n FROM images WHERE post_id = %s", (pid,))["n"]

    def wait_for(self, pid, wanted, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            if self.status(pid)["status"] in wanted:
                return
            time.sleep(0.05)
        self.fail(f"el post no llegó a {wanted}: {self.status(pid)['status']}")


class ApiTests(Base):
    def test_sin_api_key_401(self):
        r = self.client.post("/api/drafts", data=draft_form(), content_type="multipart/form-data")
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/api/drafts", headers={"Authorization": "Bearer otra"}, data=draft_form(),
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 401)

    def test_borrador_valido(self):
        r = self.upload()
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        pid = r.get_json()["id"]
        post = self.status(pid)
        self.assertEqual(post["status"], "draft")
        self.assertEqual(json.loads(post["hashtags"]), ["excel", "productividad"])
        self.assertEqual(self.n_images(pid), 2)

    def test_rechaza_png_y_falsos_jpeg(self):
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        form = draft_form("publicacion")
        form["slides"] = [(io.BytesIO(buf.getvalue()), "slide-01.jpg")]
        r = self.client.post("/api/drafts", headers=API, data=form, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 422)
        self.assertIn("JPEG", r.get_json()["error"])

    def test_rechaza_cta_con_enlace_en_caption_y_slides(self):
        r = self.upload(caption="Aprende Excel.\nComenta NIVEL y te dejo el link.")
        self.assertEqual(r.status_code, 422)
        r = self.upload(slides_text=json.dumps(["COMENTA NIVEL", "y te paso el link"]))
        self.assertEqual(r.status_code, 422)
        with db.connect() as conn:
            self.assertEqual(db.one(conn, "SELECT COUNT(*) AS n FROM posts")["n"], 0)

    def test_listado_reciente_exige_api_key_y_no_expone_texto(self):
        self.draft(title="Primero")
        self.draft(title="Segundo")
        self.assertEqual(self.client.get("/api/posts").status_code, 401)
        rows = self.client.get("/api/posts?limit=1", headers=API).get_json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {"id", "title", "status", "kind", "source_url", "created_at", "published_at"})
        self.assertEqual(self.client.get("/api/posts?limit=x", headers=API).status_code, 400)

    def test_publicacion_e_historia(self):
        pub = self.upload("publicacion")
        self.assertEqual(pub.status_code, 201, pub.get_data(as_text=True))
        self.assertEqual(self.status(pub.get_json()["id"])["kind"], "publicacion")
        his = self.upload("historia")
        self.assertEqual(his.status_code, 201, his.get_data(as_text=True))
        post = self.status(his.get_json()["id"])
        self.assertEqual((post["kind"], post["caption"], post["hashtags"]), ("historia", "", "[]"))

    def test_historia_ignora_caption_y_hashtags(self):
        r = self.upload("historia", caption="texto que no se muestra", hashtags=json.dumps(["excel"]))
        self.assertEqual(r.status_code, 201)
        post = self.status(r.get_json()["id"])
        self.assertEqual((post["caption"], post["hashtags"]), ("", "[]"))

    def test_reglas_por_tipo(self):
        self.assertEqual(self.upload("carrusel", n=1).status_code, 422)        # un carrusel lleva 2 o más
        self.assertEqual(self.upload("publicacion", n=2).status_code, 422)     # una publicación, solo 1
        self.assertEqual(self.upload("historia", n=2).status_code, 422)
        self.assertEqual(self.upload("publicacion", caption="").status_code, 422)  # la publicación exige caption
        self.assertEqual(self.upload("reel").status_code, 422)                 # tipo desconocido

    def test_proporcion_de_imagen_por_tipo(self):
        r = self.upload("historia", size=FEED)            # una imagen 4:5 no vale como historia
        self.assertEqual(r.status_code, 422)
        self.assertIn("9:16", r.get_json()["error"])
        self.assertEqual(self.upload("publicacion", size=STORY).status_code, 422)   # 9:16 no vale en el feed
        self.assertEqual(self.upload("publicacion", size=(108, 108)).status_code, 201)  # 1:1 sí
        self.assertEqual(self.upload("carrusel", size=(190, 100)).status_code, 201)     # 1,9:1: dentro de 1,91
        self.assertEqual(self.upload("carrusel", size=(200, 100)).status_code, 422)     # 2:1: fuera del máximo

    def test_jpeg_size(self):
        self.assertEqual(server.jpeg_size(jpeg(size=(108, 192))), (108, 192))
        self.assertEqual(server.jpeg_size(jpeg(size=(1080, 1350))), (1080, 1350))
        self.assertIsNone(server.jpeg_size(b"\xff\xd8\xff\xd9"))

    def test_limites(self):
        self.assertEqual(self.upload(caption="x" * 2300).status_code, 422)
        self.assertEqual(self.upload(hashtags=json.dumps([f"t{i}" for i in range(31)])).status_code, 422)
        self.assertEqual(self.upload(hashtags=json.dumps(["con espacio"])).status_code, 422)
        self.assertEqual(self.upload(title="").status_code, 422)


class AccessTests(Base):
    def test_panel_requiere_login(self):
        pid = self.draft()
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get(f"/post/{pid}").status_code, 302)
        self.assertEqual(self.client.get(f"/media/{pid}/0.jpg").status_code, 404)

    def test_login(self):
        c = server.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf"]
        r = c.post("/login", data={"username": "admin", "password": "mala", "csrf": token})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.get("/").status_code, 302)
        self.assertEqual(self.login(c).status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)

    def test_login_sin_csrf_400(self):
        self.assertEqual(self.client.post("/login", data={"username": "admin", "password": "clave-de-prueba"}).status_code, 400)

    def test_redireccion_next_solo_relativa(self):
        c = server.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf"]
        r = c.post("/login?next=//evil.com", data={"username": "admin", "password": "clave-de-prueba", "csrf": token})
        self.assertEqual(r.headers["Location"], "/")

    def test_media_visible_con_sesion(self):
        pid = self.draft()
        self.login()
        r = self.client.get(f"/media/{pid}/0.jpg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/jpeg")

    def test_paginas_renderizan(self):
        pid = self.draft()
        self.login()
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Por aprobar", html)
        self.assertIn(f"/media/{pid}/0.jpg", html)
        page = self.client.get(f"/post/{pid}").get_data(as_text=True)
        self.assertIn("Aprobar y poner en cola", page)
        self.assertIn("#productividad", page)

    def test_sin_csrf_400(self):
        pid = self.draft()
        self.login()
        self.assertEqual(self.client.post(f"/post/{pid}/approve", data={"confirm": "on"}).status_code, 400)
        self.assertEqual(self.client.post(f"/post/{pid}/reject", data={}).status_code, 400)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.cfg = schedule.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.txt"))

    def test_archivo_por_defecto(self):
        self.assertEqual(self.cfg.tz_name, "Europe/Madrid")
        self.assertEqual([(d, f"{t:%H:%M}", k) for d, t, k in self.cfg.slots],
                         [(1, "15:30", "carrusel"), (3, "19:00", "historia"), (3, "19:00", "publicacion")])
        self.assertEqual(self.cfg.describe(),
                         "martes 15:30 (carrusel), jueves 19:00 (historia), jueves 19:00 (publicación)")

    def test_hueco_vigente_verano(self):
        self.assertEqual(self.cfg.due_slots(at("2026-09-22T13:29:00+00:00")), {})
        self.assertEqual(self.cfg.due_slots(at(TUE_SLOT)), {"carrusel": at(TUE_SLOT)})
        self.assertEqual(self.cfg.due_slots(at("2026-09-22T15:29:00+00:00")), {"carrusel": at(TUE_SLOT)})
        self.assertEqual(self.cfg.due_slots(at(TUE_TOO_LATE)), {})
        self.assertEqual(self.cfg.due_slots(at(THU_SLOT)),
                         {"publicacion": at(THU_SLOT), "historia": at(THU_SLOT)})
        self.assertEqual(self.cfg.due_slots(at(MON)), {})

    def test_cambio_de_hora_invierno(self):
        self.assertEqual(self.cfg.due_slots(at(TUE_WINTER)), {"carrusel": at(TUE_WINTER)})
        self.assertEqual(self.cfg.due_slots(at("2026-12-01T13:30:00+00:00")), {})  # 14:30 en Madrid: aún no

    def test_proximos_huecos_por_tipo(self):
        now = at("2026-09-22T10:00:00+00:00")
        self.assertEqual(self.cfg.upcoming(now, None, 3, "carrusel"),
                         [at(TUE_SLOT), at("2026-09-29T13:30:00+00:00"), at("2026-10-06T13:30:00+00:00")])
        self.assertEqual(self.cfg.upcoming(now, at(TUE_SLOT), 1, "carrusel"), [at("2026-09-29T13:30:00+00:00")])
        self.assertEqual(self.cfg.upcoming(now, None, 2, "historia"), [at(THU_SLOT), at("2026-10-01T17:00:00+00:00")])
        self.assertEqual(self.cfg.label(at(TUE_SLOT)), "martes 22 sep, 15:30")

    def test_errores_de_formato(self):
        for text in ["lunes 25:00 carrusel", "foo 10:00 carrusel", "martes 10:00", "martes carrusel",
                     "martes 10:00 reel", "zona: Marte/Olimpo\nmartes 10:00 carrusel",
                     "tolerancia_minutos: mucha\nmartes 10:00 carrusel", "# solo comentarios"]:
            with self.assertRaises(schedule.ScheduleError, msg=text):
                schedule.parse(text)

    def test_acentos_y_varios_huecos(self):
        cfg = schedule.parse("miércoles 9:05 publicación\nmiercoles 18:00 historia\nsábado 10:00 carrusel")
        self.assertEqual(len(cfg.slots), 3)
        self.assertEqual(cfg.kinds(), {"publicacion", "historia", "carrusel"})


class QueueTests(Base):
    """Aprobar pone en cola; publica el aviso del programador en su hueco."""

    def fake_publish(self, calls=None):
        def fake(urls, caption, user_id, token, **kw):
            if calls is not None:
                calls.append(urls)
            return {"media_id": "123", "permalink": "https://www.instagram.com/p/XYZ/"}
        instagram.publish = fake

    def test_aprobar_no_publica_al_momento(self):
        pid = self.draft()
        calls = []
        self.fake_publish(calls)
        self.approve(pid)
        time.sleep(0.2)
        self.assertEqual(self.status(pid)["status"], "approved")
        self.assertIsNotNone(self.status(pid)["approved_at"])
        self.assertFalse(calls)

    def test_sin_confirmar_no_se_encola(self):
        pid = self.draft()
        self.approve(pid, confirm=False)
        self.assertEqual(self.status(pid)["status"], "draft")

    def test_un_post_por_hueco_por_orden_de_aprobacion(self):
        a, b = self.draft(title="A"), self.draft(title="B")
        calls = []
        self.fake_publish(calls)
        self.approve(a)
        self.approve(b)
        self.assertEqual(self.tick(MON).get_json()["action"], "idle")
        r = self.tick(TUE_SLOT).get_json()
        self.assertEqual((r["action"], r["post_id"]), ("publishing", a))
        self.wait_for(a, {"published"})
        self.assertEqual(self.status(b)["status"], "approved")
        # mismo hueco otra vez (el cron avisa cada 30 min): no publica nada más
        self.assertEqual(self.tick(TUE_LATER).get_json()["action"], "slot-used")
        self.assertEqual(self.status(b)["status"], "approved")
        # siguiente hueco: le toca a B
        self.assertEqual(self.tick(THU_SLOT).get_json()["post_id"], b)
        self.wait_for(b, {"published"})
        self.assertEqual(len(calls), 2)

    def test_publica_borra_imagenes_y_las_expone_solo_mientras_publica(self):
        pid = self.draft()
        seen = {}

        def fake_publish(urls, caption, user_id, token, **kw):
            anon = server.app.test_client()  # sin sesión, como Instagram
            seen["anon"] = [anon.get(u.replace("http://localhost", "")).status_code for u in urls]
            seen["urls"], seen["caption"], seen["token"] = urls, caption, token
            return {"media_id": "123", "permalink": "https://www.instagram.com/p/XYZ/"}

        instagram.publish = fake_publish
        self.approve(pid)
        # en cola las imágenes NO son públicas
        self.assertEqual(server.app.test_client().get(f"/media/{pid}/0.jpg").status_code, 404)
        self.tick(TUE_SLOT)
        self.wait_for(pid, {"published"})
        post = self.status(pid)
        self.assertEqual(post["permalink"], "https://www.instagram.com/p/XYZ/")
        self.assertEqual(seen["anon"], [200, 200], "públicas mientras se publica")
        self.assertTrue(seen["caption"].endswith("#excel #productividad"))
        self.assertEqual(seen["token"], "IGAA-TOKEN-SECRETO-DE-PRUEBA")
        self.assertEqual(self.n_images(pid), 0, "no se conserva ningún JPG")
        self.assertEqual(server.app.test_client().get(f"/media/{pid}/0.jpg").status_code, 404)
        self.assertEqual(self.client.get(f"/media/{pid}/0.jpg").status_code, 404)

    def test_hueco_sin_posts_se_pierde(self):
        self.fake_publish()
        self.assertEqual(self.tick(TUE_SLOT).get_json()["action"], "empty-queue")
        pid = self.draft()
        self.approve(pid)  # aprobado DESPUÉS de que pasara el aviso de ese hueco
        self.assertEqual(self.tick(TUE_LATER).get_json()["action"], "slot-used")
        self.assertEqual(self.status(pid)["status"], "approved")
        self.assertEqual(self.tick(THU_SLOT).get_json()["post_id"], pid)

    def test_fuera_de_tolerancia_no_publica(self):
        pid = self.draft()
        self.fake_publish()
        self.approve(pid)
        self.assertEqual(self.tick(TUE_TOO_LATE).get_json()["action"], "idle")
        self.assertEqual(self.status(pid)["status"], "approved")

    def test_tick_exige_api_key(self):
        self.assertEqual(self.tick(TUE_SLOT, headers={}).status_code, 401)
        self.assertEqual(self.tick(TUE_SLOT, headers={"Authorization": "Bearer otra"}).status_code, 401)

    def test_force_publica_sin_gastar_hueco(self):
        a, b = self.draft(title="A"), self.draft(title="B")
        self.fake_publish()
        self.approve(a)
        self.approve(b)
        self.assertEqual(self.tick(MON, force=True).get_json()["post_id"], a)
        self.wait_for(a, {"published"})
        self.assertEqual(self.tick(TUE_SLOT).get_json()["post_id"], b)  # el hueco seguía libre
        self.wait_for(b, {"published"})

    def test_fallo_conserva_imagenes_y_oculta_credenciales(self):
        pid = self.draft()

        def failing(urls, caption, user_id, token, **kw):
            raise instagram.IGError(f"API 400 en {user_id}/media con {token}: Invalid OAuth access token")

        instagram.publish = failing
        self.approve(pid)
        self.tick(TUE_SLOT)
        self.wait_for(pid, {"failed"})
        post = self.status(pid)
        self.assertNotIn("IGAA-TOKEN", post["error"])
        self.assertNotIn("17841400000000000", post["error"])
        self.assertIn("***", post["error"])
        self.assertEqual(self.n_images(pid), 2)
        self.client.post(f"/post/{pid}/reopen", data={"csrf": self.csrf()})
        self.assertEqual(self.status(pid)["status"], "draft")

    def test_contenido_prohibido_no_llega_a_publicarse(self):
        pid = self.draft()
        self.approve(pid)
        with db.connect() as conn:  # simula un registro manipulado tras aprobar
            db.execute(conn, "UPDATE posts SET caption = %s WHERE id = %s", ("Comenta EXCEL y te dejo el link", pid))
        called = []
        instagram.publish = lambda *a, **k: called.append(1)
        self.tick(TUE_SLOT)
        self.wait_for(pid, {"failed"})
        self.assertFalse(called)
        self.assertIn("restricción de CTA", self.status(pid)["error"])

    def test_aprobar_dos_veces_encola_una_vez(self):
        pid = self.draft()
        calls = []
        self.fake_publish(calls)
        self.approve(pid)
        self.approve(pid)
        self.tick(TUE_SLOT)
        self.wait_for(pid, {"published"})
        time.sleep(0.2)
        self.assertEqual(len(calls), 1)

    def test_sacar_de_la_cola_y_rechazar(self):
        pid = self.draft()
        self.approve(pid)
        self.client.post(f"/post/{pid}/unqueue", data={"csrf": self.csrf()})
        self.assertEqual(self.status(pid)["status"], "draft")
        self.assertIsNone(self.status(pid)["approved_at"])
        self.approve(pid)
        self.client.post(f"/post/{pid}/reject", data={"csrf": self.csrf()})
        self.assertEqual(self.status(pid)["status"], "rejected")
        self.assertEqual(self.n_images(pid), 0)

    def test_cta_prohibido_no_se_aprueba(self):
        pid = self.draft()
        with db.connect() as conn:
            db.execute(conn, "UPDATE posts SET caption = %s WHERE id = %s", ("Comenta EXCEL y te dejo el link", pid))
        self.approve(pid)
        self.assertEqual(self.status(pid)["status"], "draft")

    def test_panel_muestra_cola_hora_prevista_y_avisos(self):
        pid = self.draft()
        self.approve(pid)
        server.utcnow = lambda: at("2026-09-22T10:00:00+00:00")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("En cola", html)
        self.assertIn("Sale: martes 22 sep, 15:30", html)
        self.assertIn("El programador no se ha comunicado", html)  # nunca ha habido un aviso
        self.tick("2026-09-22T10:00:00+00:00")
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("El programador no se ha comunicado", html)
        self.assertIn("martes 15:30 (carrusel), jueves 19:00 (carrusel)", html)
        page = self.client.get(f"/post/{pid}").get_data(as_text=True)
        self.assertIn("Sacar de la cola", page)

    def test_programacion_invalida_devuelve_error_y_lo_muestra(self):
        bad = os.path.join(_TMP, "malo.txt")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("martes 99:99\n")
        schedule.SCHEDULE_FILE = bad
        r = self.tick(TUE_SLOT)
        self.assertEqual(r.status_code, 500)
        self.login()
        self.assertIn("no es válida", self.client.get("/").get_data(as_text=True))


class KindQueueTests(Base):
    """Un hueco por tipo (schedule.txt real): carrusel el martes; publicación e historia el jueves."""

    def setUp(self):
        super().setUp()
        schedule.SCHEDULE_FILE = self._schedule_file
        self.calls = []

        def fake(urls, caption, user_id, token, kind="carrusel"):
            self.calls.append({"kind": kind, "n": len(urls), "caption": caption})
            return {"media_id": kind, "permalink": f"https://www.instagram.com/p/{kind}/"}

        instagram.publish = fake

    def test_publicacion_e_historia_salen_juntas_el_jueves(self):
        car, pub, his = self.draft("carrusel"), self.draft("publicacion"), self.draft("historia")
        for pid in (car, pub, his):
            self.approve(pid)
        self.assertEqual(self.tick(MON).get_json()["action"], "idle")
        r = self.tick(THU_SLOT).get_json()
        self.assertEqual(r["action"], "publishing")
        self.assertEqual({p["kind"] for p in r["posts"]}, {"publicacion", "historia"})
        self.wait_for(pub, {"published"})
        self.wait_for(his, {"published"})
        self.assertEqual(self.status(car)["status"], "approved")   # el carrusel espera a su hueco del martes
        by_kind = {c["kind"]: c for c in self.calls}
        self.assertEqual(by_kind["historia"]["caption"], "")       # las historias no llevan texto
        self.assertEqual((by_kind["historia"]["n"], by_kind["publicacion"]["n"]), (1, 1))
        self.assertIn("#excel", by_kind["publicacion"]["caption"])
        for pid in (pub, his):
            self.assertEqual(self.n_images(pid), 0)                # se borran las imágenes de ambos
        # la semana siguiente le toca al carrusel
        self.assertEqual(self.tick("2026-09-29T13:30:00+00:00").get_json()["post_id"], car)
        self.wait_for(car, {"published"})
        self.assertEqual([c["kind"] for c in self.calls].count("carrusel"), 1)

    def test_cada_tipo_tiene_su_cola_y_su_hueco(self):
        h1, h2 = self.draft("historia", title="H1"), self.draft("historia", title="H2")
        self.approve(h1)
        self.approve(h2)
        self.assertEqual(self.tick(THU_SLOT).get_json()["post_id"], h1)   # solo una historia por hueco
        self.wait_for(h1, {"published"})
        self.assertEqual(self.tick("2026-09-24T17:30:00+00:00").get_json()["action"], "slot-used")
        self.assertEqual(self.status(h2)["status"], "approved")

    def test_hueco_de_un_tipo_sin_posts_no_afecta_al_otro(self):
        pub = self.draft("publicacion")
        self.approve(pub)                                          # no hay historia aprobada
        r = self.tick(THU_SLOT).get_json()
        self.assertEqual([p["kind"] for p in r["posts"]], ["publicacion"])
        self.wait_for(pub, {"published"})
        his = self.draft("historia")
        self.approve(his)                                          # tarde: su hueco de esta semana ya pasó
        self.assertEqual(self.tick("2026-09-24T17:40:00+00:00").get_json()["action"], "slot-used")
        self.assertEqual(self.status(his)["status"], "approved")

    def test_forzar_un_tipo_concreto(self):
        car, his = self.draft("carrusel"), self.draft("historia")
        self.approve(car)
        self.approve(his)
        self.assertEqual(self.tick(MON, force=True, kind="historia").get_json()["post_id"], his)
        self.wait_for(his, {"published"})
        self.assertEqual(self.status(car)["status"], "approved")
        self.assertEqual(self.tick(MON, force=True, kind="reel").status_code, 400)

    def test_un_fallo_no_impide_publicar_el_otro_tipo(self):
        pub, his = self.draft("publicacion"), self.draft("historia")
        self.approve(pub)
        self.approve(his)

        def fake(urls, caption, user_id, token, kind="carrusel"):
            if kind == "publicacion":
                raise instagram.IGError("API 400: fallo simulado")
            return {"media_id": "1", "permalink": ""}

        instagram.publish = fake
        self.tick(THU_SLOT)
        self.wait_for(pub, {"failed"})
        self.wait_for(his, {"published"})

    def test_panel_hora_prevista_por_tipo_y_aviso_sin_hueco(self):
        car, his = self.draft("carrusel"), self.draft("historia")
        self.approve(car)
        self.approve(his)
        server.utcnow = lambda: at("2026-09-21T10:00:00+00:00")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Sale: martes 22 sep, 15:30", html)
        self.assertIn("Sale: jueves 24 sep, 19:00", html)
        self.assertIn("Historia", html)
        page = self.client.get(f"/post/{his}").get_data(as_text=True)
        self.assertIn("no llevan texto de publicación", page)
        # un tipo aprobado sin hueco definido se avisa
        with db.connect() as conn:
            db.execute(conn, "DELETE FROM schedule_slots WHERE kind = 'historia'")
        self.assertIn("sin ningún hueco en la programación", self.client.get("/").get_data(as_text=True))

    def test_migracion_de_una_base_sin_columna_kind(self):
        old = os.path.join(_TMP, "vieja.db")
        con = sqlite3.connect(old)
        con.execute("CREATE TABLE posts (id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL, "
                    "caption TEXT NOT NULL, hashtags TEXT NOT NULL, slides_text TEXT NOT NULL, source_url TEXT, "
                    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, approved_at TEXT, published_at TEXT, "
                    "media_id TEXT, permalink TEXT, error TEXT)")
        con.execute("INSERT INTO posts (id, title, status, caption, hashtags, slides_text, created_at, updated_at) "
                    "VALUES ('x', 'Viejo', 'published', 'c', '[]', '[]', 'a', 'b')")
        con.commit()
        con.close()
        previous = db.SQLITE_PATH
        db.SQLITE_PATH = old
        try:
            db.init_db()
            db.init_db()  # es idempotente
            with db.connect() as conn:
                self.assertEqual(db.one(conn, "SELECT kind FROM posts WHERE id = 'x'")["kind"], "carrusel")
        finally:
            db.SQLITE_PATH = previous


class UserTests(Base):
    """Varios usuarios: alta, baja, roles y acceso."""

    def post(self, client, path, **data):
        client.get("/login")
        with client.session_transaction() as s:
            token = s["csrf"]
        return client.post(path, data={"csrf": token, **data})

    def as_admin(self):
        self.login()
        return self.client

    def create(self, name="ana", password="clave-larga-1", role="editor"):
        r = self.post(self.as_admin(), "/admin/users", username=name, password=password, role=role)
        self.assertEqual(r.status_code, 302)
        with db.connect() as conn:
            return db.one(conn, "SELECT * FROM users WHERE username = %s", (name.lower(),))

    def login_as(self, name, password="clave-larga-1"):
        c = server.app.test_client()
        r = self.post(c, "/login", username=name, password=password)
        return c, r

    def test_crear_usuario_y_entrar(self):
        row = self.create("Ana")  # el nombre se guarda en minúsculas
        self.assertEqual(row["username"], "ana")
        self.assertNotIn("clave-larga-1", row["password_hash"])  # cifrada, nunca en claro
        c, r = self.login_as("ANA")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)

    def test_credenciales_incorrectas(self):
        self.create("ana")
        for user, pw in (("ana", "otra-clave-x"), ("nadie", "clave-larga-1"), ("ana", "")):
            c, r = self.login_as(user, pw)
            self.assertEqual(r.status_code, 200, (user, pw))
            self.assertEqual(c.get("/").status_code, 302)

    def test_eliminar_usuario_le_quita_el_acceso_al_instante(self):
        row = self.create("ana")
        c, _ = self.login_as("ana")
        self.assertEqual(c.get("/").status_code, 200)
        r = self.post(self.client, f"/admin/users/{row['id']}/delete")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/").status_code, 302)  # su sesión ya no vale
        c2, _ = self.login_as("ana")
        self.assertEqual(c2.get("/").status_code, 302)  # ni puede volver a entrar

    def test_no_se_puede_eliminar_la_propia_cuenta(self):
        row = self.create("ana", role="admin")
        c, _ = self.login_as("ana")
        self.post(c, f"/admin/users/{row['id']}/delete")
        self.assertEqual(c.get("/admin/users").status_code, 200)

    def test_editor_no_gestiona_usuarios_ni_programacion(self):
        self.create("ana", role="editor")
        c, _ = self.login_as("ana")
        for path in ("/admin/users", "/admin/schedule"):
            self.assertEqual(c.get(path).status_code, 403, path)
        self.assertEqual(self.post(c, "/admin/users", username="otro", password="clave-larga-1", role="admin").status_code, 403)
        self.assertEqual(self.post(c, "/admin/schedule/slots", day="0", time="10:00", kind="carrusel").status_code, 403)
        html = c.get("/").get_data(as_text=True)
        self.assertNotIn("/admin/users", html)
        self.assertEqual(c.get("/").status_code, 200)  # pero sí puede usar el panel

    def test_admin_de_la_base_de_datos_gestiona_usuarios(self):
        self.create("jefe", role="admin")
        c, _ = self.login_as("jefe")
        self.assertEqual(c.get("/admin/users").status_code, 200)
        self.assertEqual(c.get("/admin/schedule").status_code, 200)

    def test_validaciones_de_alta(self):
        admin = self.as_admin()
        for name, pw, role in (("ab", "clave-larga-1", "editor"), ("con espacio", "clave-larga-1", "editor"),
                               ("admin", "clave-larga-1", "editor"), ("ana", "corta", "editor"),
                               ("ana", "clave-larga-1", "superhéroe")):
            self.post(admin, "/admin/users", username=name, password=pw, role=role)
        with db.connect() as conn:
            self.assertEqual(db.query(conn, "SELECT * FROM users"), [])
        self.create("ana")
        self.post(admin, "/admin/users", username="ANA", password="otra-clave-larga", role="editor")
        with db.connect() as conn:
            self.assertEqual(len(db.query(conn, "SELECT * FROM users")), 1)  # sin duplicados

    def test_cambiar_contrasena_propia(self):
        self.create("ana")
        c, _ = self.login_as("ana")
        r = self.post(c, "/account", current_password="incorrecta", new_password="nueva-clave-99", again="nueva-clave-99")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.login_as("ana", "nueva-clave-99")[0].get("/").status_code, 302)  # no cambió
        self.post(c, "/account", current_password="clave-larga-1", new_password="nueva-clave-99", again="distinta-99999")
        self.assertEqual(self.login_as("ana", "nueva-clave-99")[0].get("/").status_code, 302)
        self.post(c, "/account", current_password="clave-larga-1", new_password="nueva-clave-99", again="nueva-clave-99")
        self.assertEqual(self.login_as("ana", "nueva-clave-99")[0].get("/").status_code, 200)
        self.assertEqual(self.login_as("ana", "clave-larga-1")[0].get("/").status_code, 302)

    def test_cuenta_integrada_no_cambia_contrasena_desde_el_panel(self):
        self.login()
        self.assertIn("ADMIN_PASSWORD", self.client.get("/account").get_data(as_text=True))

    def test_usuarios_sin_csrf_400(self):
        self.login()
        self.assertEqual(self.client.post("/admin/users", data={"username": "ana"}).status_code, 400)
        self.assertEqual(self.client.post("/admin/schedule/slots", data={}).status_code, 400)

    def test_sesion_antigua_sin_usuario_no_vale(self):
        with self.client.session_transaction() as s:
            s["auth"] = True  # formato de sesión anterior a los usuarios
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_quien_aprueba_queda_registrado(self):
        self.create("ana")
        pid = self.draft()
        c, _ = self.login_as("ana")
        c.get("/")
        with c.session_transaction() as s:
            token = s["csrf"]
        c.post(f"/post/{pid}/approve", data={"csrf": token, "confirm": "on"})
        self.assertEqual(self.status(pid)["status"], "approved")
        with db.connect() as conn:
            self.assertEqual(db.one(conn, "SELECT approved_by FROM posts WHERE id = %s", (pid,))["approved_by"], "ana")
        self.assertIn("Aprobado por ana", c.get(f"/post/{pid}").get_data(as_text=True))


class ScheduleAdminTests(Base):
    """Huecos de publicación editables desde el panel."""

    def setUp(self):
        super().setUp()
        schedule.SCHEDULE_FILE = self._schedule_file  # el de verdad: sirve de programación inicial

    def slots(self):
        with db.connect() as conn:
            return [(r["weekday"], r["slot_time"], r["kind"]) for r in db.query(
                conn, "SELECT * FROM schedule_slots ORDER BY weekday, slot_time, kind")]

    def act(self, path, **data):
        self.login()
        return self.client.post(path, data={"csrf": self.csrf(), **data})

    def test_primera_carga_copia_schedule_txt(self):
        self.login()
        html = self.client.get("/admin/schedule").get_data(as_text=True)
        self.assertEqual(self.slots(), [(1, "15:30", "carrusel"), (3, "19:00", "historia"), (3, "19:00", "publicacion")])
        for text in ("Martes", "15:30", "Jueves", "19:00", "Europe/Madrid"):
            self.assertIn(text, html)

    def test_manda_la_base_de_datos_no_el_archivo(self):
        self.login()
        self.client.get("/admin/schedule")
        bad = os.path.join(_TMP, "ignorado.txt")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("esto ni es un horario\n")
        schedule.SCHEDULE_FILE = bad
        self.assertEqual(self.client.get("/admin/schedule").status_code, 200)
        self.assertEqual(self.tick(MON).get_json()["action"], "idle")

    def test_anadir_y_eliminar_hueco(self):
        self.act("/admin/schedule/slots", day="4", time="9:05", kind="carrusel")
        self.assertIn((4, "09:05", "carrusel"), self.slots())
        self.act("/admin/schedule/slots", day="4", time="09:05", kind="carrusel")  # duplicado
        self.assertEqual(self.slots().count((4, "09:05", "carrusel")), 1)
        with db.connect() as conn:
            sid = db.one(conn, "SELECT id FROM schedule_slots WHERE weekday = 4")["id"]
        self.act(f"/admin/schedule/slots/{sid}/delete")
        self.assertNotIn((4, "09:05", "carrusel"), self.slots())

    def test_rechaza_huecos_no_validos(self):
        self.login()
        self.client.get("/admin/schedule")  # carga inicial
        before = self.slots()
        self.assertEqual(len(before), 3)
        for day, time_, kind in (("9", "10:00", "carrusel"), ("x", "10:00", "carrusel"), ("1", "25:00", "carrusel"),
                                 ("1", "10:99", "carrusel"), ("1", "", "carrusel"), ("1", "10:00", "reel")):
            self.act("/admin/schedule/slots", day=day, time=time_, kind=kind)
        self.assertEqual(self.slots(), before)

    def test_el_hueco_nuevo_publica_en_el_tick(self):
        pid = self.draft("carrusel")
        self.approve(pid)
        self.act("/admin/schedule/slots", day="2", time="12:00", kind="carrusel")  # miércoles 12:00
        instagram.publish = lambda urls, caption, user_id, token, **kw: {
            "media_id": "1", "permalink": "https://www.instagram.com/p/A/"}
        # creado a las 10:05 UTC, cuando las 12:00 de Madrid (10:00 UTC) ya habían pasado: no cuenta
        with db.connect() as conn:
            db.execute(conn, "UPDATE schedule_slots SET created_at = '2026-09-23T10:05:00+00:00' WHERE weekday = 2")
        self.assertEqual(self.tick("2026-09-23T10:10:00+00:00").get_json()["action"], "idle")
        with db.connect() as conn:
            db.execute(conn, "UPDATE schedule_slots SET created_at = '2026-09-22T09:00:00+00:00' WHERE weekday = 2")
        r = self.tick("2026-09-23T10:10:00+00:00").get_json()  # creado el día anterior: sí
        self.assertEqual(r["action"], "publishing")
        self.assertEqual(r["posts"][0]["kind"], "carrusel")

    def test_hueco_recien_creado_no_publica_una_hora_pasada(self):
        cfg = schedule.build("Europe/Madrid", 120, [
            {"weekday": 1, "slot_time": "15:30", "kind": "carrusel", "created_at": "2026-09-22T13:40:00+00:00"}])
        self.assertEqual(cfg.due_slots(at(TUE_LATER)), {})  # las 15:30 ya pasaron cuando se creó el hueco
        self.assertEqual(cfg.upcoming(at(TUE_LATER), None, 1, "carrusel"), [at("2026-09-29T13:30:00+00:00")])

    def test_eliminar_un_hueco_deja_de_publicar_ahi(self):
        pid = self.draft("carrusel")
        self.approve(pid)
        with db.connect() as conn:
            sid = db.one(conn, "SELECT id FROM schedule_slots WHERE kind = 'carrusel'")["id"]
        self.act(f"/admin/schedule/slots/{sid}/delete")
        self.assertEqual(self.tick(TUE_SLOT).get_json()["action"], "idle")
        self.assertIn("sin ningún hueco en la programación", self.client.get("/").get_data(as_text=True))

    def test_sin_ningun_hueco_no_falla(self):
        with db.connect() as conn:
            db.execute(conn, "DELETE FROM schedule_slots")
            db.kv_set(conn, "schedule_seeded", db.now())
            db.kv_set(conn, "schedule_tz", "Europe/Madrid")
            db.kv_set(conn, "schedule_tolerance", "120")
        self.login()
        self.assertIn("No hay ningún hueco", self.client.get("/admin/schedule").get_data(as_text=True))
        self.assertEqual(self.tick(TUE_SLOT).get_json()["action"], "idle")
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.slots(), [])  # no se vuelve a copiar schedule.txt

    def test_ajustes_zona_y_tolerancia(self):
        self.act("/admin/schedule/settings", tz="America/Bogota", tolerance="60")
        with db.connect() as conn:
            self.assertEqual(db.kv_get(conn, "schedule_tz"), "America/Bogota")
            self.assertEqual(db.kv_get(conn, "schedule_tolerance"), "60")
        # 15:30 en Bogotá (UTC-5) = 20:30 UTC
        self.assertEqual(self.tick("2026-09-22T13:30:00+00:00").get_json()["action"], "idle")  # ya no es la hora
        self.assertEqual(self.tick("2026-09-22T20:30:00+00:00").get_json()["action"], "empty-queue")
        for tz, tol in (("Marte/Olimpo", "60"), ("Europe/Madrid", "5"), ("Europe/Madrid", "99999"), ("Europe/Madrid", "abc")):
            self.act("/admin/schedule/settings", tz=tz, tolerance=tol)
        with db.connect() as conn:
            self.assertEqual(db.kv_get(conn, "schedule_tz"), "America/Bogota")
            self.assertEqual(db.kv_get(conn, "schedule_tolerance"), "60")


class TokenTests(Base):
    def test_renueva_y_guarda(self):
        instagram.refresh = lambda token: ("TOKEN-NUEVO", 5184000)
        with db.connect() as conn:
            server.maybe_refresh_token(conn)
            self.assertEqual(server.get_token(conn), "TOKEN-NUEVO")

    def test_token_nuevo_del_entorno_manda_sobre_el_guardado(self):
        instagram.refresh = lambda token: ("TOKEN-RENOVADO", 5184000)
        with db.connect() as conn:
            server.maybe_refresh_token(conn)
        os.environ["IG_ACCESS_TOKEN"] = "TOKEN-EXTERNO-NUEVO"
        try:
            with db.connect() as conn:
                self.assertEqual(server.get_token(conn), "TOKEN-EXTERNO-NUEVO")
        finally:
            os.environ["IG_ACCESS_TOKEN"] = "IGAA-TOKEN-SECRETO-DE-PRUEBA"

    def test_fallo_al_renovar_no_rompe(self):
        with db.connect() as conn:
            server.maybe_refresh_token(conn)  # refresh lanza IGError; no debe propagarse
            self.assertEqual(server.get_token(conn), "IGAA-TOKEN-SECRETO-DE-PRUEBA")


class GuardTests(unittest.TestCase):
    def test_prohibidos(self):
        for text in ["Comenta NIVEL y te dejo el link", "COMENTA CLASES y te paso el enlace",
                     "Link en la bio", "enlace en la descripción", "te dejo el link del test",
                     "escríbeme por DM", "Comenta \"TEST\" abajo", "comenta la palabra y recibe el link"]:
            self.assertTrue(guards.check(text), text)

    def test_permitidos(self):
        for text in ["Haz el test gratis de 5 minutos en trabajoenexcel.com.",
                     "Reserva tu clase diagnóstico gratis en trabajoenexcel.com",
                     "TU EQUIPO HACE SPRINTS. Pero no está haciendo Scrum.",
                     "¿Qué te parece? Cuéntanos tu experiencia con Excel."]:
            self.assertFalse(guards.check(text), text)


if __name__ == "__main__":
    unittest.main()
