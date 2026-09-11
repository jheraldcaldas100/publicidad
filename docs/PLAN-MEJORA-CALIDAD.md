# Plan de mejora del flujo de imágenes de Gorrolandia

Fecha: 2026-09-10. Alcance: diagnóstico y propuesta; no se modificó el código operativo ni se ejecutaron generaciones o evaluaciones de pago.

## Conclusión

Hay errores concretos del flujo que explican buena parte de los resultados. El generador exige copa blanca y visera negra para cualquier producto, y el evaluador incorpora esos mismos colores. Cambiar de modelo antes de corregir esto no permite medir su capacidad real. La meta propuesta es una imagen publicable en uno o dos intentos por escena; es una meta a validar, no una garantía.

Se revisaron las cinco capturas, el worker de producción, QA y reintentos, panel, base de datos, compositing y scripts de validación/comparativa. Se inspeccionó además la foto original de TEST-SKU-004. Los documentos históricos se trataron como antecedentes, no como instrucciones para ejecutar fases o gastar presupuesto. No se auditó la facturación del proveedor ni se reconstruyeron las respuestas originales de QA desde logs; las causas históricas no observables se señalan como hipótesis.

## Hallazgos y evidencia

| Prioridad | Hallazgo | Evidencia y efecto |
|---|---|---|
| P0 | Colores fijos para todos los SKU | `src/fase8_worker_ingesta.py`, `PROMPT_V3`: exige `WHITE` y `BLACK`. Contradice las fotos de productos verdes, negros o con visera marrón. |
| P0 | Evaluador sesgado con la misma respuesta | `src/fase6_qa_reintento.py`, `ITEMS`: define el color correcto como «base blanca, visera negra». Los 100 mostrados no demuestran fidelidad al SKU. |
| P0 | Comparaciones sin referencia | QA recibe solamente producto y resultado. No recibe la escena original, aunque evalúa si rostro, ropa y fondo permanecieron iguales. |
| P0 | Reintento contradictorio | Se conserva `PROMPT_V3` y se añaden correcciones. Pedir copiar el color real no elimina la orden anterior de usar blanco y negro. |
| P1 | Respuesta de QA sin validación estricta | `calcular_score()` usa `bool(valor)`: una cadena `"false"` se interpreta como verdadero. Es un riesgo comprobable del código; no hay evidencia de que explique estas respuestas concretas. |
| P1 | Identidad del producto incompleta | Forma y presencia de parche lateral se presuponen para cualquier SKU. En la foto revisada del verde no se observa parche lateral: no corresponde exigir uno sin evidencia. La forma tiene peso no crítico y puede fallar con 88 puntos y aprobarse. |
| P1 | Marca de agua mezclada con el producto | TEST-SKU-004 contiene marca de agua en el margen inferior. Las capturas muestran marcas sobre escena y visera. La transferencia desde la referencia es una explicación probable, no verificada mediante una prueba controlada. |
| P1 | QA validado sobre un solo producto | `fase6_validacion_clasificador.py` usa diez salidas del mismo SKU y acepta 8/10 coincidencias. No valida generalización entre colores ni controla específicamente aprobaciones falsas. |
| P1 | Tres escenas fijas por SKU | El worker usa 04, 09 y 29 siempre. No selecciona según ángulo, visibilidad del logo o compatibilidad con la foto disponible. |
| P1 | Costos incompletos | El worker registra `costo_usd=0.06` por generación como constante. QA no registra su consumo. No hay detalle de tokens, análisis, llamadas fallidas ni conciliación con facturación. El costo mostrado no es una medición completa. |
| P1 | Panel mezcla candidatos y fallos | Promedia todos los intentos por SKU; la aprobación es del trabajo completo. No selecciona una imagen final por escena ni impide incluir intentos defectuosos. |
| P2 | Trazabilidad insuficiente para repetir trabajos | Las generaciones se vinculan por SKU, no por trabajo; las rutas reutilizan SKU/escena/intento. Reprocesar puede mezclar registros o sobrescribir imágenes anteriores. |

El estado `listo_para_revision` no significa publicación automática: existe revisión humana. Sin embargo, se asigna incluso si se agotaron intentos sin aprobar QA, y el panel no presenta esa diferencia con suficiente claridad.

## Flujo propuesto

1. Validar fotos y ficha del SKU una sola vez.
2. Seleccionar una escena compatible y una referencia del producto con ángulo cercano.
3. Construir un único prompt coherente desde la ficha y las referencias.
4. Generar un candidato.
5. Evaluar identidad del producto y conservación de escena por separado.
6. Si cumple, seleccionar candidato y pasar a revisión humana. Si falla de forma corregible, realizar un único segundo intento. Si falta evidencia, detener esa escena antes de gastar otro intento.
7. Si el segundo intento falla, marcar «sin resultado apto» con motivo. Conservar ambos candidatos y su historial.
8. Crear formatos y colocar la marca gráfica desde el archivo oficial después de aceptar la imagen.

Dos intentos significan dos generaciones por combinación SKU/escena, no por cada recorte de salida. Tres escenas implican hasta seis generaciones; empezar el piloto con una por SKU evita multiplicar gasto prematuramente.

## Fase A — Corregir el contrato del producto y QA

Cambios previstos: `fase8_worker_ingesta.py`, `fase6_qa_reintento.py` y módulo compartido de ficha/prompts. Retirar las copias del prompt de scripts reutilizables o marcarlas explícitamente como históricas para evitar reintroducir el error.

- Ficha por SKU: colores de copa, paneles laterales, visera y botón; forma; logo/parche frontal; laterales observados; texto legible; referencias y zonas no observables. Puede partir de un análisis visual único y cacheado, con revisión humana de ambigüedades. No convertir suposiciones en atributos confirmados.
- Separar marca de agua editorial del diseño físico. Preferir fotos originales limpias; cuando la marca esté fuera del producto, preparar una referencia recortada conservando el original. Si invade el producto, solicitar el original limpio. Añadir la marca final de manera determinista.
- QA recibe producto, escena original y candidato, con roles explícitos y consistentes. Para detalles pequeños, añadir recortes relevantes dentro de la misma evaluación cuando el endpoint lo admita.
- Identidad: verificar cada componente de color, logo, texto, ubicación y forma contra el producto. Conservación: comparar persona/fondo contra la escena. Integración: ajuste, escala, luz y sombras.
- Usar estados estrictos `cumple`, `falla`, `no_verificable` y `no_aplica`, con evidencia breve por criterio. `no_aplica` solo con justificación de la ficha o geometría, nunca para ocultar una contradicción. Una zona oculta no exige inventar un parche visible.
- Un fallo de color, logo, elemento inventado, forma esencial o identidad de la persona bloquea el candidato. Un atributo crítico no verificable requiere revisión, no aprobación automática. La estética no compensa errores de producto.
- Validar esquema y tipos; respuesta malformada significa QA inválido. No regenerar una imagen por un error de lectura del evaluador. Registrar y limitar también las llamadas adicionales de QA.
- Quitar el significado de «porcentaje de calidad» al score: el 100 actual solo representa ocho respuestas afirmativas. Mostrar criterios y estado de aptitud; cualquier puntuación estética será secundaria.

Aceptación antes de llamar APIs: pruebas locales con respuestas simuladas verifican que color incorrecto y `"false"` no aprueban; desconocidos críticos bloquean; SKU verde no produce un prompt blanco/negro; un parche inexistente no se exige. Estas pruebas validan lógica, no capacidad visual.

## Fase B — Mejorar el primer intento

- Preparar vistas frontal y tres cuartos, y lateral cuando la escena muestre detalles que la referencia actual no enseña. Aprovechar las fotos existentes cuando basten; no exigir nuevas fotos a todo el catálogo.
- Catalogar escenas por orientación de cabeza, tamaño visible de gorra, oclusiones y dificultad de iluminación. Comenzar con ángulo cercano a la foto del SKU y luz clara. La selección debe reemplazar la lista fija universal.
- Usar un brief visual reutilizable: estilo editorial deseado, tamaño de la gorra en encuadre, luz, composición y ejemplos aceptables. La expectativa estética aún no está definida con referencias positivas; provisionalmente, priorizar fotografía comercial natural y producto protagonista.
- Establecer una sola fuente de verdad para colores y geometría. Evitar instrucciones absolutas como «pixel por pixel» para una gorra cuya perspectiva e iluminación cambian.
- Si persisten cambios fuera de la gorra, evaluar una ruta de edición con máscara o composición restringida. Verificar soporte real del endpoint antes de diseñar alrededor de esa función; no asumir que el actual admite máscaras.
- Separar el trabajo de catálogo (Pista A) del de persona (Pista B). La composición local preserva mejor el producto al no redibujarlo, pero aun requiere revisar recorte, escala y bordes; determinismo no equivale a calidad visual.

Ejemplo de prompt para TEST-SKU-004, sujeto a ficha verificada:

> Imagen 1: escena que se debe conservar. Imagen 2: referencia del producto. Sustituye únicamente la gorra de la persona por el producto de la imagen 2. Conserva la copa, visera y botón verde oscuro del producto, adaptando su iluminación a la escena sin cambiar su identidad cromática. Reproduce el parche frontal cuadrado oscuro con su símbolo claro y su ubicación; no añadas logos ni parches que no estén documentados en la referencia. Conserva la estructura y curvatura observables del producto. Ajusta perspectiva, escala y sombra de contacto a la cabeza. Mantén rostro, cabello, ropa y fondo de la imagen 1. Las marcas gráficas del margen de la foto de producto no forman parte de la gorra y no deben trasladarse a la escena.

## Fase C — Segundo intento con una decisión explícita

El segundo intento se autoriza dentro del presupuesto solo si hay una corrección concreta respaldada por referencias. Reconstruir el prompt sin contradicciones y enumerar todos los fallos críticos, no solo el comentario principal. Si el primer candidato es casi correcto, considerar edición localizada siempre que la ruta soporte esa operación. Si está muy desviado, partir de escena y producto originales. No realimentar indefinidamente una salida defectuosa.

Mantener máximo dos generaciones por escena, guardar ambas, y seleccionar solo un candidato que pase los controles. No escoger automáticamente el último o el de mayor promedio. Si faltan vistas o falla otra vez la identidad, solicitar mejor referencia/cambiar a una escena compatible en un trabajo posterior, sin lanzar un tercer intento oculto.

## Fase D — Costos, panel y recuperación

- Registrar `trabajo_id`, hashes de entradas, endpoint, versión de prompt y QA, respuesta completa estructurada, ID de solicitud del proveedor, parámetros efectivos, duración y candidato seleccionado.
- Registrar generación, análisis y QA por separado, incluidos errores facturables. Usar consumo/tarifa verificable cuando esté disponible; etiquetar estimaciones y conciliar con proveedor. No sustituir valores desconocidos por cero.
- Definir presupuesto por trabajo y por piloto; reservar costo antes de cada llamada. Cachear ficha y referencias por hash y versión. Una caché inválida por cambio de archivo no debe reutilizarse.
- Hacer reanudación por escena/intento: conservar pasos completados y recuperar solicitudes existentes cuando sea posible, sin volver a pagar por todas las escenas después de un error. Usar rutas únicas por trabajo.
- Panel: producto original y candidato lado a lado, acercamiento a la gorra, diferencias críticas, estado apto/revisión/sin resultado apto, costo acumulado real o estimado y selección por escena. Mantener intentos fallidos en historial. No aprobar un lote por promedio.

Indicador económico principal: costo total de generación + análisis + QA + fallos facturables dividido por imágenes aprobadas por una persona. Si no hay aprobadas, mostrar «sin imágenes útiles», nunca costo cero. Las adaptaciones de formato no cuentan como nuevos éxitos independientes de fidelidad.

## Validación acotada y elección de modelo

1. Reutilizar primero 20–30 resultados existentes, diversos en SKU/color/logo/escena, con etiquetas humanas. Incluir obligatoriamente las gorras verde, negra LIMA y crema/marrón de las capturas. Evaluarlas con QA corregido cuesta evaluación, pero no nuevas generaciones. Mantener una parte reservada sin usarla para ajustar prompts.
2. Puerta de QA: cero aprobaciones falsas en los errores críticos conocidos del conjunto reservado y al menos 90% de coincidencia global. Es un criterio del piloto; una muestra pequeña no demuestra error cero en producción.
3. Piloto de generación: cinco SKU representativos, una escena compatible por SKU, hasta dos intentos cada uno: máximo diez generaciones. Buscar al menos 4/5 aceptados en el primer intento y 5/5 como máximo en el segundo, con cero fallos críticos en los aceptados. Si falla, analizar el patrón antes de ampliar.
4. Solo después, si quedan fallos de síntesis, comparar el endpoint actual corregido con una alternativa sobre las mismas cinco parejas SKU/escena, mismo material y reglas. La alternativa tiene también máximo diez generaciones. Elegir por aprobación humana al primer intento y costo por imagen útil, sin prometer que una versión más cara gana.
5. Ampliar a 20–30 SKU únicamente tras pasar el piloto. Revisar aprobación humana, falsos positivos de QA, costo por imagen útil y media de intentos. Meta operativa inicial: ≥90% aceptados en hasta dos intentos y media ≤1,3 generaciones; ajustar con evidencia y presupuesto.

El código usa `fal-ai/nano-banana/edit`. La documentación oficial distingue esa ruta de `fal-ai/nano-banana-2/edit` y `fal-ai/nano-banana-pro/edit`; la etiqueta «nano_banana» del panel no sirve para identificar una versión nueva ni comparar prestaciones. No se ha comprobado superioridad de una alternativa para estas gorras.

Fuentes de API consultadas el 2026-09-10: [endpoint actual](https://fal.ai/models/fal-ai/nano-banana/edit/api), [Nano Banana 2](https://fal.ai/models/fal-ai/nano-banana-2/edit/api), [Nano Banana Pro](https://fal.ai/docs/model-api-reference/image-generation-api/nano-banana-pro). Verificar tarifas y parámetros al preparar el experimento; no usar costos históricos como precios vigentes.

## Orden de ejecución recomendado

Primero corregir colores, referencias y validación de QA; después ficha, preparación de referencias y selección de escena; luego reintento, presupuesto y panel; finalmente ejecutar el piloto acotado. Las fotos ideales en uno o dos intentos dependen también de referencias suficientes y compatibilidad de escena. Si se exige exactitud total del bordado en cualquier ángulo, considerar fotografía real del producto puesto o composición controlada para esos casos.

La siguiente implementación debe entregar primero cambios locales verificables sin llamadas pagadas. El piloto se prepara con entradas concretas, límite de llamadas y estimación completa antes de ejecutarlo. Este documento no inicia ni pausa el worker existente.
