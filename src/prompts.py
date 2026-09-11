"""
Fuente unica de verdad para el prompt de generacion de Pista B y las
constantes de version/escenas que dependen de el.

No hardcodear aqui ningun valor especifico de un SKU (color, forma de marca,
etc.) - el prompt debe funcionar igual de bien para cualquier gorra que pase
por el pipeline, no solo para la gorra blanca/negra usada en las pruebas
iniciales.
"""

PROMPT_V3 = (
    "Image 1 is a person wearing a plain cap. Image 2 is a product photo of a cap "
    "on a white background. Replace the cap the person is wearing in image 1 with "
    "the exact cap shown in image 2, matching its color, embroidered logo text, and "
    "side patch precisely. "
    "CRITICAL COLOR RULE: match the crown and visor colors EXACTLY as they appear in "
    "image 2, pixel by pixel - do NOT reuse any color from the cap currently worn in "
    "image 1. Do not blend, average, or tint the two cap colors together. "
    "CRITICAL BRANDING RULE: reproduce any embroidered logo, printed text, or side "
    "patch from image 2 exactly as it appears there - same text, same font, same "
    "position, same colors. If image 2's cap has no visible side patch, do not add "
    "one. "
    "CRITICAL SHAPE RULE: replicate the exact crown structure and brim curvature of "
    "the cap in image 2 - do NOT use the crown shape, brim curve, or softness of the "
    "cap currently worn in image 1. "
    "Keep the person's face, skin tone, hair, pose, clothing, and background "
    "completely unchanged. Match the head angle and lighting of image 1."
)

# Version del prompt + esquema de QA. Subirla invalida automaticamente las
# evaluaciones anteriores para efectos de "evaluacion vigente" (ver
# ultima_evaluacion_vigente en db.py) sin tocar ninguna fila historica -
# actualizar esto cada vez que cambie PROMPT_QA, el esquema de items, o el
# criterio de aprobacion en fase6_qa_reintento.py.
VERSION_QA = "v2_generic_2026-09-10"

# Subconjunto fijo del banco de escenas usado en produccion (Pista B). Vive
# aqui, no en fase8_worker_ingesta.py, para que db.py pueda importarlo
# (aprobar_trabajo lo necesita) sin crear un import circular con el worker.
ESCENAS_PRODUCCION = ["04", "09", "29"]
