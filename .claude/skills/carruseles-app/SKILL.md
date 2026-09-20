---
name: carruseles-app
description: Crea carruseles de Instagram de alto impacto y alcance para conseguir seguidores, promocionando las 3 páginas de trabajoenexcel.com (homepage, profesor-excel-online.html, test-nivel-excel.html), y los sube como borrador a la app de aprobación, donde el usuario los revisa y autoriza su publicación en @trabajoenexcel. Úsala SIEMPRE que el usuario pida "un carrusel", "carrusel de Instagram", "un post", "promociona esta URL en Instagram", mencione alcance/seguidores/engagement para trabajoenexcel.com, o pida contenido de Instagram sobre clases de Excel, el profesor particular, o el test de nivel. También úsala si pide ajustar colores, tipografía o número de slides de un carrusel ya generado con esta skill.
---

# Carruseles App — trabajoenexcel.com

Genera carruseles de Instagram (JPG 1080x1350) promocionando una de las 3 URLs
objetivo del negocio, con copy optimizado para alcance orgánico con pocos o cero
seguidores, y los sube como **borrador** a la app de aprobación (`app/`, publicada
en Render; ver `CLAUDE.md`). El usuario los revisa allí y, si los aprueba, la app
los publica en el siguiente hueco de `app/schedule.txt` y borra las imágenes.

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
- **Nº de slides:** 3–5. Si no lo dice, usa 5.

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

No escribas saltos de línea a mano: el script hace wrap midiendo la fuente real
(ver la sección anti-overflow de `references/style-guide.md`).

### 4. Generar las imágenes
Escribe el spec JSON y genera las imágenes en el **directorio temporal**
(scratchpad), nunca dentro del repo: las imágenes no deben pasar por git.

```bash
python .claude/skills/carruseles-app/scripts/carousel_gen.py <tmp>/spec.json <tmp>/post
```

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

- `title`: nombre corto del post para el panel (máx. 120 caracteres).
- `source_url`: la URL de trabajoenexcel.com que promociona.
- `caption` y `hashtags` (lo que sigue).
- No hay `status` ni fecha: el estado lo gestiona la app y se publica cuando el
  usuario lo aprueba.
- **Primera línea del caption = keyword SEO exacta de la URL** (Instagram indexa
  en Google; está en `references/urls.md`). El hook de curiosidad va en el slide
  1, no en el caption.
- Cuerpo: 2-3 líneas máximo, directo, sin relleno.
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
  raíz, ignorado por git). Si faltan, dilo al usuario; no las inventes.
- Tras subirlo, el script borra las imágenes locales y muestra el enlace del
  borrador. **Dáselo al usuario y termina ahí**: la aprobación la hace él en el
  panel y la publicación sale sola en el siguiente hueco de `app/schedule.txt`
  (por defecto martes 15:30 y jueves 19:00, hora de España). Recuérdale que debe
  aprobarlo **antes** de esa hora. No apruebes ni fuerces la publicación.

Si el post queda `failed` en el panel, el usuario ve el error. Un fallido no se
reintenta a ciegas (podría duplicar la publicación): primero se comprueba en el
perfil de Instagram si llegó a publicarse.

## Tanda semanal (los lunes)

Cuando se pida «la tanda semanal», «los 3 posts de la semana», o la ejecute la
rutina programada de los lunes, genera **3 carruseles** siguiendo el flujo 1-7 para
cada uno, más estas reglas:

1. **Contexto:** ejecuta `python scripts/upload_draft.py --recent` para ver los posts
   de las últimas semanas (título y URL). Necesita `IG_APP_URL` e `IG_APP_API_KEY`.
2. **3 URLs al azar de `url.txt`, distintas entre sí:** obtenlas con
   `python scripts/pick_urls.py 3` (no las elijas tú: el script es el que sortea).
   Un post por cada URL. Si una URL no está en `references/urls.md`, saca el dolor,
   la keyword y el CTA real de la propia página (`WebFetch`) y aplica la fórmula
   «[acción concreta] en trabajoenexcel.com». En la tanda semanal no modifiques
   archivos del repo (no añadas esa URL a `urls.md`).
3. **Ángulos distintos:** entre los 3 de la tanda y respecto a los recientes: no
   repitas el mismo dolor, gancho ni ejemplo de las últimas 3-4 semanas. Varía el
   objetivo (alcance / conexión / venta) entre los 3.
4. **Cada post en su propia carpeta temporal** (`<tmp>/post1`, `post2`, `post3`), con
   su revisión visual del paso 5 y las «Restricciones» de siempre.
5. **Sube los 3 borradores.** Si el servidor rechaza uno, corrígelo y vuelve a
   subirlo; si al final no se pueden subir los 3, dilo claramente en el resumen.
6. **No apruebes ni publiques nada.** Termina con un resumen corto: los 3 títulos con
   su enlace del panel, y el recordatorio de que hay 2 huecos por semana (martes
   15:30 y jueves 19:00): que aprueben los 2 mejores antes de la hora.

## Referencias
- `references/urls.md` — dolor, keyword y CTA reales de las 3 URLs. Léelo
  siempre en el paso 2, no lo repitas de memoria de conversaciones pasadas.
- `references/style-guide.md` — paleta, tipografía, estructura de slide y la
  regla anti-overflow. Léelo si vas a tocar colores/fuentes o si el script da
  overflow en varios slides seguidos.
- `scripts/carousel_gen.py` — el generador. No lo reescribas desde cero; si
  necesitas un ajuste de layout, edita este archivo.
