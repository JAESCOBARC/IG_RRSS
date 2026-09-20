# IG_RRSS — carruseles de Instagram con aprobación

Genera carruseles para **@trabajoenexcel** (promocionan trabajoenexcel.com), los
sube como borrador a una app web de aprobación y, cuando el usuario los aprueba
allí, se publican en Instagram. Repo: `JAESCOBARC/IG_RRSS` (**público**).

## Cómo funciona
1. Claude genera las slides (JPG) y el texto **en un directorio temporal** con la
   skill `carruseles-app` y ejecuta `scripts/upload_draft.py`.
2. La app (`app/`, Flask, desplegada en Render; blueprint en `render.yaml`) guarda
   el borrador en Postgres (Neon) y lo muestra en un panel con contraseña: slides,
   caption y hashtags, con botones «Aprobar y poner en cola» / «Rechazar».
3. Al aprobar, el post pasa a la **cola**. Un workflow (`tick.yml`) avisa a la app
   cada 30 min y, en cada hueco de `app/schedule.txt` (martes 15:30 y jueves 19:00,
   hora de España peninsular), **la app publica el post más antiguo de la cola**
   (sirviendo ella misma las imágenes por una URL pública, solo mientras dura la
   publicación) y **borra los JPG**. Solo conserva título, texto, estado y enlace.
   Si en un hueco no hay nada aprobado, ese hueco se pierde.
4. El token de Instagram se renueva solo (al iniciar sesión o publicar, cada
   20 días) y se guarda en la base de datos.

Las imágenes **nunca pasan por git**: el repo es público y git conservaría los
JPG en el historial aunque se borren.

## Crear posts
Usa la skill **`carruseles-app`** (`.claude/skills/carruseles-app/`) siempre que
se pida un carrusel o un post. Las URLs a promocionar están en `url.txt`; los
ángulos verificados de cada una, en `references/urls.md` de la skill. La skill
termina subiendo el borrador y dándole al usuario el enlace del panel.

## Reglas
- **CTA prohibido:** nunca crear ni publicar slides o captions del tipo «Comenta X
  y te dejo el link», «link en la bio/descripción» ni «escríbeme por DM». El CTA
  nombra la web (trabajoenexcel.com) con una acción concreta. El servidor
  (`app/guards.py`) también lo rechaza.
- **El tema sale de las URLs de `url.txt`**.
- **Claude no publica ni aprueba:** publicar es una acción sobre una cuenta real y
  la autoriza el usuario en el panel. Claude solo sube borradores. Tampoco lanza el
  workflow con «forzar» (publica fuera de hueco): es solo una prueba manual del usuario.
- **Horarios:** solo los de `app/schedule.txt`. Para cambiarlos se edita ese archivo.
- **Un post `failed` no se reintenta a ciegas**: puede haberse publicado ya.
  Se comprueba el perfil antes de reabrirlo.
- **No se guardan imágenes:** ni en el repo, ni en el servidor tras publicar, ni en
  local tras subir el borrador. Generar siempre en el directorio temporal.
- **El repo es público: nunca** escribir tokens, API keys, contraseñas ni ficheros
  con secretos dentro de la carpeta. Los secretos viven en las variables de
  entorno de Render y en `.env` local (ignorado por git), y no se pegan en el chat.
- Máximo 2200 caracteres de caption y 30 hashtags (la skill usa 3-6).
- Commits: mensaje corto en inglés, como los existentes.

## Comandos
- Pruebas de la app: `cd app && python -m unittest -v` (SQLite + Instagram simulado).
- Arrancar la app en local: `cd app && APP_ENV=dev ADMIN_PASSWORD=x API_KEY=y python server.py`.
- Guía de despliegue, programación y pruebas en producción: `app/README.md`.

## Estado y datos fijos
- Cuenta de Instagram: **trabajoenexcel** (ID de cuenta `17841443221425746`, no
  es secreto). App de Meta: «Carruseles y Post».
- **Sistema anterior (a retirar tras verificar la app en producción):**
  `queue/`, `scripts/publish.py`, `scripts/prepare.py` y los workflows
  `publish.yml` / `refresh-token.yml` publicaban desde GitHub Actions. Quedan
  hasta confirmar que la app funciona; no usarlos para posts nuevos.
- Pendiente conocido: un token anterior quedó visible en el commit `7dc2497`
  (por haber cruzado los secrets). Sin revocar por decisión del usuario.
