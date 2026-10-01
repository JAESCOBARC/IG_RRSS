# Guía de estilo — Instagram trabajoenexcel.com

## Patrón visual: «dark editorial»
Casi todo es tipografía y un solo color de acento. Titular gigante en Black con tracking
apretado (-2 %) e interlínea ~0,98, alineado a la izquierda; una frase de acento en lima;
párrafo opcional en gris; botones en píldora (CTA relleno + web con contorno). Sin iconos,
fotos, degradados ni sombras. Lo genera `scripts/carousel_gen.py`; no hay que elegir el tema
salvo con `"theme"`.

## Paleta
| Rol | Hex |
|---|---|
| Fondo negro | `#0A0A0A` |
| Fondo verde tinta | `#1A2410` |
| Fondo / acento lima | `#D4FF3F` |
| Texto principal | `#F5F5F5` |
| Texto secundario | `#C7C7C7` |
| Borde de píldora | `#5F5F5F` |

El lima se usa poco: la frase de acento y el botón. Aprox. de una referencia de diseño del
usuario (hero oscuro con acento lima), medida en píxeles.

## Fondos por formato
- **carrusel** (1080x1350): portada y CTA final en negro; intermedias alternando tinta (slides
  2, 4…) y negro (3, 5…). `"theme": "lima"` en una slide intermedia da un golpe de ritmo (máx. 1-2).
- **publicacion** (1080x1350): negro.
- **historia** (1080x1920): lima con texto negro; la frase de acento va en blanco sobre píldora negra. (Se probó
  verde tinta, pero se prefirió mantener el fondo lima.)
  Márgenes de seguridad: Instagram tapa ~250 px arriba y abajo; cabecera en y=300 y botones
  por encima de y≈1620. Una sola imagen sin caption: debe leerse en segundos.

## Tipografía
`assets/fonts/InterTight-Variable.ttf` (Inter Tight, licencia OFL). Titular Black (900),
párrafo Regular (400), botones y marca SemiBold (600). El tamaño del titular se ajusta solo
(168-84 px) para llenar el espacio; si ni a 84 px cabe, el script avisa con
«⚠ POSIBLE OVERFLOW» y hay que acortar el copy.

## Copy
- **Ortografía:** cada frase, línea de titular y botón empieza por mayúscula; sin erratas ni tildes
  que falten; `¿?`/`¡!` completos; espacio duro antes de `%` (`20\u00a0%`). Se revisa antes de subir (SKILL.md, paso 5).
- Frase completa con punto final, en minúsculas normales (no mayúsculas). Tono afirmativo.
- `runs`: `"bold"` = titular blanco; `"italic"` = frase de acento (ya no es cursiva).
- `body` (opcional): 1-2 líneas de apoyo en gris.
- `cta_text` (≤ 28 caracteres): «Haz el test gratis»; la píldora añade la flecha y al lado la web.
- 3-5 slides por carrusel; una idea por slide; slide 1 = hook específico; última = CTA con
  acción concreta + trabajoenexcel.com (nunca «sígueme» ni «comenta X»; ver `urls.md`).
- Sin saltos de línea a mano: el script hace el wrap midiendo la fuente real.
