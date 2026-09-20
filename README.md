# ig-publisher

Publica carruseles en Instagram de forma automática, con aprobación previa, usando solo GitHub Actions (gratis) y la *Instagram API with Instagram Login* (no necesita Página de Facebook).

**Flujo:** dejas un post en `queue/` → lo pones en `status: approved` → haces `push` → cada día a las 09:00 UTC el workflow publica los aprobados cuya `scheduled_date` ya llegó y guarda el resultado en `meta.yaml`.

```
queue/
└── 2026-09-25-lanzamiento/
    ├── meta.yaml
    ├── slide-01.jpg
    └── slide-02.jpg
scripts/publish.py      # publicación
scripts/prepare.py      # conversión local PNG -> JPG
.github/workflows/publish.yml
```

## 1. Configuración inicial (una sola vez)

### 1.1 Repositorio
Crea un repositorio **público** en GitHub y sube este proyecto. Es público porque Instagram descarga las imágenes desde una URL pública (`raw.githubusercontent.com`); el contenido se va a publicar de todos modos. **Nunca** metas tokens en el repo: van en Secrets.

### 1.2 App en Meta for Developers
1. Entra en <https://developers.facebook.com/apps> y crea una app de tipo **Business** (o "Otro → Business").
2. Añade el producto **Instagram** y elige **API setup with Instagram login**.
3. En *Generate access tokens* añade tu cuenta de Instagram (Business/Creator) como cuenta de prueba/rol de la app y acéptalo desde Instagram (*Configuración → Sitio web y herramientas → Invitaciones de la app*).
4. Genera el token con el permiso `instagram_business_content_publish` (y `instagram_business_basic`). Guarda el **token** y el **ID de la cuenta de Instagram** que muestra el panel.

### 1.3 Token de larga duración (60 días)
El token del panel dura 1 hora. Cámbialo por uno de 60 días (necesitas el *App Secret* de la app, en *Configuración → Básica*):

```bash
curl -s "https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=APP_SECRET&access_token=TOKEN_CORTO"
```

La respuesta trae `access_token` (el de larga duración) y `expires_in`.

### 1.4 Secrets en GitHub
En el repo: *Settings → Secrets and variables → Actions → New repository secret*:

| Secret | Valor |
|---|---|
| `IG_ACCESS_TOKEN` | el token de larga duración |
| `IG_USER_ID` | el ID de la cuenta de Instagram |

## 2. Publicar un post

1. Crea una carpeta `queue/AAAA-MM-DD-tema/`.
2. Copia dentro `meta.yaml` (mira `queue/2026-01-01-ejemplo/meta.yaml`) y edita `caption`, `hashtags` y `scheduled_date`.
3. Añade las imágenes del carrusel como `slide-01.jpg`, `slide-02.jpg`… (1 imagen = post simple; 2 a 10 = carrusel).
   - Instagram **solo acepta JPEG**. Si tu skill genera PNG, ejecuta antes `pip install pillow` y `python scripts/prepare.py` para convertirlos.
4. Revisa el contenido y cambia `status: draft` → `status: approved`.
5. `git add`, `commit` y `push`. En la primera ejecución diaria a partir de `scheduled_date` se publica.

Para no esperar al cron: pestaña **Actions → Publicar en Instagram → Run workflow**. Marca *dry_run* para solo validar los posts (imágenes, caption, fecha) sin publicar.

### Estados de `meta.yaml`
| Estado | Significado |
|---|---|
| `draft` | En preparación, no se publica |
| `approved` | Listo; se publica al llegar `scheduled_date` |
| `published` | Publicado (el script añade `published_at`, `media_id`, `permalink`) |
| `failed` | Falló (el script añade `error`). **No se reintenta solo**, para evitar duplicados. Revisa el error, corrígelo y vuelve a poner `approved` |

## 3. Renovar el token (cada ~50 días)

El token caduca a los 60 días. Antes de eso (y pasadas 24 h desde que se emitió):

```bash
curl -s "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=TOKEN_ACTUAL"
```

Copia el nuevo `access_token` al secret `IG_ACCESS_TOKEN`. Apunta en tu calendario un recordatorio a los 50 días.

## Prueba en local (sin publicar)

```bash
pip install -r requirements.txt
python scripts/publish.py --dry-run                     # valida los posts aprobados de hoy
python scripts/publish.py --dry-run --today 2026-12-31  # simula otra fecha
```

## Notas y límites
- Instagram permite hasta 100 publicaciones por API cada 24 h; de sobra para este uso.
- GitHub desactiva los workflows programados si el repo lleva 60 días sin actividad; tus propios commits (nuevos posts) mantienen el repo activo; si dejas de subir posts durante meses, reactívalo desde la pestaña Actions.
- Fuera de alcance por ahora: LinkedIn, generación de contenido con IA, renovación automática del token y reintentos automáticos.
