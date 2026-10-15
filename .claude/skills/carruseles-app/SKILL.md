---
name: carruseles-app
description: Crea contenido de Instagram (carruseles, publicaciones de una imagen, historias y Reels en vídeo animado de hasta 30 s con música libre) de alto impacto y alcance para conseguir seguidores, promocionando las páginas de trabajoenexcel.com (homepage, profesor-excel-online.html, test-nivel-excel.html), y los sube como borrador a la app de aprobación, donde el usuario los revisa y autoriza su publicación en @trabajoenexcel. Úsala SIEMPRE que el usuario pida "un carrusel", "carrusel de Instagram", "un post", "una historia", "una publicación", "un reel", "un vídeo", "promociona esta URL en Instagram", mencione alcance/seguidores/engagement para trabajoenexcel.com, o pida contenido de Instagram sobre clases de Excel, el profesor particular, o el test de nivel. También úsala si pide ajustar colores, tipografía o número de slides de un carrusel ya generado con esta skill.
---

# Carruseles App — trabajoenexcel.com

Genera contenido de Instagram en JPG (y vídeo MP4 para Reels), en cuatro formatos, con copy optimizado para
alcance orgánico con pocos o cero seguidores, y lo sube como **borrador** a la app
de aprobación (`app/`, publicada en Render; ver `CLAUDE.md`). El usuario lo revisa
allí y, si lo aprueba, la app lo publica en el siguiente hueco de `app/schedule.txt`
para su tipo y borra las imágenes.

## Formatos (tipos de post)

| Tipo (`kind`) | Qué es | Imagen | Texto de publicación |
|---|---|---|---|
| `carrusel` | 3–5 slides que promocionan una URL (servicios) | 1080x1350 (4:5), `--format carrusel`, fondo negro / verde tinta (portada y CTA en negro) | caption + hashtags |
| `publicacion` | 1 sola imagen: **un truco o dato útil de Excel**, con la web al final | 1080x1350 (4:5), `--format publicacion`, **fondo negro** | caption + hashtags |
| `historia` | 1 sola imagen: **promoción breve** de una URL | 1080x1920 (9:16), `--format historia`, **fondo lima y letra negra** | **ninguno** |
| `reel` | **vídeo animado de 10-30 s** (2-8 escenas de texto que entran línea a línea, barra de progreso y música original): dolor → solución → CTA | `reel_gen.py` → `video.mp4` 1080x1920 (9:16), H.264 | caption + hashtags |

Las historias por API son solo una imagen: no admiten stickers, enlaces, encuestas
ni texto de publicación, y duran 24 horas. **Todo el mensaje va dentro de la imagen**
(corto: un gancho y un remate) y el CTA nombra la web. El generador ya respeta los
márgenes de seguridad de Instagram (~250 px arriba y abajo).

**Reel (vídeo):** lo genera `scripts/reel_gen.py` (Pillow + el ffmpeg que trae `imageio-ffmpeg`; no hace
falta instalar ffmpeg). Duración total 6-30 s (la app rechaza más de 30 s y menos de 3 s); apunta a
**15-25 s**. Cada escena es un titular corto (el mismo estilo que las imágenes: `runs`, `body`, `theme`,
`seconds`), el texto aparece línea a línea y una barra lima de progreso recorre la parte alta. La
**música es original**: `reel_gen.py` la sintetiza él mismo (acordes, bajo, bombo suave y hi-hat; sin
samples ni terceros), así que está libre de derechos y no hay que atribuir nada. **Nunca** metas música
descargada ni de ningún catálogo (ni «libre» de terceros): cualquier otra pista exigiría verificar su
licencia. `--no-music` deja el vídeo con pista silenciosa. Estructura de un buen Reel: escena 1 = gancho
de ≤ 8 palabras (se decide en 2 s si se sigue viendo); 1-3 escenas intermedias con una idea cada una; última =
CTA con la web (lleva `cta_text`; la píldora de la web aparece sola). 3-6 escenas de 3-5 s funcionan bien.

## Principio de trabajo: AUTONOMÍA TOTAL en la creación

El usuario no quiere elegir entre variantes ni aprobar cada slide. **Genera un
único resultado final por slide, revísalo tú mismo visualmente (paso 5) y
entrega el carrusel completo de una vez.** Solo pregunta (con AskUserQuestion)
por datos que de verdad falten (ver paso 1).

La **publicación** es otra cosa: es una acción sobre la cuenta real del usuario y
la autoriza él en la app de aprobación. Esta skill nunca publica por su cuenta:
termina subiendo el borrador (paso 7).

## Restricciones (obligatorias)

**Prohibido**, en slides y en caption, cualquier CTA que dependa de enviar un
enlace por comentarios, mensajes o la bio:
- «Comenta X y te dejo/paso/mando el link» (y cualquier variante de «Comenta
  [PALABRA]…»).
- «Link en la bio», «link en la descripción», «te lo envío por DM».

El CTA siempre nombra la web (trabajoenexcel.com) con una acción concreta, por
ejemplo «Haz el test gratis de 5 minutos en trabajoenexcel.com». Antes de
generar o publicar, relee el copy de todos los slides y del caption y descarta
cualquier texto que incumpla esto. Si un carrusel lo incumple, no se publica.

## Flujo

### 1. Definir objetivo y URL
- **URL:** las páginas a promocionar están en la app (panel → URLs, que el usuario edita);
  léelas con `python scripts/pick_urls.py 99` (sin conexión usa `app/url.txt`). Si el usuario no especifica cuál, y no hay contexto para inferirlo,
  pregunta con opciones sacadas de ese archivo. Si menciona una URL de
  trabajoenexcel.com que no está en la lista, úsala igualmente.
- **Lectura obligatoria de la página:** el tema de CADA post sale de la página real de la URL (las del
  panel, incluidas las que el usuario acabe de añadir), aunque la URL esté en `references/urls.md`: ese
  archivo es solo apoyo. Si no puedes abrir la página (red bloqueada, error), **no generes ese post
  con datos de memoria ni lo cambies por otra URL sin avisar**: dile al usuario qué URL falló y por qué.
- **Tema:** haz `WebFetch` de la URL elegida y extrae de la página real el dolor,
  la keyword y la oferta. No te bases solo en memoria.
- **Objetivo (alcance / conexión / venta):** si no lo dice, infiérelo del
  contexto («quiero seguidores» → alcance; «quiero que compren clases» → venta)
  y dilo en una frase; no lo preguntes salvo que sea genuinamente ambiguo.
- **Tipo y nº de slides:** si no lo dice, carrusel. Un carrusel lleva 3–5 slides (por defecto 5); una publicación o una historia, exactamente 1 imagen; un reel, 1 vídeo (2-8 escenas, 6-30 s).

### 2. Sacar el ángulo real
Combina lo que extrajiste de la página con `references/urls.md`, que ya tiene el
dolor, la keyword SEO y el CTA verificados de cada página (si difieren, manda la
página). No inventes dolor genérico ni cifras que no estén en ninguna de las dos.

### 3. Escribir el copy de cada slide
Estructura por slide: `runs` = lista de (texto, "bold"|"italic"); `bold` = titular blanco, `italic` = frase de acento en lima; texto en minúsculas normales, no en mayúsculas; `body` opcional = párrafo en gris.
- Slide 1: hook específico, 1-2 líneas bold + remate de acento.
- Slides intermedios: una idea cada uno, con progresión lógica.
- Slide final: SIEMPRE termina con el CTA de `references/urls.md` para esa URL
  (acción concreta + trabajoenexcel.com). Lleva `"cta_text"` (frase corta,
  máx. 28 caracteres) y `"swipe_hint": false`. Respeta la sección
  «Restricciones» de más abajo.
- Todos los slides salvo el último llevan `"slide_no": "0N / 0T"`.

**Publicación de una imagen** (`publicacion`): un truco, atajo, función o dato útil de
Excel, correcto y comprobable (nombres de funciones en español: `BUSCARV`, `SI.ERROR`,
`HOY()`; si el truco depende de la versión, dilo). No inventes cifras ni estadísticas.
Si el truco lleva un atajo de teclado, lee antes `references/trucos-excel.md`: los
atajos Ctrl+letra no siempre coinciden entre el inglés y el español (público
España/LATAM), y ahí se registran las correcciones ya detectadas. Si el atajo no
está verificado ahí, usa un truco que no dependa de un atajo de teclado.
Una sola imagen: gancho en bold (el truco) + remate de acento (por qué importa), y
`"cta_text"` tipo «Más en trabajoenexcel.com» (máx. 28 caracteres). Sin `slide_no`.
`source_url`: `https://www.trabajoenexcel.com/`.

**Historia** (`historia`): una sola imagen 9:16 con la promoción breve de una URL:
gancho corto en bold + remate de acento + `"cta_text"` con la acción («Haz el test gratis»). Máximo unas 3-4 líneas de texto en total: se lee en 5 segundos. Sin caption.

**Reel** (`reel`): el mismo copy corto y afirmativo, pero repartido en escenas (JSON de escenas, ver la
cabecera de `reel_gen.py`). Ritmo: 3-4 s por escena (un titular de 2-3 líneas se lee en 3 s). Sin cifras
ni afirmaciones que no estén en la página real. Lleva caption y hashtags como una publicación (paso 6).

No escribas saltos de línea a mano: el script hace wrap midiendo la fuente real
(ver la sección anti-overflow de `references/style-guide.md`).

### 4. Generar las imágenes
Escribe el spec JSON y genera las imágenes en el **directorio temporal**
(scratchpad), nunca dentro del repo: las imágenes no deben pasar por git.

```bash
python .claude/skills/carruseles-app/scripts/carousel_gen.py <tmp>/spec.json <tmp>/post --format carrusel|publicacion|historia
```

(`--format` por defecto es `carrusel`. Con `publicacion` o `historia` el JSON lleva
exactamente 1 slide; el script lo comprueba.)

- **Reel:** `python .claude/skills/carruseles-app/scripts/reel_gen.py <tmp>/escenas.json <tmp>/post`
  escribe `<tmp>/post/video.mp4` y la hoja de contacto `<tmp>/post.preview.jpg` (fuera de la carpeta). Tarda
  ~1-2 min. Si avisa con `⚠ POSIBLE OVERFLOW` o con «el texto aún está entrando», acorta la escena o alarga
  `seconds`, y regenera. Si falta `imageio-ffmpeg`: `pip install imageio-ffmpeg numpy pillow`.
- Carpeta: `<tmp>/post/` (temporal). Solo existe hasta que se sube el borrador.
- El script escribe `slide-01.jpg`, `slide-02.jpg`... (Instagram solo acepta
  JPEG) e imprime dónde termina el texto de cada slide. Si avisa con
  `⚠ POSIBLE OVERFLOW`, acorta el copy de ese slide y vuelve a ejecutarlo.
- Requiere Pillow (`pip install pillow`). Las fuentes van incluidas en
  `assets/fonts/`; no hace falta instalar nada más.

### 5. Revisar
**Ortografía y mayúsculas (obligatorio, antes de subir nada).** Relee TODO el texto: el de cada
imagen, el título, el caption y los hashtags. Comprueba que:
- cada frase, cada línea de titular y cada botón **empiezan por mayúscula** (también el remate de
  acento y el `cta_text`; no vale «no hace falta aprender Excel» ni «solo el 20 %»);
- no hay erratas, faltan tildes ni signos de apertura (`¿ ?`, `¡ !`), y los números con porcentaje
  llevan espacio duro (`20\u00a0%`) para que el % no quede solo en una línea;
- los nombres propios y de funciones respetan su forma (Excel, BUSCARV, trabajoenexcel.com).
Si algo falla, corrige el JSON y regenera: nunca subas un borrador con una errata.

**Reel:** abre con Read la hoja `<tmp>/post.preview.jpg` (un fotograma por escena): comprueba que el
texto se lee entero y sin cortes. Además, el script imprime la duración final; debe ser ≤ 30 s.

Abre con Read el slide 1, el último y cualquiera que haya dado aviso de
overflow, y comprueba que no hay cortes de texto. Nunca entregues sin revisar
al menos el hook y los slides largos.

### 6. Escribir `meta.yaml` (copy de Instagram)
Crea `<tmp>/post/meta.yaml` con estos campos:

- `kind`: `carrusel`, `publicacion`, `historia` o `reel` (si falta, se entiende carrusel).
- `title`: nombre corto del post para el panel (máx. 120 caracteres).
- `source_url`: la URL de trabajoenexcel.com que promociona.
- `caption` y `hashtags` (lo que sigue). **Una historia no lleva `caption` ni
  `hashtags`**: solo `kind`, `title` y `source_url`.
- No hay `status` ni fecha: el estado lo gestiona la app y se publica cuando el
  usuario lo aprueba.
- **Primera línea del caption = keyword SEO exacta de la URL** (Instagram indexa
  en Google; está en `references/urls.md`). El hook de curiosidad va en el slide
  1, no en el caption.
- Cuerpo: 2-3 líneas máximo, directo, sin relleno. En una publicación con un truco
  de Excel, el cuerpo lo explica en 2-3 líneas con un ejemplo breve.
- CTA: el mismo del slide final, apuntando a trabajoenexcel.com (ver
  `references/urls.md`). Respeta la sección «Restricciones».
- Hashtags (`hashtags:` sin `#`): 3-6 mezclando tres tipos: genéricos de volumen
  alto (`excel`, `productividad`), de nicho medio (`buscarv`, `tablasdinamicas`,
  `powerquery`) y de intención de búsqueda (`buscandotrabajo`,
  `entrevistadetrabajo`, `cursodeexcel`).
- Música: los Reels de esta skill llevan pista original sin derechos (ver «Formatos»). El audio en
  tendencia de Instagram no se puede elegir por API; si el usuario quiere otro, que lo cambie él en
  Instagram tras publicar.

### 7. Subir el borrador a la app de aprobación
```bash
python scripts/upload_draft.py <tmp>/post --spec <tmp>/spec.json
```

- Sube las slides (o el `video.mp4`), el caption, los hashtags y el texto de los slides. El
  servidor vuelve a comprobar la restricción de CTA y rechaza el borrador si la
  incumple: corrige el copy y vuelve a subirlo.
- Necesita `IG_APP_URL` e `IG_APP_API_KEY` (variables de entorno o `.env` en la
  raíz, ignorado por git). En la rutina de la nube solo existe `IG_APP_URL`: la
  clave es una «credencial de API» del entorno que añade el proxy, así que el script
  funciona sin ella. Si el servidor responde 401 o falta `IG_APP_URL`, dilo al usuario;
  no inventes valores.
- Tras subirlo, el script borra las imágenes locales y muestra el enlace del
  borrador. **Dáselo al usuario y termina ahí**: la aprobación la hace él en el
  panel y la publicación sale sola en el siguiente hueco de `app/schedule.txt` para su
  tipo (por defecto: carrusel el martes 15:30; publicación e historia el jueves 19:00,
  hora de España). Recuérdale que debe aprobarlo **antes** de esa hora. No apruebes
  ni fuerces la publicación.

Si el post queda `failed` en el panel, el usuario ve el error. Un fallido no se
reintenta a ciegas (podría duplicar la publicación): primero se comprueba en el
perfil de Instagram si llegó a publicarse.

## Tanda semanal (los lunes)

Cuando se pida «la tanda semanal», «los 4 posts de la semana», o la ejecute la
rutina programada de los lunes, genera **4 piezas, una de cada tipo**, siguiendo el
flujo 1-7 para cada una, más estas reglas:

1. **Contexto:** ejecuta `python scripts/upload_draft.py --recent` para ver los posts
   de las últimas semanas (tipo, título y URL). Necesita `IG_APP_URL` (y la clave, ver paso 7).
2. **URLs al azar:** obtén 3 con `python scripts/pick_urls.py 3` (no las elijas tú: el
   script es el que sortea). La primera es para el **carrusel**, la segunda para la
   **historia** y la tercera para el **Reel**. Si una URL no está en `references/urls.md`, saca el dolor, la keyword y
   el CTA real de la propia página (`WebFetch`) y aplica la fórmula «[acción concreta] en
   trabajoenexcel.com». En la tanda semanal no modifiques archivos del repo.
3. **Las 4 piezas:**
   - **Carrusel** (`carrusel`, 3–5 slides): servicios/URL sorteada.
   - **Publicación de una imagen** (`publicacion`): un truco o dato útil de Excel, con
     la web al final.
   - **Historia** (`historia`): promoción breve de la segunda URL.
   - **Reel** (`reel`): vídeo animado de 15-25 s sobre la tercera URL (dolor → solución → CTA),
     con `reel_gen.py` y música original.
4. **Ángulos distintos:** entre las 4 de la tanda y respecto a los recientes: no repitas
   el mismo dolor, gancho, truco ni ejemplo de las últimas 3-4 semanas (en los trucos de
   Excel, no repitas la función o el atajo). Varía el objetivo (alcance / conexión / venta).
5. **Cada pieza en su propia carpeta temporal** (`<tmp>/post1` … `post4`), con
   su formato (`--format`), su revisión visual del paso 5 y las «Restricciones» de siempre.
6. **Sube las 4** con `scripts/upload_draft.py`. Si el servidor rechaza una, corrígela y
   vuelve a subirla; si al final no se pueden subir las 4, dilo claramente en el resumen.
7. **No apruebes ni publiques nada.** Termina con un resumen corto: las 4 piezas (tipo,
   título y enlace del panel) y el recordatorio de las horas de `app/schedule.txt` (por
   defecto: el carrusel sale el martes 15:30; la publicación y la historia, el jueves
   19:00; el Reel, el sábado 12:00): que las aprueben **antes** de esa hora.

## Referencias
- `references/urls.md` — dolor, keyword y CTA reales de las URLs verificadas. Léelo
  siempre en el paso 2, no lo repitas de memoria de conversaciones pasadas.
- `references/trucos-excel.md` — atajos y datos de Excel ya corregidos por el
  usuario (público España/LATAM). Léelo antes de dar un atajo de teclado en una
  `publicacion`, y añade ahí cualquier corrección nueva que te haga el usuario.
- `references/style-guide.md` — paleta, tipografía, estructura de slide y la
  regla anti-overflow. Léelo si vas a tocar colores/fuentes o si el script da
  overflow en varios slides seguidos.
- `scripts/carousel_gen.py` — el generador. No lo reescribas desde cero; si
  necesitas un ajuste de layout, edita este archivo.
