# Brief de sesión fotográfica — Fase 4 (banco de escenas)

> **Superado (2026-09-07):** el proyecto pivotó de sesión fotográfica real a escenas
> 100% generadas por IA. Este documento queda como referencia histórica de los
> requisitos técnicos de encuadre/composición, que siguen aplicando igual para
> escenas generadas. Ver `criterios-fase4-banco-escenas.md` para los criterios
> vigentes (origen IA, ratio de rostro visible, resolución).

Basado en `FASES-PROYECTO.md` (Fase 4) y en los resultados medidos en Fase 2/3
(`output/fase2/resultados-fase2.md`, `output/fase3/resultados-fase3.md`).

## Decisión: ángulo de cabeza fijo en 3/4

Justificación con datos, no solo costo:
- Fase 2 usó el 3/4 como escena "fácil" y el modelo ganador (Nano Banana) llegó a 5/5
  con el prompt corregido.
- Fase 3 probó frontal (0°), 3/4 (~45°) y perfil (~90°): **9/9 aprobadas**, sin
  degradación en ningún ángulo. Fijar 3/4 no sacrifica calidad, solo simplifica la
  dirección de foto (menos poses que coordinar = sesión más corta = menos costo).
- Riesgo a vigilar: el ángulo no es uno de los ejes de variación exigidos por el
  checklist (ver abajo), pero si las 25-30 fotos tienen el mismo giro de cabeza,
  el feed puede verse repetitivo. Se compensa variando fuerte los otros 5 ejes.

## 1. Requisitos técnicos de cada foto

- **Resolución:** mínimo 2000px en el lado corto — se necesita margen para recortar
  en los 3 formatos de salida (4:5, 1:1, 9:16) sin perder nitidez.
- **Enfoque:** nítido en rostro y en toda la zona de la cabeza (donde va a ir la
  gorra editada). Sin motion blur.
- **Iluminación:** controlada y pareja, sin sombras duras que corten la cara o la
  zona de la cabeza — la IA tiene que poder matchear esa luz al pegar la gorra real.
- **Entrega:** JPEG o PNG sin compresión agresiva, sin marca de agua, sin overlays
  de estudio/agencia (igual que se pidió para la foto de producto en Fase 0).

## 2. Encuadre y composición

- **Headroom:** dejar espacio arriba de la cabeza — si se corta el tope de la gorra
  al recortar a 4:5/1:1/9:16, la foto se descarta.
- **Altura de cámara:** a la altura de los ojos del modelo. Evitar picado/contrapicado
  fuerte (distorsiona la cabeza y complica que la gorra calce bien en la edición).
- **Variar encuadre entre tomas:** medio cuerpo, 3/4 de cuerpo, cuerpo entero — esto
  sí es un eje obligatorio del checklist, no se puede repetir el mismo encuadre en
  todas las fotos.

## 3. La gorra placeholder que usa el modelo en la sesión

- Preferentemente **lisa y de color neutro** (blanco, negro o gris), sin logo grande.
  En Fase 2 el fallo más común fue que la IA "contaminaba" el color de la gorra real
  con el color de la gorra de la escena — partir de un color neutro reduce ese riesgo.
- Calce natural en la cabeza, sin arrugas raras, sin volar con el viento.

## 4. Variación real (obligatoria, el ángulo fijo NO la reemplaza)

Ejes de la sección 3.3 — cada uno tiene que variar de foto a foto:

| Eje | Variar entre |
|---|---|
| Encuadre | medio cuerpo / 3-4 cuerpo / cuerpo entero |
| Entorno | estudio liso / urbano / exterior |
| Luz | dura / suave / dorada / fría |
| Vestuario | outfit distinto por modelo o por set |
| Postura | de pie, sentado, caminando, manos en bolsillos, brazos cruzados |

- **Rostro parcialmente oculto en ~50% de las tomas:** mirada hacia abajo, lentes de
  sol, mano cerca de la cara, cabello sobre la frente. Esto se puede lograr sin salir
  del 3/4 — de hecho la escena de Fase 2/3 que usamos de prueba ya tenía la cabeza
  mirando hacia abajo en 3/4 y funcionó perfecto.

## 5. Modelos reales — esto SÍ aplica ahora

A diferencia de la ruta 100% IA que se evaluó antes, con modelos reales el
requisito de la Fase 4 se activa:

- **Consentimiento firmado de uso comercial**, por cada modelo, antes de la sesión.
- El consentimiento debe cubrir explícitamente el uso en redes sociales
  (Instagram/TikTok) y catálogo, y el plazo de uso (indefinido o con vigencia).

## 6. Cantidad a producir

- Apuntar a **35-40 tomas candidatas** para terminar con las 25-30 aprobadas — el
  criterio de Fase 4 es binario y sin excepciones ("ninguna escena casi sirve, se
  descarta o se corrige antes de aceptar"), así que hay que dejar margen de descarte.
