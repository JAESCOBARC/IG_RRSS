# Guía de estilo — carruseles trabajoenexcel.com

## Patrón visual (inspirado en Much Media, adaptado a la marca)
Fondo sólido + tipografía condensada bold en mayúsculas + una frase corta en
itálica de acento como "punchline" + línea divisora fina + ícono de flecha en
círculo + marca en cabecera/pie. Editorial, minimalista, mucho espacio en
blanco arriba y abajo del bloque de texto.

## Paleta (aproximación verificada por el usuario como "verde bosque + crema")
- Fondo: `#F4EFE1` (cream/hueso)
- Texto principal: `#182A20` (casi negro, tono verde oscuro)
- Acento (itálica, líneas, ícono, CTA): `#2F6B47` (verde bosque)
- Texto secundario/footer: `#8A9088` (gris)

⚠️ Este hex es una aproximación de diseño, no extraído verificado del CSS del
sitio (el fetch no expone estilos). Si el usuario da en algún momento un hex
oficial de marca, actualiza esta tabla inmediatamente y trátalo como el
estándar desde ese momento.

## Tipografía
Fuentes incluidas en `assets/fonts/` (sin depender de Canva, de internet ni de
fuentes del sistema):
- Bold/mayúsculas: `DejaVu Sans Condensed` bold
- Texto secundario (cabecera derecha, numeración, pie): `DejaVu Sans Condensed` regular
- Itálica de acento: `DejaVu Serif Condensed` bold italic

Alternativas comunes si se quiere replicar en Canva/Figma más adelante:
- Bold condensada: **Oswald** (o Bebas Neue / Anton para más impacto)
- Itálica de acento: **Playfair Display** bold italic

## Estructura de cada slide
1. Header: `TRABAJO EN EXCEL®` (izq) / `SOCIAL AD` (der), pequeño, letter-spacing.
2. Bloque de texto principal, empieza ~y=460–560 según cuánto texto tenga:
   - 1-2 líneas bold en mayúsculas (la idea)
   - 1 línea itálica en verde (el "punch" — la frase que se recuerda)
   - opcional: 1 línea bold más cerrando la idea
3. Footer: línea divisora fina verde + `TRABAJOENEXCEL.COM` (der).
4. Esquina inferior derecha: ícono de flecha en círculo (indicador de swipe)
   en todos los slides excepto el último, que en su lugar lleva el CTA_TEXT
   + el mismo ícono.
5. Esquina inferior izquierda: numeración `01 / 0N` en todos menos el CTA.

## Reglas de contenido (heredadas del sistema de carruseles)
- 4 a 9 slides. Slide 1 = hook específico (nunca genérico). Última = CTA con
  fórmula "[Acción concreta] en trabajoenexcel.com" (el `cta_text` ≤ 28
  caracteres para no chocar con la flecha) — nunca "sígueme" ni "Comenta [PALABRA]
  y te dejo el link" (ver la restricción de CTA en `urls.md`).
- Una idea por slide. Si un slide no avanza la idea, no va.
- Progresión lógica: cada slide construye sobre el anterior.

## Anti-overflow (lección aprendida — no repetir el error)
NUNCA escribas saltos de línea a mano adivinando dónde corta el texto. El
script mide el ancho real con la fuente exacta (Pillow + `getbbox`) y hace
wrap automático. Si un slide queda muy denso (el script avisa con
"⚠ POSIBLE OVERFLOW"), la solución es acortar el copy o subir `start_y`, no
forzar el tamaño de fuente hacia abajo (rompe la jerarquía visual).

## Formatos
- **carrusel** y **publicacion**: 1080x1350 (4:5). La publicación va sin flecha de deslizar
  ni numeración; el CTA (`cta_text`) va abajo a la izquierda.
- **historia**: 1080x1920 (9:16). Instagram superpone su interfaz en los ~250 px de arriba
  y de abajo: cabecera en y=300, texto desde y≈760 y pie/CTA por encima de y≈1620. Sin flecha.
  Es una sola imagen sin caption: el mensaje va entero en la imagen y debe leerse en segundos.
