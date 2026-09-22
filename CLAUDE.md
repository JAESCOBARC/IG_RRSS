# IG_RRSS — contenido de Instagram con aprobación

Genera contenido para **@trabajoenexcel** (promociona trabajoenexcel.com) en tres tipos:
**carrusel**, **publicación de una imagen** e **historia** (una imagen 9:16, sin texto de
publicación). Lo sube como borrador a una app web de aprobación y, cuando el usuario los aprueba
allí, se publican en Instagram. Repo: `JAESCOBARC/IG_RRSS` (**público**).

## Cómo funciona
1. Claude genera las imágenes (JPG) y el texto **en un directorio temporal** con la
   skill `carruseles-app` (`--format carrusel|publicacion|historia`) y ejecuta
   `scripts/upload_draft.py`.
2. La app (`app/`, Flask, desplegada en Render; blueprint en `render.yaml`) guarda
   el borrador en Postgres (Neon) y lo muestra en un panel con usuarios y contraseña: slides,
   caption y hashtags, con botones «Aprobar y poner en cola» / «Rechazar».
3. Al aprobar, el post pasa a la **cola**. Un cron externo (cron-job.org, cada 5 min — fiable;
   ver `app/README.md` §4) avisa a la app en `/api/cron/tick`; un workflow de GitHub
   (`tick.yml`) hace lo mismo de **respaldo** (~cada 30 min, pero puede retrasarse horas: los
   `schedule` de GitHub Actions no son fiables por sí solos, de ahí el cron externo) y además
   es el que usa el usuario para las pruebas manuales con «forzar» y el que avisa por correo si
   una publicación falla. En cada hueco de la programación del panel (`app/schedule.txt` es solo
   la inicial) —cada hueco es «día hora tipo»: carrusel el martes 15:30; publicación e historia
   el jueves 19:00, hora de España peninsular—, **la app publica el post más antiguo de la cola
   de ese tipo** (sirviendo ella misma las imágenes por una URL pública, solo mientras dura la
   publicación) y **borra los JPG**. Solo conserva título, texto, estado y enlace. Si en un
   hueco no hay nada aprobado de ese tipo, ese hueco se pierde. Reclamar un hueco es atómico:
   aunque los dos avisos lleguen casi a la vez, nunca se publica dos veces.
4. El token de Instagram se renueva solo (al iniciar sesión o publicar, cada
   20 días) y se guarda en la base de datos.

Las imágenes **nunca pasan por git**: el repo es público y git conservaría los
JPG en el historial aunque se borren.

## Crear posts
Usa la skill **`carruseles-app`** (`.claude/skills/carruseles-app/`) siempre que
se pida un carrusel, una publicación, una historia o un post. Las URLs a promocionar están en `url.txt`; los
ángulos verificados de cada una, en `references/urls.md` de la skill.
**Cada lunes** una rutina programada de Claude en la nube genera la **tanda semanal**
(3 borradores, uno de cada tipo: un **carrusel** de servicios, una **publicación de una
imagen** con un truco de Excel y una **historia** con una promoción breve; las URLs se
sortean de `url.txt` con `scripts/pick_urls.py` y no se repiten temas recientes; ver
«Tanda semanal» en la skill). El usuario los aprueba antes de sus huecos (el carrusel,
antes del martes 15:30; la publicación y la historia, antes del jueves 19:00). La skill
termina subiendo el borrador y dándole al usuario el enlace del panel.

## Reglas
- **CTA prohibido:** nunca crear ni publicar slides o captions del tipo «Comenta X
  y te dejo el link», «link en la bio/descripción» ni «escríbeme por DM». El CTA
  nombra la web (trabajoenexcel.com) con una acción concreta. El servidor
  (`app/guards.py`) también lo rechaza.
- **El tema sale de las URLs de `url.txt`**.
- **Claude no publica ni aprueba:** publicar es una acción sobre una cuenta real y
  la autoriza el usuario en el panel. Claude solo sube borradores. Tampoco lanza el
  workflow con «forzar» (publica fuera de hueco, y admite elegir el tipo): es solo una prueba manual del usuario.
- **Horarios:** solo los de la programación de la app, que edita el usuario (administrador) en el panel
  (**Programación**). `app/schedule.txt` solo se lee la primera vez, para sembrar la base de datos. Claude
  no cambia horarios ni usuarios.
- **Un post `failed` no se reintenta a ciegas**: puede haberse publicado ya.
  Se comprueba el perfil antes de reabrirlo.
- **No se guardan imágenes:** ni en el repo, ni en el servidor tras publicar, ni en
  local tras subir el borrador. Generar siempre en el directorio temporal.
- **El repo es público: nunca** escribir tokens, API keys, contraseñas ni ficheros
  con secretos dentro de la carpeta. Los secretos viven en las variables de
  entorno de Render, en `.env` local (ignorado por git) y, para la rutina de la nube, en
  las «credenciales de API» de su entorno (no como variable de entorno: esas las ve
  cualquiera que use el entorno). No se pegan en el chat.
- Máximo 2200 caracteres de caption y 30 hashtags (la skill usa 3-6). **Las historias no
  llevan caption ni hashtags** (la API no los admite): todo el mensaje va en la imagen.
- **Tipos e imágenes:** carrusel 2-10 imágenes y publicación/historia 1 sola; feed 4:5
  (1080x1350) e historia 9:16 (1080x1920). La app rechaza lo que no cumpla.
- Commits: mensaje corto en inglés, como los existentes.

## Comandos
- Pruebas de la app: `cd app && python -m unittest -v` (SQLite + Instagram simulado).
- Arrancar la app en local: `cd app && APP_ENV=dev ADMIN_PASSWORD=x API_KEY=y python server.py`.
- Guía de despliegue, programación y pruebas en producción: `app/README.md`.

## Estado y datos fijos
- **Bitácora de la versión actual:** [`STATUS.md`](STATUS.md) (qué está verificado, qué no, decisiones
  y cambios). Actualizarla tras cada cambio relevante o prueba en producción.
- Cuenta de Instagram: **trabajoenexcel** (ID de cuenta `17841443221425746`, no
  es secreto). App de Meta: «Carruseles y Post».
- Pendiente conocido: un token anterior quedó visible en el commit `7dc2497`
  (por haber cruzado los secrets). Sin revocar por decisión del usuario.
