# IG_RRSS

Contenido de Instagram para **@trabajoenexcel** —un carrusel, una publicación de una imagen y
una historia por semana—: se genera solo cada lunes, lo revisas y apruebas en un panel web, y se
publica en los huecos que definas. Las imágenes no se guardan: se borran al publicar.

```
Rutina de Claude (lunes)  ──▶  carrusel + publicación + historia  ──▶  Panel web (Render + Neon)
                                                        │  tú: revisar y aprobar
GitHub Actions (cada 30 min)  ──▶  ¿hueco de la programación?  ──▶  Instagram  ──▶  borra los JPG
```

## Piezas
| Qué | Dónde |
|---|---|
| App de aprobación y publicación (Flask) | [`app/`](app/README.md) |
| Horarios y usuarios | Se editan en el panel (Programación / Usuarios); [`app/schedule.txt`](app/schedule.txt) es solo la programación inicial |
| Programador (avisa a la app cada 30 min) | [`.github/workflows/tick.yml`](.github/workflows/tick.yml) |
| Despliegue en Render | [`render.yaml`](render.yaml) |
| Generador de carruseles y reglas de copy | [`.claude/skills/carruseles-app/`](.claude/skills/carruseles-app/SKILL.md) |
| Páginas a promocionar | [`url.txt`](url.txt) |
| Subir un borrador a la app | [`scripts/upload_draft.py`](scripts/upload_draft.py) |
| Elegir URLs al azar de url.txt para la tanda semanal | [`scripts/pick_urls.py`](scripts/pick_urls.py) |

## Uso
1. Cada lunes, la rutina programada de Claude en la nube genera 3 borradores (un carrusel, una
   publicación de una imagen y una historia) y los sube a la app. También puedes pedirle a Claude
   un carrusel, una publicación o una historia en cualquier momento.
2. Entra en el panel, revisa las imágenes y el texto, y aprueba los que quieras, antes de la hora
   de su hueco.
3. En cada hueco, la app publica el post aprobado más antiguo de ese tipo y borra sus imágenes.

Guía de despliegue, programación y pruebas en producción: [`app/README.md`](app/README.md).
Reglas del proyecto (seguridad, CTAs prohibidos, quién puede publicar): [`CLAUDE.md`](CLAUDE.md).
Estado, pruebas realizadas y pendientes: [`STATUS.md`](STATUS.md).

## Scripts en local
```
pip install -r requirements.txt
python scripts/upload_draft.py --recent          # posts recientes de la app (necesita .env)
python scripts/pick_urls.py 3                    # 3 URLs al azar de url.txt
cd app && python -m unittest -v                  # pruebas de la app
```
El `.env` (ignorado por git) lleva `IG_APP_URL` e `IG_APP_API_KEY`.
