# STATUS — bitácora de la versión actual

**Versión:** 2 (aprobación + cola + tres tipos de contenido) · **Fecha:** 2026-09-20 · **Último commit:** `4ce02c3`
**Cuenta:** @trabajoenexcel · **Repo:** `JAESCOBARC/IG_RRSS` (público) · **App:** https://ig-rrss.onrender.com

Este archivo es el registro de lo que hay, lo que se ha comprobado de verdad y lo que no. Distingue
**verificado** (probado con evidencia) de **no verificado**. Para reglas de trabajo, ver [`CLAUDE.md`](CLAUDE.md);
para desplegar y operar, [`app/README.md`](app/README.md). No contiene secretos ni claves.

---

## 1. Qué es
Sistema que genera contenido de Instagram cada semana, lo deja como borrador en un panel web para que
lo apruebes tú, y lo publica solo en los huecos que definas. **Las imágenes no se guardan**: se borran
del servidor al publicar (o al rechazar) y del equipo al subirlas.

## 2. Piezas
| Pieza | Dónde vive | Notas |
|---|---|---|
| App de aprobación y publicación (Flask) | Render, plan gratuito (`app/`, `render.yaml`) | Un solo worker; despliegue **manual** (ver §7) |
| Base de datos (borradores, imágenes temporales, token renovado) | Neon (Postgres) | Tablas `posts`, `images`, `kv`, `users`, `schedule_slots`; las migraciones (`kind`, `approved_by`) se aplican al arrancar |
| Programador | GitHub Actions, `.github/workflows/tick.yml` | Avisa a la app cada 30 min; secrets `APP_URL` y `APP_API_KEY` |
| Generación semanal | Rutina de Claude en la nube (lunes 08:02 Madrid) | Sin conectores; entorno «Default» con `IG_APP_URL` + credencial de API |
| Generador de imágenes y reglas de copy | `.claude/skills/carruseles-app/` | Pillow, fuentes incluidas |
| Subida de borradores desde Claude | `scripts/upload_draft.py`, `scripts/pick_urls.py` | Se ejecutan desde local o desde la rutina |
| Horarios | Panel → Programación (base de datos) | `app/schedule.txt` solo es la programación inicial (se copia una vez) |
| Usuarios | Panel → Usuarios (base de datos) | Roles `admin` y `editor`; cuenta integrada `admin` = `ADMIN_PASSWORD` |

## 3. Tipos de contenido
| Tipo | Imágenes | Proporción | Texto de publicación | Contenido |
|---|---|---|---|---|
| `carrusel` | 2–10 (skill: 3–5) | 4:5 a 1,91:1 (1080×1350) | caption + hashtags | Servicios, sobre una URL de `url.txt` |
| `publicacion` | 1 | 4:5 a 1,91:1 (1080×1350) | caption + hashtags | Truco o dato útil de Excel, con la web |
| `historia` | 1 | 9:16 (1080×1920) | **ninguno** (la API no lo admite) | Promoción breve de una URL; se ve 24 h |

La app valida el tipo, el nº de imágenes y la proporción al subir el borrador.

## 4. Programación inicial (`app/schedule.txt`, editable desde el panel)
Se copia a la base de datos al primer arranque; desde entonces se cambia en el panel. Zona `Europe/Madrid` (cambio verano/invierno automático), tolerancia 120 min.
- Martes **15:30** → `carrusel`
- Jueves **19:00** → `publicacion` y `historia` (salen juntas)

Reglas: un post por hueco y tipo (el aprobado más antiguo de ese tipo); si a esa hora no hay ninguno
aprobado, el hueco **se pierde**; el aviso de GitHub llega cada 30 min, así que un post puede salir
hasta ~30 min tarde. Aprobar = ponerlo en cola; **Claude nunca aprueba ni publica**.

## 5. Reglas de negocio y seguridad
- **CTA prohibido** en slides y captions: «Comenta X y te dejo el link», «link en la bio/descripción», «por DM».
  El CTA nombra la web con una acción concreta. Lo aplican la skill **y** el servidor (`app/guards.py`), al subir y al aprobar.
- **Sin imágenes almacenadas**: fuera de git (repo público), borradas del servidor tras publicar/rechazar y del equipo tras subir.
- **Sin secretos en el repo**: variables de Render, `.env` local (ignorado) y «credencial de API» del entorno de la rutina.
- Las imágenes solo son públicas mientras el post está en «Publicando» (Instagram las descarga entonces).
- Un post `failed` no se reintenta a ciegas (podría haberse publicado).
- Panel con usuarios (contraseñas cifradas con hash), sesión con cookie firmada, protección CSRF y límite de intentos de login por IP; la API exige clave.
- Roles: `editor` aprueba/rechaza; `admin` además gestiona usuarios y programación. El acceso se comprueba en cada petición: borrar un usuario corta su sesión al instante.

## 6. Verificado (con evidencia)
**Pruebas automáticas:** 72 pruebas (`cd app && python -m unittest`) con SQLite e Instagram simulado: seguridad, restricción de CTA,
cola FIFO por tipo, un post por hueco, varios tipos en el mismo hueco, horario de verano/invierno, huecos perdidos, tolerancia,
borrado de imágenes, ocultación de credenciales en errores, renovación de token y migración de una base sin la columna `kind`; usuarios (alta, baja con corte de sesión al instante, roles, contraseñas) y programación editable (alta/baja de huecos, validaciones, huecos nuevos sin efecto retroactivo, zona y tolerancia).

**En producción (Render + Neon + GitHub + Instagram real):**
- App en línea: `/healthz` 200, login carga, la API rechaza con 401 sin clave.
- Rutina en la nube → app: genera y sube borradores sin exponer la clave (credencial de API); probado con carruseles y con los tres tipos.
- Programador de GitHub → app: responde `idle` fuera de hueco; con «forzar» publica y el workflow espera al resultado y falla con aviso si algo va mal.
- **Publicaciones reales:** un carrusel (publicado y enlace verificado), y una **historia** (publicada por la API, enlace responde 200).
- Fallo controlado: con un `IG_USER_ID` incorrecto Meta devolvió 400; la app lo marcó `failed`, ocultó las credenciales, conservó las imágenes y no publicó nada. Tras corregir Render, publicó bien.
- Migración de la base de datos (`kind`): aplicada al arrancar la versión nueva (si fallara, el despliegue no habría quedado en línea).
- Borrado de imágenes tras publicar: comprobado (404 en `/media/...`; el panel indica «las imágenes se borraron»).

## 7. No verificado / pendiente
| Punto | Estado |
|---|---|
| Publicación real de una **publicación de una imagen** | Sin probar en Instagram (mismo código que un carrusel simple, validada en local) |
| Primer **hueco programado real** (martes 15:30 / jueves 19:00) | Sin observar: solo se ha probado el programador con «forzar» y en «idle». Hay que vigilar el primero |
| Aspecto de la **historia en el móvil** (márgenes de seguridad de 250 px) | Sin ver; comprobarlo abriendo la historia publicada |
| **Dominios de trabajoenexcel.com bloqueados** en el entorno de la rutina (`EGRESS_BLOCKED`) | Abierto: la rutina no puede leer las páginas y usa los ángulos de `urls.md` (solo 3 de las 7 URLs) |
| **Render no despliega solo** al hacer commit (Auto-Deploy en «On Commit» pero no se dispara) | Abierto: hay que pulsar *Manual Deploy*. Opción: usar el *Deploy Hook* desde un workflow |
| **Token de Instagram** filtrado en el historial público (commit `7dc2497`, por unos secrets cruzados) | Abierto por decisión del usuario; la solución limpia es revocarlo y generar otro |
| PAT de GitHub «IG_RRSS refresh» (sin caducidad) creado para el sistema antiguo | Borrado el secret `GH_PAT`, pero **no verificado** que se haya borrado el token en sí |
| Migración de Postgres probada solo por arranque | Sin consulta directa a Neon; en local se probó con SQLite |
| Límites de los planes gratuitos | Render gratuito: se duerme (~1 min de despertar) y su documentación desaconseja producción; Neon: sin comprobar cuotas |
| GitHub desactiva workflows programados tras 60 días sin actividad | El workflow intenta reactivarse solo; sin verificar |
| **Usuarios y programación editable** (versión 3) | Solo probados en local (SQLite). Sin desplegar ni probar en Render/Neon (Postgres): tras desplegar, comprobar que crea las tablas, que siembra la programación y que el primer hueco real publica |
| Repo dentro de OneDrive | Riesgo de conflictos de sincronización con `.git`; recomendado moverlo fuera |

## 8. Decisiones de diseño (y por qué)
1. **Imágenes fuera de git**: el repo es público y git conservaría los JPG en el historial aunque se borren → la app sirve y borra las imágenes.
2. **La app publica** (no GitHub Actions): así el borrado es real y no hace falta el repo público para servir imágenes a Instagram.
3. **Aprobar = cola, no publicar al instante**: un post por hueco y tipo, con los huecos definidos en el panel.
4. **Cola por tipo, con huecos que pueden compartir hora**: permite publicación e historia juntas el jueves.
5. **Token en Neon, renovado por la app** (cada 20 días al iniciar sesión o publicar); el de Render solo es el inicial.
6. **Clave de la rutina como «credencial de API»**, no como variable de entorno (las variables las ve cualquiera que use el entorno).
7. **Neon + Render gratuitos** para empezar; Vercel descartado (plan gratuito solo no comercial y exigía reescribir la publicación en segundo plano).
8. **Un carrusel, una publicación y una historia por semana**; los tres se generan el lunes, sortean URLs con un script y no repiten temas recientes.

## 9. Incidentes y lecciones
- Los secrets `IG_ACCESS_TOKEN` e `IG_USER_ID` se guardaron cruzados; el error de la API con el token dentro se escribió en un `meta.yaml` público. Lección: los errores se redactan en la app (`redact`) y se revisan antes de subir.
- `git add -A` subió por error `.claude/settings.json` (permisos locales). Sacado del repo y añadido a `.gitignore`.
- El auto-despliegue de Render no se dispara; se detectó porque la versión en línea no cambiaba (se comprobó con un archivo estático público).
- El mismo `IG_USER_ID` mal copiado en Render hizo fallar la primera publicación real: de ahí el aviso de mirar el perfil antes de reintentar.
- La tanda semanal del 2026-09-22 dio un atajo de Excel en inglés (Ctrl+E para Relleno rápido) en vez del de la versión en español (Ctrl+Mayús+E); el usuario lo corrigió tras verlo en el panel. Lección: los atajos con Ctrl+letra no siempre coinciden entre idiomas; ahora se verifican contra `.claude/skills/carruseles-app/references/trucos-excel.md` antes de darlos por buenos.

## 10. Operación (semana tipo)
1. **Lunes ~08:02 (Madrid):** la rutina sube 3 borradores (carrusel, publicación, historia). Recibes el resumen con los enlaces.
2. **Antes del martes 15:30 / jueves 19:00:** revisas en el panel y aprobáis. Lo no aprobado a tiempo espera al siguiente hueco de su tipo.
3. **En cada hueco:** la app publica y borra las imágenes. Si algo falla, el workflow termina en rojo (correo de GitHub) y el panel muestra el error.
4. **Pruebas manuales:** GitHub → Actions → «Programador de publicaciones» → *Run workflow* (`forzar` y `tipo`). Publica ya y de verdad.

## 11. Registro de cambios
| Commit | Cambio |
|---|---|
| `08c90c8`…`d05e397` | Sistema inicial: publicación desde GitHub Actions sobre una carpeta `queue/` (ya retirado) |
| `136860e` | Workflow mensual de renovación del token (ya retirado) |
| `a0d5306` | App de aprobación, cola, programador y skill de carruseles |
| `1ba4d5c` | El programador se salta el aviso mientras no tiene sus secrets |
| `252aee4` | Modo «tanda semanal» y listado de posts recientes (para no repetir temas) |
| `ec4232a` | URLs de la tanda sorteadas al azar desde `url.txt` |
| `2522397` | La rutina usa una credencial de API en lugar de la clave como variable |
| `43bc838` | Retirado el sistema antiguo (`queue/`, `publish.py`, workflows viejos) |
| `0863b58` | `.claude/settings.json` deja de versionarse |
| `4ce02c3` | **Tres tipos** (carrusel, publicación, historia), horarios por tipo, generador `--format`, migración de la BD |
