# Prompts para generar escenas — Fase 4

Dos plantillas: una para rostro oculto (~80-85% de las escenas) y otra para
rostro visible (~15-20%), según el criterio fijado en
`criterios-fase4-banco-escenas.md`. Cambia los `[ ]` en cada generación para
cumplir la variación obligatoria de encuadre/entorno/luz/vestuario/postura.

## Plantilla A — rostro oculto (usar en ~80-85% de las escenas)

```
Professional lifestyle photo of a [DESCRIPCIÓN DE PERSONA: edad/género/etnia/
contextura] wearing a plain solid gray baseball cap with no logo, no text, no
graphics. The person's face is mostly hidden or turned away — [VARIAR: looking
down at the ground / cap brim pulled low over the eyes / hand raised near the
face adjusting the cap / head turned to a 3/4 angle away from camera / seen
from behind]. [ENCUADRE: close-up headshot / medium shot from the waist up /
full body shot]. Setting: [ENTORNO: plain seamless studio background in
[color] / urban street with soft bokeh / outdoor natural light / cozy indoor
setting]. Lighting: [LUZ: soft diffused studio light / warm golden hour light
/ cool overcast light / hard directional light with visible shadow].
Wardrobe: [VESTUARIO: oversized t-shirt / hoodie / knit sweater / denim
jacket / plain shirt], casual streetwear style. Pose: [POSTURA: standing
relaxed / crouching / walking / hands in pockets / arms crossed / leaning
against a wall]. Photorealistic, shot on a professional camera, sharp focus,
high detail, no text overlays, no watermark, no brand logos anywhere in frame.
```

## Plantilla B — rostro visible (usar en ~15-20% de las escenas)

```
Professional portrait photo of a [DESCRIPCIÓN DE PERSONA: edad/género/etnia/
contextura] wearing a plain solid gray baseball cap with no logo, no text, no
graphics, cap brim up so the eyes are clearly visible. Looking directly at
the camera or at a natural 3/4 angle, face clearly visible and in focus,
neutral or subtle confident expression. [ENCUADRE: close-up headshot / medium
shot from the chest up]. Setting: [ENTORNO: plain seamless studio background
in [color] / softly blurred outdoor background]. Lighting: [LUZ: soft
flattering studio light with a visible catchlight in the eyes / warm natural
light]. Wardrobe: [VESTUARIO: plain t-shirt / sweater / shirt], casual
streetwear style. Photorealistic, shot on a professional camera, sharp focus
on the face, high detail, no text overlays, no watermark, no brand logos
anywhere in frame.
```

## Notas de uso

- **Variá la descripción de persona** en cada generación (edad, género,
  etnia, tipo de cabello) para mantener la diversidad que ya tiene el lote
  actual de 33 — no repitas la misma persona en escenas distintas.
- **La gorra siempre gris lisa, sin logo.** Es la que evita que la IA de la
  Fase 2/3 (Nano Banana) contamine el color al reemplazarla por la gorra real.
- **Resolución:** ChatGPT/DALL-E no deja pedir un tamaño en píxeles exacto,
  solo orientación (cuadrada/vertical/horizontal) — por eso el paso de
  upscale con `fal-ai/clarity-upscaler` (~$0.16/imagen) sigue siendo necesario
  después de generar, sin importar qué tan detallado pidas el prompt.
- **Ángulo:** por defecto dejé "3/4" como opción dentro de la variación de
  Plantilla A, pero no es obligatorio uniformarlo — la Fase 3 confirmó que
  cualquier ángulo entre frontal y perfil funciona igual de bien en la edición
  posterior.
