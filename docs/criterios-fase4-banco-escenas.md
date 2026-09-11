# Criterios vigentes — Fase 4 (banco de escenas)

Reemplaza el criterio original de `FASES-PROYECTO.md` en los dos puntos donde el
proyecto se desvió deliberadamente de la especificación base. Todo lo demás de
Fase 4 sigue vigente sin cambios.

## Origen: 100% generado por IA (ChatGPT), no sesión fotográfica real

- **Consentimiento firmado de uso comercial: no aplica.** Ese requisito de
  `FASES-PROYECTO.md` es condicional ("si hay modelo real") — con personas
  sintéticas queda descartado.
- **Verificar licencia de la herramienta generadora.** OpenAI permite uso
  comercial del contenido generado en ChatGPT/API siempre que no representen
  personas reales identificables sin consentimiento (no aplica aquí, son
  personas sintéticas) — confirmar la política de uso vigente antes de publicar
  a gran escala, ya que estos términos cambian con el tiempo.
- Para el lote ampliado (ver siguiente sección) se generará vía fal.ai en vez de
  la interfaz de ChatGPT, por reproducibilidad y trazabilidad (registro CSV por
  imagen, igual que en Fase 2/3). Mismo razonamiento de licencia aplica.

## Ratio de rostro visible: ~15-20%, no ~50%

**Decisión de marca (2026-09-07):** la gorra debe ser la protagonista, no el
modelo. Se descarta el "~50% con rostro parcialmente oculto" de la
especificación original y se fija el ratio real del primer lote de 33 escenas
(~5-6 de 33 con rostro claramente visible) como el objetivo del banco completo.

- Nota de contexto (no bloqueante): contenido con rostro humano visible suele
  tener mejor engagement en Instagram/TikTok — por eso se mantiene una fracción
  menor visible en vez de ir a 0%.

## Lo que NO cambia — sigue siendo criterio de aprobación binario

- **Resolución mínima 2000px en el lado corto.** El lote inicial de 33 (PNG,
  ~1024-1350px, generadas directamente en ChatGPT) no cumple esto — necesitan
  upscale antes de entrar al banco, o regenerarse a mayor resolución.
- Variación real de encuadre, entorno, luz, vestuario, postura (sección 3.3).
- Gorra placeholder neutra (gris, sin logo) — el lote de 33 ya lo cumple bien.
- Cada escena pasa el checklist binario antes de entrar al banco — ninguna
  "casi sirve".

## Estado del lote de 33 (`assets/escenas_base/01.png`...`33.png`)

Aprobado en variación de encuadre/entorno/vestuario/postura y en la gorra
placeholder consistente. Pendiente: subir resolución (upscale) antes de usarlas
en producción — no se descartan, se corrigen.
