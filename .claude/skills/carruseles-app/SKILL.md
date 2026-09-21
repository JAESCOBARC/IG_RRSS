---
name: carruseles-app
description: Crea contenido de Instagram (carruseles, publicaciones de una imagen e historias) de alto impacto y alcance para conseguir seguidores, promocionando las páginas de trabajoenexcel.com (homepage, profesor-excel-online.html, test-nivel-excel.html), y los sube como borrador a la app de aprobación, donde el usuario los revisa y autoriza su publicación en @trabajoenexcel. Úsala SIEMPRE que el usuario pida "un carrusel", "carrusel de Instagram", "un post", "una historia", "una publicación", "promociona esta URL en Instagram", mencione alcance/seguidores/engagement para trabajoenexcel.com, o pida contenido de Instagram sobre clases de Excel, el profesor particular, o el test de nivel. También úsala si pide ajustar colores, tipografía o número de slides de un carrusel ya generado con esta skill.
---

# Carruseles App — trabajoenexcel.com

Genera contenido de Instagram en JPG, en tres formatos, con copy optimizado para
alcance orgánico con pocos o cero seguidores, y lo sube como **borrador** a la app
de aprobación (`app/`, publicada en Render; ver `CLAUDE.md`). El usuario lo revisa
allí y, si lo aprueba, la app lo publica en el siguiente hueco de `app/schedule.txt`
para su tipo y borra las imágenes.

## Formatos (tipos de post)

| Tipo (`kind`) | Qué es | Imagen | Texto de publicación |
|---|---|---|---|
| `carrusel` | 3–5 slides que promocionan una URL (servicios) | 1080x1350 (4:5), `--format carrusel`, fondo crema y letra oscura | caption + hashtags |
| `publicacion` | 1 sola imagen: **un truco o dato útil de Excel**, con la web al final | 1080x1350 (4:5), `--format publicacion`, **fondo verde y letra blanca** | caption + hashtags |
| `historia` | 1 sola imagen: **promoción breve** de una URL | 1080x1920 (9:16), `--format historia`, **fondo verde y letra blanca** | **ninguno** |

Las historias por API son solo una imagen: no admiten stickers, enlaces, encuestas
ni texto de publicación, y duran 24 horas. **Todo el mensaje va dentro de la imagen**
(corto: un gancho y un remate) y el CTA nombra la web. El generador ya respeta los
márgenes de seguridad de Instagram (~250 px arriba y abajo).

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
- **URL:** las páginas a promocionar están en `url.txt` (raíz del repo); léelo
  siempre. Si el usuario no especifica cuál, y no hay contexto para inferirlo,
  pregunta con opciones sacadas de ese archivo. Si menciona una URL de
  trabajoenexcel.com que no está en `url.txt`, úsala igualmente.
- **Tema:** haz `WebFetch` de la URL elegida y extrae de la página real el dolor,
  la keyword y la oferta. No te bases solo en memoria.
- **Objetivo (alcance / conexión / venta):** si no lo dice, infiérelo del
  contexto («quiero seguidores» → alcance; «quiero que compren clases» → venta)
  y dilo en una frase; no lo preguntes salvo que sea genuinamente ambiguo.
- **Tipo y nº de slides:** si no lo dice, carrusel. Un carrusel lleva 3–5 slides (por defecto 5); una publicación o una historia, exactamente 1 imagen.

### 2. Sacar el ángulo real
Combina lo que extrajiste de la página con `references/urls.md`, que ya tiene el
dolor, la keyword SEO y el CTA verificados de cada página (si difieren, manda la
página). No inventes dolor genérico ni cifras que no estén en ninguna de las dos.

### 3. Escribir el copy de cada slide
Estructura por slide: `runs` = lista de (texto, "bold"|"italic").
- Slide 1: hook específico, 1-2 líneas bold + remate en itálica.
- Slides intermedios: una idea cada uno, con progresión lógica.
- Slide final: SIEMPRE termina con el CTA de `references/urls.md` para esa URL
  (acción concreta + trabajoenexcel.com). Lleva `"cta_text"` (frase corta, en
  mayúsculas, máx. 28 caracteres) y `"swipe_hint": false`. Respeta la sección
  «Restricciones» de más abajo.
- Todos los slides salvo el último llevan `"slide_no": "0N / 0T"`.

**Publicación de una imagen** (`publicacion`): un truco, atajo, función o dato útil de
Excel, correcto y comprobable (nombres de funciones en español: `BUSCARV`, `SI.ERROR`,
`HOY()`; si el truco depende de la versión, dilo). No inventes cifras ni estadísticas.
Una sola imagen: gancho en bold (el truco) + remate en itálica (por qué importa), y
`"cta_text"` tipo «MÁS EN TRABAJOENEXCEL.COM» (máx. 28 caracteres). Sin `slide_no`.
`source_url`: `https://www.trabajoenexcel.com/`.

**Historia** (`historia`): una sola imagen 9:16 con la promoción breve de una URL:
gancho corto en bold + remate en itálica + `"cta_text"` con la acción («HAZ EL TEST
GRATIS.»). Máximo unas 3-4 líneas de texto en total: se lee en 5 segundos. Sin caption.

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

- Carpeta: `<tmp>/post/` (temporal). Solo existe hasta que se sube el borrador.
- El script escribe `slide-01.jpg`, `slide-02.jpg`... (Instagram solo acepta
  JPEG) e imprime dónde termina el texto de cada slide. Si avisa con
  `⚠ POSIBLE OVERFLOW`, acorta el copy de ese slide y vuelve a ejecutarlo.
- Requiere Pillow (`pip install pillow`). Las fuentes van incluidas en
  `assets/fonts/`; no hace falta instalar nada más.

### 5. Revisar
Abre con Read el slide 1, el último y cualquiera que haya dado aviso de
overflow, y comprueba que no hay cortes de texto. Nunca entregues sin revisar
al menos el hook y los slides largos.

### 6. Escribir `meta.yaml` (copy de Instagram)
Crea `<tmp>/post/meta.yaml` con estos campos:

- `kind`: `carrusel`, `publicacion` o `historia` (si falta, se entiende carrusel).
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
- Si preguntan por música/audio: el audio en tendencia impulsa Reels, no
  carruseles estáticos; para máximo alcance, un Reel con las mismas slides rinde
  más (este repo solo publica carruseles/imágenes).

### 7. Subir el borrador a la app de aprobación
```bash
python scripts/upload_draft.py <tmp>/post --spec <tmp>/spec.json
```

- Sube las slides, el caption, los hashtags y el texto de los slides. El
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

Cuando se pida «la tanda semanal», «los 3 posts de la semana», o la ejecute la
rutina programada de los lunes, genera **3 piezas, una de cada tipo**, siguiendo el
flujo 1-7 para cada una, más estas reglas:

1. **Contexto:** ejecuta `python scripts/upload_draft.py --recent` para ver los posts
   de las últimas semanas (tipo, título y URL). Necesita `IG_APP_URL` (y la clave, ver paso 7).
2. **URLs al azar:** obtén 2 con `python scripts/pick_urls.py 2` (no las elijas tú: el
   script es el que sortea). La primera es para el **carrusel** y la segunda para la
   **historia**. Si una URL no está en `references/urls.md`, saca el dolor, la keyword y
   el CTA real de la propia página (`WebFetch`) y aplica la fórmula «[acción concreta] en
   trabajoenexcel.com». En la tanda semanal no modifiques archivos del repo.
3. **Las 3 piezas:**
   - **Carrusel** (`carrusel`, 3–5 slides): servicios/URL sorteada.
   - **Publicación de una imagen** (`publicacion`): un truco o dato útil de Excel, con
     la web al final.
   - **Historia** (`historia`): promoción breve de la segunda URL.
4. **Ángulos distintos:** entre las 3 de la tanda y respecto a los recientes: no repitas
   el mismo dolor, gancho, truco ni ejemplo de las últimas 3-4 semanas (en los trucos de
   Excel, no repitas la función o el atajo). Varía el objetivo (alcance / conexión / venta).
5. **Cada pieza en su propia carpeta temporal** (`<tmp>/post1`, `post2`, `post3`), con
   su formato (`--format`), su revisión visual del paso 5 y las «Restricciones» de siempre.
6. **Sube las 3** con `scripts/upload_draft.py`. Si el servidor rechaza una, corrígela y
   vuelve a subirla; si al final no se pueden subir las 3, dilo claramente en el resumen.
7. **No apruebes ni publiques nada.** Termina con un resumen corto: las 3 piezas (tipo,
   título y enlace del panel) y el recordatorio de las horas de `app/schedule.txt` (por
   defecto: el carrusel sale el martes 15:30; la publicación y la historia, el jueves
   19:00): que las aprueben **antes** de esa hora.

## Referencias
- `references/urls.md` — dolor, keyword y CTA reales de las URLs verificadas. Léelo
  siempre en el paso 2, no lo repitas de memoria de conversaciones pasadas.
- `references/style-guide.md` — paleta, tipografía, estructura de slide y la
  regla anti-overflow. Léelo si vas a tocar colores/fuentes o si el script da
  overflow en varios slides seguidos.
- `scripts/carousel_gen.py` — el generador. No lo reescribas desde cero; si
  necesitas un ajuste de layout, edita este archivo.
