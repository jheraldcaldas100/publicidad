# Checklist QA — sección 6.2 (reconstruido)

> El documento original `especificacion-sistema-publicaciones-gorras.md` no está en el repo.
> Este checklist se reconstruyó a partir de los criterios ya usados en el proyecto
> (prompt de Pista B en Fase 1, y el gate de calidad mencionado en la Fase 9) para poder
> cerrar el criterio de aprobación de la Fase 2. Ajustar si aparece el documento original.

Cada imagen generada (Pista B) se evalúa contra estos 8 ítems, binario cumple/no cumple.
4 de ellos son **críticos**: si falla cualquiera, la corrida se cuenta como **NO aprobada**
sin importar el resto.

| # | Ítem | Crítico |
|---|------|:---:|
| 1 | Color de la gorra coincide con el SKU real (base y visera), no se mezcla con el color de la gorra de la escena | ✅ |
| 2 | Bordado/logo texto legible y fiel al original (mismo texto, mismo estilo, sin distorsión) | ✅ |
| 3 | Parche lateral presente, no duplicado, no deformado | ✅ |
| 4 | Rostro, tono de piel y cabello de la persona sin alterar | ✅ |
| 5 | Pose, ropa y fondo de la escena sin alterar | |
| 6 | Ángulo de la gorra coherente con el ángulo de la cabeza (no se ve pegada/flotando) | |
| 7 | Iluminación y sombra de la gorra coherente con la escena | |
| 8 | Estructura de la gorra (copa de 6 paneles rígida, curvatura moderada de la visera) coherente con el SKU real — no hereda la forma de la gorra placeholder de la escena (ej. copa suave/floja, visera plana o excesivamente curva) | |

**Regla de aprobación por corrida:** PASA si cumple los 4 ítems críticos Y al menos 3 de los
4 no críticos (score ≥ 7/8). Cualquier falla crítica = NO aprobada, sin excepción.

**Historial:** el ítem 8 se agregó en Fase 4 (2026-09-07) al detectar que, sin una regla
explícita de forma en el prompt, la visera podía salir casi plana en vez de con la curvatura
moderada del SKU real — no copiaba la gorra placeholder, pero tampoco clonaba con precisión
la del producto. Ver `PROMPT_V3` en `src/fase2_retry_nano_banana.py` /
`src/fase3_tolerancia_angulo.py`. Los resultados de Fase 2/3 documentados con `PROMPT_V2`
(sin regla de forma) siguen válidos para los ítems 1-7; el ítem 8 no fue evaluado en esas
corridas.

**Regla de aprobación por modelo (Fase 2):**
- Test 1 (escena fácil, ángulo similar a la foto de producto): ≥4 de 5 corridas aprobadas
- Test 2 (escena difícil, ángulo divergente): ≥3 de 5 corridas aprobadas
- Si ningún modelo llega a 4/5 en Test 1 → parar el proyecto en este punto (gate de Fase 2,
  ver `FASES-PROYECTO.md`), el problema es la foto de entrada, no el modelo.
