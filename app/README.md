# App de aprobación

Panel web para revisar el contenido generado (**carruseles, publicaciones de una imagen e
historias**), autorizarlo y publicarlo en Instagram **en los huecos que definas**
(se configuran desde el panel). Al publicar, la app **borra
los JPG**; solo conserva el texto, el estado y el enlace del post.

```
Claude ──(scripts/upload_draft.py)──▶ borrador ──▶ Neon (Postgres)
                                                       │
tú y tu equipo ──▶ panel (usuario y contraseña) ──▶ «Aprobar y poner en cola» │
                                                       ▼
GitHub Actions (cada 30 min) ──▶ /api/cron/tick ──▶ ¿hueco de la programación? ──▶ Instagram ──▶ borra los JPG
```

## Usuarios
El panel es multiusuario. Un **administrador** crea y elimina cuentas en **Usuarios** (menú superior):
- **Editor**: entra al panel y aprueba o rechaza posts.
- **Administrador**: lo mismo, más gestionar usuarios y la programación.
- La cuenta integrada **`admin`** usa la variable `ADMIN_PASSWORD` de Render. No se puede eliminar ni
  cambiar desde el panel y sirve de recuperación si te quedas sin acceso.
- Eliminar un usuario le quita el acceso **al instante** (aunque tenga la sesión abierta).
- Cada persona cambia su contraseña en su cuenta (pulsa su nombre arriba). No hay «olvidé mi contraseña»:
  el administrador borra la cuenta y la crea de nuevo.
- Los posts aprobados guardan quién los aprobó.

## Programación
Se edita en el panel (**Programación**, solo administradores): añadir o eliminar huecos «día, hora, tipo»,
la zona horaria y la tolerancia. Los cambios valen desde el siguiente aviso del programador, sin redesplegar.

`schedule.txt` solo es la **programación inicial**: se copia a la base de datos la primera vez que arranca
la app, y a partir de ahí manda la base de datos (editar el archivo ya no cambia nada). Formato:
```
zona: Europe/Madrid
tolerancia_minutos: 120
martes 15:30 carrusel
jueves 19:00 publicacion
jueves 19:00 historia
```
- Cada hueco es **«día hora tipo»** con tipo `carrusel`, `publicacion` o `historia`. Dos huecos a la
  misma hora con tipos distintos salen juntos.
- Un post por hueco: el **más antiguo de la cola de ese tipo** (orden de aprobación).
- Si a esa hora no hay ninguno aprobado de ese tipo, el hueco **se pierde**: aprueba antes de la hora.
- Un tipo sin ningún hueco no se publica nunca; el panel lo avisa.
- Un hueco recién creado solo cuenta a partir de ese momento: si añades «hoy 10:00» a las 11:00, no publica a posteriori.
- Horas de España peninsular, con cambio verano/invierno automático.
- El aviso de GitHub llega cada 30 min y puede retrasarse unos minutos: un post sale
  como mucho ~30 min después de la hora del hueco (`tolerancia_minutos` es el margen
  máximo de retraso admitido).

## Despliegue paso a paso

### 1. Base de datos gratuita (Neon)
1. <https://neon.tech> → crea cuenta → **Create project** (nombre `ig-rrss`; región
   cercana a la de Render, p. ej. Frankfurt).
2. En el panel del proyecto pulsa **Connect** y copia la **connection string**
   (`postgresql://usuario:clave@ep-….neon.tech/neondb?sslmode=require`). Es tu `DATABASE_URL`.
   Las tablas se crean solas al arrancar la app.

### 2. Servicio en Render
1. <https://dashboard.render.com> → **New + → Blueprint** → conecta GitHub y elige `IG_RRSS`.
   Render lee `render.yaml` (plan gratuito, carpeta `app/`).
2. Rellena las variables que pide (`sync: false`):

| Variable | Valor |
|---|---|
| `DATABASE_URL` | la connection string de Neon |
| `ADMIN_PASSWORD` | la contraseña de la cuenta integrada `admin` del panel (larga y única) |
| `IG_USER_ID` | `17841443221425746` |
| `IG_ACCESS_TOKEN` | el token de Instagram de larga duración |

   `SECRET_KEY` y `API_KEY` las genera Render.
3. **Apply**. Cuando termine (unos minutos), abre `https://<tu-servicio>.onrender.com/healthz`
   (debe decir `ok`) y luego la raíz para iniciar sesión.

### 3. Conectar tu equipo (para que Claude suba borradores)
En Render → tu servicio → **Environment**, copia el valor de `API_KEY`. En la raíz del
repo crea `.env` (está en `.gitignore`):
```
IG_APP_URL=https://<tu-servicio>.onrender.com
IG_APP_API_KEY=<valor de API_KEY>
```

### 4. Conectar el programador (GitHub Actions)
Crea los dos secrets del repo (te pide el valor de cada uno):
```
gh secret set APP_URL --repo JAESCOBARC/IG_RRSS          # https://<tu-servicio>.onrender.com
gh secret set APP_API_KEY --repo JAESCOBARC/IG_RRSS      # el mismo valor de API_KEY
```
El workflow **Programador de publicaciones** empezará a avisar cada 30 min.

## Probar en producción
1. **Salud:** `/healthz` responde `ok`; el login funciona.
2. **Borrador:** pídele a Claude un carrusel. Debe aparecer en «Por aprobar» con las
   slides y el texto.
3. **Cola:** ábrelo, marca la casilla y pulsa **Aprobar y poner en cola**. Pasa a «En cola»
   con la hora prevista («Sale: martes 22 sep, 15:30»).
4. **Programador sin publicar:** GitHub → Actions → *Programador de publicaciones* →
   **Run workflow** (sin marcar «forzar»). Fuera de un hueco responde `idle` y no publica.
   En el panel, el pie muestra «Último aviso del programador».
5. **Publicación real (una vez por tipo):** repite *Run workflow* marcando **forzar** y, si
   quieres, eligiendo el **tipo**. Publica YA el post aprobado más antiguo de ese tipo (o de
   cualquiera) en @trabajoenexcel: usa uno que quieras publicar de verdad. Prueba el carrusel, la
   publicación y la historia por separado. El workflow espera al resultado y falla (con correo de GitHub) si algo va mal.
6. **Verificar:** el post pasa a «Publicado» con el enlace a Instagram, y su página indica
   «Las imágenes se borraron del servidor tras publicar».
7. **Programación normal:** a partir de ahí, lo aprobado sale solo en cada hueco.

**Tipos y reglas de imagen** (la app las valida al subir):

| Tipo | Imágenes | Proporción | Texto de publicación |
|---|---|---|---|
| Carrusel | 2-10 | 4:5 a 1,91:1 (p. ej. 1080x1350) | caption + hashtags |
| Publicación | 1 | 4:5 a 1,91:1 (p. ej. 1080x1350) | caption + hashtags |
| Historia | 1 | 9:16 (1080x1920) | ninguno (la API no lo admite) |

Estados: **Por aprobar**, **En cola**, **Publicando**, **Publicado**, **Falló** (con el error;
comprueba en Instagram que no se publicó antes de reabrirlo) y **Rechazado**.

## Cosas a saber
- **Plan gratuito de Render:** se duerme tras ~15 min sin uso y tarda ~1 min en despertar.
  Los avisos cada 30 min lo despiertan y el workflow reintenta mientras arranca.
- **Imágenes:** solo se pueden ver sin iniciar sesión mientras el post está en
  «Publicando» (Instagram las descarga entonces). En cola o como borrador, solo con sesión.
- **Aviso del programador:** si no llega ninguno en 2 h y hay posts en cola, el panel
  muestra un aviso rojo. GitHub desactiva los workflows programados tras 60 días sin
  actividad en el repo; el propio workflow intenta reactivarse cada vez. Si aun así se
  parara, se reactiva en la pestaña Actions.
- **Token de Instagram:** el de `IG_ACCESS_TOKEN` es el inicial; la app lo renueva sola
  (cada 20 días, al iniciar sesión o publicar) y guarda el nuevo en la base de datos.
  Si lo cambias en Render, el nuevo valor manda.
- **Restricción de contenido:** el servidor rechaza captions/slides con CTAs tipo
  «Comenta X y te dejo el link», «link en la bio» o «por DM» (`guards.py`).
- **Un solo worker** (`--workers 1`): el estado de «publicando» y el límite de
  intentos de login están en memoria.

## Desarrollo local
```
pip install -r requirements.txt
python -m unittest -v                                        # pruebas (SQLite + Instagram simulado)
APP_ENV=dev ADMIN_PASSWORD=x API_KEY=y python server.py      # http://localhost:5000
```
Sin `DATABASE_URL` usa SQLite (`local.db`). En local no se puede publicar de verdad:
Instagram necesita una URL pública para descargar las imágenes.
