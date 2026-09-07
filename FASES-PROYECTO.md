# Fases del proyecto — Sistema de publicaciones Gorrolandia

Basado en `especificacion-sistema-publicaciones-gorras.md` v1.0. Cada fase tiene un objetivo único, un entregable verificable y un criterio de aprobación medible (no "se ve bien", sino un número o un checklist). No se pasa a la fase siguiente sin cerrar el criterio de la anterior.

---

## Fase 0 — Insumos mínimos para empezar
**Objetivo:** tener lo mínimo indispensable para correr la Fase 1 sin bloqueos.

**Entregables:**
- 1 SKU con foto 3/4 sin marca de agua (pedir versión limpia al socio de fotografía — hoy solo existe con marca de agua, sección 7)
- 1 escena base candidata (puede ser generada con IA para esta prueba, no necesita ser del banco final)
- Cuenta en fal.ai o Replicate con API key activa

**Criterio de aprobación:** los 3 archivos existen y son accesibles desde el entorno de trabajo. Binario: sí/no.

---

## Fase 1 — Prueba manual end-to-end de 1 gorra
**Objetivo:** confirmar que el pipeline conceptual (Pista A + Pista B) es técnicamente viable antes de invertir en automatización.

**Entregable:** script (sin cola, sin Drive, sin panel) que toma 1 gorra + 1 escena y produce:
- Imagen de producto (compositing determinista)
- Imagen de contexto (edición por IA)

**Criterio de aprobación:** ambas imágenes se generan sin error técnico. Aún no se exige que la calidad sea buena — eso se mide en la Fase 2. Esta fase solo prueba que el flujo corre de punta a punta.

**Costo estimado:** < $0.10

---

## Fase 2 — Comparativa de modelos (decisión de modelo de IA)
**Objetivo:** elegir el modelo de IA para la Pista B con datos, no con especificación de fabricante.

**Método:** usar el SKU Homie (caso más difícil: bordado gótico, dorado, parche con texto diminuto) contra 2–3 modelos candidatos (FLUX.1 Kontext [pro], Nano Banana/Gemini Flash Image, FASHN v1.6).

| Test | Escena | Corridas |
|---|---|---|
| Test 1 — ángulo similar a la foto de producto | Fácil | 5 por modelo |
| Test 2 — ángulo divergente | Difícil | 5 por modelo |

**Criterio de aprobación (umbral de decisión, ya definido en la especificación):**
- El modelo ganador debe pasar **≥4 de 5 en Test 1** y **≥3 de 5 en Test 2**, evaluado con el checklist de la sección 6.2.
- **Si ningún modelo alcanza 4/5 en Test 1:** parar aquí. El problema es la calidad de la foto de entrada, no el modelo. La inversión siguiente va al protocolo de captura fotográfica, no a seguir probando modelos ni a construir el banco de escenas.

**Costo estimado:** ≈$1.50 (30 generaciones)

**Este es el punto de decisión más importante del proyecto** — condiciona si el resto tiene sentido construirse.

---

## Fase 3 — Medición de tolerancia de ángulo
**Objetivo:** cuantificar cuánto se puede desviar la cabeza del 3/4 exacto antes de que el modelo ganador falle, para tener un criterio objetivo de filtro al construir el banco de escenas.

**Método:** 3 escenas (frontal, 3/4, perfil) × 3 generaciones cada una, con el modelo elegido en Fase 2.

**Entregable:** un valor en grados (ej. "±25°") documentado como criterio de aceptación de escenas.

**Criterio de aprobación:** el experimento produce un número reproducible, no una impresión subjetiva. Se acepta cualquier resultado — incluso uno peor de lo esperado — siempre que quede cuantificado.

**Costo estimado:** ≈$0.50

---

## Fase 4 — Construcción del banco de escenas
**Objetivo:** tener el activo reutilizable que hace que el costo marginal por publicación sea bajo.

**Entregable:** 25–30 escenas aprobadas, cumpliendo:
- Ángulo de cabeza dentro de la tolerancia medida en Fase 3
- Consentimiento firmado de uso comercial (si hay modelo real)
- Variación real en encuadre, entorno, luz, vestuario, postura (checklist sección 3.3)
- Aproximadamente la mitad con rostro parcialmente oculto

**Criterio de aprobación:** cada escena pasa un checklist binario (cumple/no cumple los puntos de arriba) antes de entrar al banco. Ninguna escena "casi sirve" — se descarta o se corrige antes de aceptar.

**Costo estimado:** $5–15 (IA) o S/150–300 (sesión fotográfica real)

---

## Fase 5 — Pista A en producción (compositing determinista)
**Objetivo:** automatizar la imagen de producto, que no depende de IA y debería ser trivial de verificar.

**Entregable:** script/servicio que recibe cualquier foto normalizada de gorra y produce la imagen de catálogo (recorte + fondo + sombra) en los 3 formatos de salida (4:5, 1:1, 9:16).

**Criterio de aprobación:** correr el mismo input 5 veces produce **exactamente el mismo output** (hash idéntico o diff visual nulo). Si hay variación, algo del pipeline no es determinista y hay que corregirlo antes de seguir — este es el módulo que la especificación garantiza como "resultado idéntico siempre".

---

## Fase 6 — Control de calidad automático + reintento dirigido
**Objetivo:** implementar el ciclo que reduce "regenerar 5 veces a ciegas" a "regenerar 1.2 veces dirigido" (sección 6.1).

**Entregable:** función que recibe imagen original + imagen generada, llama al modelo de visión, devuelve el JSON de score, y dispara reintento con prompt ajustado si `score < 80` (máx. 2 intentos).

**Criterio de aprobación:** correr sobre un lote de 10 generaciones ya conocidas (mezcla de buenas y con fallas evidentes de la Fase 2). El clasificador debe coincidir con el juicio humano en al menos 8 de 10 casos. Si falla más, el prompt de QA se ajusta antes de conectar el reintento automático a producción.

---

## Fase 7 — Registro y trazabilidad
**Objetivo:** que desde la primera corrida real se pueda saber qué escena o qué prompt sale caro (sección 4.5) — no se puede reconstruir esto después.

**Entregable:** tabla en base de datos que registra cada llamada a la API con los campos de la sección 4.5 (sku, escena_id, modelo_ia, prompt, seed, intento, score_qa, problema, costo_usd, ruta_output).

**Criterio de aprobación:** después de correr las Fases 5 y 6 sobre 5 SKU de prueba, se puede responder desde la base de datos, sin mirar logs sueltos: costo total, costo por SKU, tasa de reintento, y cuál escena tiene peor tasa de aprobación.

---

## Fase 8 — Automatización end-to-end
**Objetivo:** quitar la intervención manual del flujo completo (Drive → cola → generación → QA → panel de revisión).

**Entregable:** pipeline corriendo con ingesta desde Google Drive (webhook o polling), cola de trabajos, y panel de revisión (Streamlit) donde un humano aprueba/rechaza antes de publicar.

**Criterio de aprobación:** subir 10 SKU nuevos a la carpeta de Drive sin tocar código ni consola, y verse aparecer en el panel de revisión como listos para aprobar, con costo y score visibles por ítem.

---

## Fase 9 — Piloto con catálogo real
**Objetivo:** validar el sistema completo contra volumen real antes de considerarlo "en producción".

**Entregable:** 20–30 SKU reales procesados de punta a punta, publicados (Instagram automático, TikTok exportado para subida manual).

**Criterio de aprobación:**
- Costo real por publicación ≈ el proyectado (~$0.038, sección 5.4) — si se dispara, hay que auditar qué escena o prompt lo está causando (para eso existe la Fase 7)
- Tasa de aprobación humana en el panel ≥ el umbral que se defina como aceptable (ej. 80% sin corrección manual)
- Ningún caso de checklist de la sección 6.2 fallado en lo publicado (logo ilegible, parche duplicado, cara alterada, etc.)

---

## Resumen de puntos de no-retorno (gates)

Los que de verdad frenan o redirigen el proyecto si fallan:

1. **Fase 2** — si ningún modelo pasa 4/5 en Test 1 → el problema es la foto de entrada, no la IA. Se redirige inversión al protocolo de captura.
2. **Fase 5** — si el compositing determinista no es 100% reproducible → hay un bug, no se automatiza sobre una base inestable.
3. **Fase 9** — si el costo real se dispara sobre el proyectado → se audita con los datos de la Fase 7 antes de escalar a todo el catálogo.

Todo lo demás es secuencial pero no bloqueante de la misma forma: se puede ajustar (ej. escenas rechazadas en Fase 4) sin replantear el proyecto.
