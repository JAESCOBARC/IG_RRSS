"""Pruebas de la app de aprobación (SQLite + Instagram simulado).

Ejecutar desde app/:  python -m unittest -v
"""
import datetime as dt
import io
import json
import os
import tempfile
import time
import unittest

_TMP = tempfile.mkdtemp()
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


def jpeg(color="#F4EFE1") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (108, 135), color).save(buf, "JPEG")
    return buf.getvalue()


def draft_form(**over):
    data = {"title": "Prueba", "caption": "Excel para tu día a día.\nHaz el test gratis en trabajoenexcel.com.",
            "hashtags": json.dumps(["excel", "#productividad"]),
            "slides_text": json.dumps(["TU EQUIPO HACE SPRINTS. Pero no hace Scrum."])}
    data.update(over)
    data["slides"] = [(io.BytesIO(jpeg()), "slide-01.jpg"), (io.BytesIO(jpeg("#2F6B47")), "slide-02.jpg")]
    return data


class Base(unittest.TestCase):
    def setUp(self):
        with db.connect() as conn:
            db.execute(conn, "DELETE FROM images")
            db.execute(conn, "DELETE FROM posts")
            db.execute(conn, "DELETE FROM kv")
        self.client = server.app.test_client()
        self._publish, self._refresh, self._utcnow = instagram.publish, instagram.refresh, server.utcnow
        self._schedule_file = schedule.SCHEDULE_FILE
        instagram.refresh = lambda token: (_ for _ in ()).throw(instagram.IGError("no toca"))

    def tearDown(self):
        instagram.publish, instagram.refresh, server.utcnow = self._publish, self._refresh, self._utcnow
        schedule.SCHEDULE_FILE = self._schedule_file

    # ayudas
    def upload(self, **over):
        return self.client.post("/api/drafts", headers=API, data=draft_form(**over),
                                content_type="multipart/form-data")

    def draft(self, **over) -> str:
        return self.upload(**over).get_json()["id"]

    def login(self, client=None):
        client = client or self.client
        client.get("/login")
        with client.session_transaction() as s:
            token = s["csrf"]
        return client.post("/login", data={"password": "clave-de-prueba", "csrf": token})

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

    def tick(self, when, force=False, headers=API):
        server.utcnow = lambda: at(when)
        return self.client.post("/api/cron/tick" + ("?force=1" if force else ""), headers=headers)

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
        form = draft_form()
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
        self.assertEqual(set(rows[0]), {"id", "title", "status", "source_url", "created_at", "published_at"})
        self.assertEqual(self.client.get("/api/posts?limit=x", headers=API).status_code, 400)

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
        r = c.post("/login", data={"password": "mala", "csrf": token})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.get("/").status_code, 302)
        self.assertEqual(self.login(c).status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)

    def test_login_sin_csrf_400(self):
        self.assertEqual(self.client.post("/login", data={"password": "clave-de-prueba"}).status_code, 400)

    def test_redireccion_next_solo_relativa(self):
        c = server.app.test_client()
        c.get("/login")
        with c.session_transaction() as s:
            token = s["csrf"]
        r = c.post("/login?next=//evil.com", data={"password": "clave-de-prueba", "csrf": token})
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
        self.cfg = schedule.load()

    def test_archivo_por_defecto(self):
        self.assertEqual(self.cfg.tz_name, "Europe/Madrid")
        self.assertEqual([(d, f"{t:%H:%M}") for d, t in self.cfg.slots], [(1, "15:30"), (3, "19:00")])
        self.assertEqual(self.cfg.describe(), "martes 15:30, jueves 19:00")

    def test_hueco_vigente_verano(self):
        self.assertIsNone(self.cfg.due_slot(at("2026-09-22T13:29:00+00:00")))
        self.assertEqual(self.cfg.due_slot(at(TUE_SLOT)), at(TUE_SLOT))
        self.assertEqual(self.cfg.due_slot(at("2026-09-22T15:29:00+00:00")), at(TUE_SLOT))
        self.assertIsNone(self.cfg.due_slot(at(TUE_TOO_LATE)))
        self.assertEqual(self.cfg.due_slot(at(THU_SLOT)), at(THU_SLOT))
        self.assertIsNone(self.cfg.due_slot(at(MON)))

    def test_cambio_de_hora_invierno(self):
        self.assertEqual(self.cfg.due_slot(at(TUE_WINTER)), at(TUE_WINTER))
        self.assertIsNone(self.cfg.due_slot(at("2026-12-01T13:30:00+00:00")))  # 14:30 en Madrid: aún no

    def test_proximos_huecos(self):
        now = at("2026-09-22T10:00:00+00:00")
        got = self.cfg.upcoming(now, None, 3)
        self.assertEqual(got, [at(TUE_SLOT), at(THU_SLOT), at("2026-09-29T13:30:00+00:00")])
        self.assertEqual(self.cfg.upcoming(now, at(TUE_SLOT), 2), [at(THU_SLOT), at("2026-09-29T13:30:00+00:00")])
        self.assertEqual(self.cfg.label(at(TUE_SLOT)), "martes 22 sep, 15:30")

    def test_errores_de_formato(self):
        for text in ["lunes 25:00", "foo 10:00", "martes", "zona: Marte/Olimpo\nmartes 10:00",
                     "tolerancia_minutos: mucha\nmartes 10:00", "# solo comentarios"]:
            with self.assertRaises(schedule.ScheduleError, msg=text):
                schedule.parse(text)

    def test_acentos_y_varios_huecos(self):
        cfg = schedule.parse("miércoles 9:05\nmiercoles 18:00\nsábado 10:00")
        self.assertEqual(len(cfg.slots), 3)


class QueueTests(Base):
    """Aprobar pone en cola; publica el aviso del programador en su hueco."""

    def fake_publish(self, calls=None):
        def fake(urls, caption, user_id, token):
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

        def fake_publish(urls, caption, user_id, token):
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

        def failing(urls, caption, user_id, token):
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
        self.assertIn("martes 15:30, jueves 19:00", html)
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
