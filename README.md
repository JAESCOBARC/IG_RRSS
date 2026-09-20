# IG_RRSS

Carruseles de Instagram para **@trabajoenexcel**: se generan solos cada semana, los revisas y
apruebas en un panel web, y se publican en los huecos que definas. Las imágenes no se guardan:
se borran al publicar.

```
Rutina de Claude (lunes)  ──▶  3 borradores  ──▶  Panel web (Render + Neon)
                                                        │  tú: revisar y aprobar
GitHub Actions (cada 30 min)  ──▶  ¿hueco de schedule.txt?  ──▶  Instagram  ──▶  borra los JPG
```

## Piezas
| Qué | Dónde |
|---|---|
| App de aprobación y publicación (Flask) | [`app/`](app/README.md) |
| Horarios de publicación (martes 15:30, jueves 19:00) | [`app/schedule.txt`](app/schedule.txt) |
| Programador (avisa a la app cada 30 min) | [`.github/workflows/tick.yml`](.github/workflows/tick.yml) |
| Despliegue en Render | [`render.yaml`](render.yaml) |
| Generador de carruseles y reglas de copy | [`.claude/skills/carruseles-app/`](.claude/skills/carruseles-app/SKILL.md) |
| Páginas a promocionar | [`url.txt`](url.txt) |
| Subir un borrador a la app | [`scripts/upload_draft.py`](scripts/upload_draft.py) |
| Elegir 3 URLs al azar para la tanda semanal | [`scripts/pick_urls.py`](scripts/pick_urls.py) |

## Uso
1. Cada lunes, la rutina programada de Claude en la nube genera 3 borradores y los sube a la app.
   También puedes pedirle un carrusel a Claude en cualquier momento.
2. Entra en el panel, revisa las slides y el texto, y aprueba los que quieras (2 por semana caben
   en los huecos). Aprueba antes de la hora del hueco.
3. En cada hueco, la app publica el post aprobado más antiguo y borra sus imágenes.

Guía de despliegue, programación y pruebas en producción: [`app/README.md`](app/README.md).
Reglas del proyecto (seguridad, CTAs prohibidos, quién puede publicar): [`CLAUDE.md`](CLAUDE.md).

## Scripts en local
```
pip install -r requirements.txt
python scripts/upload_draft.py --recent          # posts recientes de la app (necesita .env)
python scripts/pick_urls.py 3                    # 3 URLs al azar de url.txt
cd app && python -m unittest -v                  # pruebas de la app
```
El `.env` (ignorado por git) lleva `IG_APP_URL` e `IG_APP_API_KEY`.
