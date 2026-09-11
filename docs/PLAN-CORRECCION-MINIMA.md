# Plan de corrección mínima — pipeline de generación/QA de gorras (Gorrolandia)

## Contexto del proyecto

Proyecto Python de un solo desarrollador/operador. Dos procesos propios
corren en paralelo: el worker de polling de Fase 8 y el panel de
Streamlit — ambos acceden al mismo SQLite (`output/gorrolandia.db`). Genera
imágenes de marketing para una tienda de gorras: Pista A = compositing
determinista local (recorte + fondo, sin IA); Pista B = edición por IA
(`fal-ai/nano-banana/edit` vía fal.ai) que reemplaza la gorra que lleva
puesta una persona en una foto de escena por la gorra real de un SKU. Un
clasificador de visión (`google/gemini-2.5-flash` vía
`openrouter/router/vision` en fal.ai) califica cada resultado contra un
checklist de 8 ítems y dispara un reintento dirigido si falla. Un worker
hace polling de una carpeta de Google Drive **privada, compartida solo con
la cuenta de servicio del propio dueño de la tienda** (no es un endpoint
público) para ingestar SKU nuevos.

**Estado real verificado de la base de datos al momento de este plan:** 10
trabajos (ids 3-12, uno por SKU, sin ambigüedad), 69 filas en
`generaciones` asociadas a esos SKU (30 `compositing_local` de Pista A + 39
`nano_banana` de Pista B), estados de trabajo: 1 `aprobado`, 9
`listo_para_revision`.

## Problema confirmado (evidencia, no hipótesis)

Se auditó el pipeline contra un SKU real (`TEST-SKU-004`, gorra **verde
olivo** con un parche pequeño de solo un ícono, sin texto, sin parche
lateral) y se encontraron 4 bugs P0 confirmados con evidencia directa
(código + imágenes generadas), más su propagación directa (encontrada en
cuatro rondas de revisión externa y verificada en código/base de datos en
cada caso):

1. **`PROMPT_V3`** — duplicado **tres** veces (`src/fase7_poblar_registro.py`,
   `src/fase8_worker_ingesta.py`, `src/fase6_demo_reintento.py`, verificado
   en código) hardcodea *"the cap's front crown panels must end up
   WHITE... The visor/bill must be BLACK"* para **cualquier** SKU. Las 5
   salidas generadas para `TEST-SKU-004` (verde) volvieron blancas con
   visera negra.
2. **El clasificador de QA tiene el mismo sesgo hardcodeado**:
   `item_1_color` en `src/fase6_qa_reintento.py` dice literalmente *"(base
   blanca, visera negra)"*. Confirmado en logs reales: para `TEST-SKU-004`
   escena 29, el intento 1 detectó correctamente el error de color (score
   62), pero el intento 2 — con la MISMA salida incorrecta — se aprobó con
   score 100.
3. **QA nunca recibe la escena original** — `evaluar_calidad(ruta_original,
   ruta_generada)` siempre pasa la foto del producto, nunca la escena. Los
   ítems 4 (rostro) y 5 (escena) piden verificar algo contra una imagen
   que el modelo nunca vio.
4. **El reintento es contradictorio** — concatena una corrección de color
   sobre el mismo `PROMPT_V3` que exige blanco/negro.

**Bug adicional de la misma clase (confirmado en código):** `CRITICAL SHAPE
RULE` e `item_2_logo`/`item_3_parche` también asumen una construcción de
producto fija. `TEST-SKU-004` (ícono sin texto, sin parche lateral)
fallaría estos ítems por razones ilegítimas incluso después de arreglar
solo el color.

**Bugs de propagación de la truthiness cruda (confirmados en código):**
`calcular_score()`, `construir_prompt_reintento()`, y la
list-comprehension dentro de `generar_con_reintento()` usan
`bool(valor)`/`not valor` crudos — el string `"false"` se evalúa como
verdadero en Python en los tres lugares.

**Consecuencia:** el cierre reportado de la Fase 8 ("10 SKU reales
aprobados") es inválido para cualquier SKU cuyo color, logo o construcción
real no coincida con el patrón asumido. El trabajo actualmente en estado
`aprobado` fue aprobado por una persona que confiaba en scores calculados
por el clasificador sesgado.

## Decisión de alcance

Existe un plan más amplio (`PLAN-MEJORA-CALIDAD.md`) que además propone
ficha estructurada por SKU, catálogo de escenas por dificultad, reserva de
presupuesto, reconciliación de costos con el proveedor, estados
`no_verificable`/`no_aplica`, panel con diffs, y una máquina de estados de
resumibilidad completa. Se decidió no implementar eso todavía. Este plan
cubre los bugs P0 confirmados + su propagación directa + los huecos de
correctitud encontrados en cuatro rondas de revisión externa sobre estos
mismos cambios. Se declina explícitamente protección contra decompression
bombs (justificado por modelo de amenaza) y la máquina de estados de
resumibilidad completa (ver "Fuera de alcance").

## Conceptos clave (para resolver contradicciones de rondas anteriores)

- **`VERSION_QA`** — constante de texto (ej. `"v2_generic_2026-09-10"`) que
  identifica el prompt/esquema de QA corregido de este plan. Toda fila de
  `evaluaciones_qa` se etiqueta con la versión que la produjo. **Vive en
  `src/prompts.py`, no en `fase6_qa_reintento.py`** (corrige riesgo real de
  import circular: `db.py` necesita `VERSION_QA` como valor por defecto de
  `ultima_evaluacion_vigente()`, y `fase6_qa_reintento.py` necesita
  funciones de `db.py` para auditarse a sí mismo — si `VERSION_QA` viviera
  en `fase6_qa_reintento.py`, `db.py` tendría que importar de un módulo
  que a su vez importa `db.py`. `prompts.py` no importa nada de ninguno de
  los dos, así que ambos pueden importar `VERSION_QA` de ahí sin ciclo.
- **`evaluaciones_qa`** es el único lugar que crece con cada evaluación
  (normal, reintento, re-QA histórica, o `qa_error`) — tabla de auditoría,
  nunca se sobrescribe.
- **`generaciones.score_qa` / `.problema`** quedan como snapshot congelado
  de lo que ya existe hoy en las 69 filas históricas — nunca se
  sobrescriben. **A partir de este cambio, las filas nuevas ya no llenan
  estas dos columnas en absoluto** (quedan `NULL`/`""`): `evaluaciones_qa`
  pasa a ser la única fuente de verdad para todo lo generado de aquí en
  adelante (detalle de la nueva secuencia de escritura en el punto 3).
- **Qué generación representa una escena, cuando hay varios intentos**
  (faltaba especificar — corrige riesgo real: una escena con el intento 1
  aprobado y el intento 2 en `qa_error` podía leerse como "tiene una
  evaluación completa" si algo consultaba "existe alguna evaluación
  vigente completa para cualquier intento de esta escena", cuando el
  intento 2 es el artefacto real vigente y el 1 ya no representa nada):
  para cada `(trabajo_id, escena_id)`, **la generación que cuenta es
  siempre la de intento máximo** — todo lo demás (regla de estado,
  `aprobar_trabajo()`, reconciliación, panel, agotamiento de QA) se basa
  en la evaluación vigente de esa generación específica, nunca de un
  intento anterior de la misma escena.
- **Regla única de estado de trabajo** (aplica igual a trabajos nuevos y a
  los 10 históricos): un trabajo pasa a `listo_para_revision` si **al
  menos una** de sus escenas de Pista B tiene una evaluación vigente
  (`evaluaciones_qa`, `VERSION_QA` actual) completa (no `qa_error`); pasa a
  `error` solo si **todas** sus evaluaciones vigentes son `qa_error`. Esto
  decide si el trabajo es **visible** en el panel, no si se puede
  aprobar.
- **Regla de bloqueo del botón "Aprobar":** el panel deshabilita
  visualmente el botón "Aprobar" mientras **alguna** de las escenas de
  Pista B esperadas para ese trabajo no tenga una evaluación vigente
  **completa** (es decir, QA terminó de opinar — no quedó en `qa_error` ni
  sin generar) — muestra en su lugar "Faltan N escenas por evaluar, no se
  puede aprobar todavía". **"Completa" no significa "aprobada por QA"**:
  un humano puede aprobar un trabajo cuya evaluación automática dio
  `aprobado=0`, viendo la advertencia correspondiente — bloquear eso
  convertiría al clasificador en la decisión final en vez del humano, que
  es justo lo que el panel existe para evitar. "Rechazar" sigue disponible
  siempre.
- **`aprobar_trabajo()` transaccional — la validación real vive en la
  base, no en la UI** (corrige riesgo real de carrera: el chequeo visual
  solo lee datos al momento de dibujar la página; entre ese render y el
  click, otra pestaña del panel o un ciclo de reconciliación puede cambiar
  la realidad). **El snippet de la ronda anterior tenía dos bugs reales
  además de la carrera que pretendía arreglar:** (a) solo contaba como
  "incompleta" una escena que YA tenía fila en `generaciones` — un
  trabajo al que directamente le faltara una de las 3 escenas esperadas
  (nunca se generó) pasaba con `incompletas = 0` y se aprobaba igual; (b)
  el SQL no es ejecutable tal cual: `existe_evaluacion_vigente_completa(...)`
  se usaba como si fuera una función SQL registrada cuando es un
  concepto de Python, `VERSION_QA` aparecía como si fuera una columna en
  vez de un parámetro, y `SELECT g.id, MAX(g.intento) ... GROUP BY
  g.escena_id` depende del comportamiento no portable de SQLite para
  asociar `g.id` con el intento máximo (nada garantiza que sea así).
  Reescrito con lógica explícita en Python, iterando la lista de escenas
  esperadas en vez de intentar una sola consulta agregada:
  ```python
  # ESCENAS_PRODUCCION vive en src/prompts.py (no en el worker ni en db.py)
  # para que el panel pueda importarla sin depender del modulo del worker
  from prompts import ESCENAS_PRODUCCION, VERSION_QA

  # Codigos de razon posibles - strings simples, mismo estilo que ya usa
  # el proyecto para `trabajos.estado` (no se introduce un dataclass/enum
  # nuevo para esto, para no romper esa convencion existente):
  #   "aprobado"            -> exito
  #   "estado_invalido"     -> el trabajo ya no estaba en listo_para_revision
  #   "escena_faltante"     -> una escena esperada nunca se genero
  #   "qa_incompleto"       -> falta evaluacion vigente, o quedo en qa_error
  #   "artefacto_invalido"  -> un archivo (Pista A o B) esta perdido o corrupto
  def aprobar_trabajo(trabajo_id) -> str:
      con = conectar()
      con.execute("BEGIN IMMEDIATE")
      try:
          fila = con.execute(
              "SELECT estado FROM trabajos WHERE id = ?", (trabajo_id,)
          ).fetchone()
          if fila is None or fila[0] != "listo_para_revision":
              con.rollback()
              return "estado_invalido"

          # Pista A: las 3 formatos deben existir en disco y decodificar -
          # corrige hueco real: la reconciliacion de QA solo revisita
          # trabajos con evaluaciones incompletas, asi que un archivo que
          # se corrompe o se borra DESPUES de que el trabajo ya llego a
          # listo_para_revision con QA completo nunca se vuelve a chequear.
          # El panel de hoy simplemente omite la imagen que falta al
          # mostrarla, sin bloquear nada - aprobar_trabajo() es el unico
          # lugar donde de verdad importa evitar aprobar algo roto.
          formatos_pista_a = con.execute("""
              SELECT ruta_output FROM generaciones
              WHERE trabajo_id = ? AND modelo_ia = 'compositing_local'
          """, (trabajo_id,)).fetchall()
          if len(formatos_pista_a) != 3:
              con.rollback()
              return "artefacto_invalido"  # falta un formato de Pista A por completo
          for (ruta,) in formatos_pista_a:
              if not archivo_es_imagen_valida(ruta):
                  con.rollback()
                  return "artefacto_invalido"  # formato de Pista A perdido o corrupto

          for escena in ESCENAS_PRODUCCION:
              generacion = con.execute("""
                  SELECT id, ruta_output FROM generaciones
                  WHERE trabajo_id = ? AND modelo_ia = 'nano_banana' AND escena_id = ?
                  ORDER BY intento DESC LIMIT 1
              """, (trabajo_id, escena)).fetchone()
              if generacion is None:
                  con.rollback()
                  return "escena_faltante"  # la escena esperada nunca se genero

              generacion_id, ruta_output = generacion
              if not archivo_es_imagen_valida(ruta_output):
                  con.rollback()
                  return "artefacto_invalido"  # el artefacto vigente de esta escena esta perdido o corrupto

              evaluacion = con.execute("""
                  SELECT aprobado, qa_error FROM evaluaciones_qa
                  WHERE generacion_id = ? AND version_prompt_qa = ?
                  ORDER BY id DESC LIMIT 1
              """, (generacion_id, VERSION_QA)).fetchone()
              # Solo se exige que QA haya terminado de opinar (qa_error=0),
              # NO que haya dicho "aprobado". Un humano en el panel puede
              # anular un fallo automatico de QA - ese es el sentido de
              # tener revision humana como ultimo paso (ver Fase 6/8: "un
              # humano aprueba/rechaza antes de publicar"). Bloquear la
              # aprobacion humana ante un score bajo pero completo
              # convertiria a QA en la decision final, no en un insumo
              # para la decision final.
              if evaluacion is None or evaluacion[1] == 1:
                  con.rollback()
                  return "qa_incompleto"  # sin evaluacion vigente, o QA quedo en qa_error

          cur = con.execute(
              "UPDATE trabajos SET estado = 'aprobado' WHERE id = ? AND estado = 'listo_para_revision'",
              (trabajo_id,)
          )
          con.commit()
          return "aprobado" if cur.rowcount == 1 else "estado_invalido"
      except Exception:
          con.rollback()
          raise
      finally:
          con.close()
  ```
  Cada `SELECT` está parametrizado (nunca interpolación de string), y la
  condición `AND estado = 'listo_para_revision'` en el `UPDATE` final es
  la verificación atómica real — todo lo anterior en la transacción es
  para decidir si vale la pena llegar a ese `UPDATE`, pero el `UPDATE`
  mismo es lo que realmente previene la carrera.

  **`archivo_es_imagen_valida(ruta)`** es el mismo helper compartido que
  ya usan el guard de Pista A/B y la validación de descargas (`Path(ruta).exists()`
  + `PIL.Image.open(ruta).verify()`) — no una reimplementación nueva. Se
  agrega aquí porque es el único punto real donde importa detectar
  corrupción/borrado ocurrido **después** de que el trabajo ya llegó a
  `listo_para_revision` con QA completo: la reconciliación de QA (punto 7)
  solo revisita trabajos con evaluaciones incompletas, así que un archivo
  que se corrompe o se borra después de eso nunca se vuelve a chequear
  hasta este momento. El panel hoy simplemente omite la imagen que falta
  al mostrarla, sin bloquear nada — por eso la validación real tiene que
  vivir en `aprobar_trabajo()`, no solo en la UI.

  **El panel elige el mensaje directamente a partir del código de razón
  devuelto** (corrige inconsistencia real de la ronda anterior: la firma
  decía `-> bool`, que no puede distinguir "el trabajo cambió" de "un
  archivo se corrompió" — y el panel necesitaba mostrar mensajes
  distintos para cada caso, además de que la prueba correspondiente ya
  esperaba ese mensaje específico. En vez de que el panel vuelva a
  consultar la base para adivinar por qué falló —una segunda consulta no
  atómica, que podría ver un estado distinto al que realmente causó el
  `False`—, usa directamente el string que ya devolvió la única llamada
  transaccional):
  - `"aprobado"` → éxito, refresca la vista normalmente.
  - `"estado_invalido"` / `"escena_faltante"` / `"qa_incompleto"` →
    "el trabajo cambió mientras revisabas, refresca la página".
  - `"artefacto_invalido"` → "un archivo de este trabajo se perdió o
    corrompió después de la revisión — no se puede aprobar, contacta a
    quien mantiene el sistema". No se resuelve solo con refrescar; el
    trabajo se queda visible en `listo_para_revision` para que quede claro
    que necesita reparación manual, en vez de desaparecer o aprobarse solo.

  Se aplican las mismas verificaciones de estado (no las de archivos, que
  no aplican) a "Rechazar" y a "Reintentar" — ninguna acción del panel
  hace un `UPDATE` incondicional.

## Cambios propuestos

### 1. Prompt de generación — módulo compartido, genérico, sin construcción fija

**Archivo nuevo:** `src/prompts.py`, única fuente de verdad para
`PROMPT_V3`, `VERSION_QA` (ver "Conceptos clave" — vive aquí, no en
`fase6_qa_reintento.py`, para evitar un import circular con `db.py`), **y
`ESCENAS_PRODUCCION`** (la lista `["04", "09", "29"]`, hoy definida solo
dentro de `fase8_worker_ingesta.py` — se mueve aquí porque
`aprobar_trabajo()` en `db.py` también necesita saber cuáles son las
escenas esperadas de un trabajo, sin importar el módulo del worker):

```
CRITICAL COLOR RULE: match the crown and visor colors EXACTLY as shown in
image 2 (the real product photo) - whatever those colors are. Do NOT use
the color of the cap currently worn in image 1 for the crown or visor.

CRITICAL BRANDING RULE: reproduce exactly whatever branding appears on
image 2 - whether it is embroidered text, an icon-only mark, both, or a
side patch - matching its exact content, style, and position. Do NOT add
a side patch, text, or icon that is not visible in image 2. Do NOT omit
one that is visible in image 2.

CRITICAL SHAPE RULE: match the crown structure (panel count and
stiffness) and the visor/brim curvature exactly as shown in image 2 -
whatever that construction is. Do NOT default to any specific style not
shown in image 2.
```

Los 2 puntos de uso vigentes (`fase8_worker_ingesta.py`,
`fase6_demo_reintento.py`) importan desde `src/prompts.py`; se elimina la
copia local de cada uno. **`fase7_poblar_registro.py` no se migra, se
retira** (ver más abajo) — moot para él, nunca más se ejecuta con el
prompt viejo ni con el nuevo.

### 2. QA — 3 imágenes, criterios comparativos, validación de esquema estricta

**Archivo:** `src/fase6_qa_reintento.py`

- `evaluar_calidad(ruta_producto, ruta_escena, ruta_generada, generacion_id,
  modelo_qa=MODELO_VISION, version_prompt_qa=VERSION_QA)` — 3 imágenes
  nombradas explícitamente en el prompt. **Recibe `generacion_id`
  directamente y audita internamente CADA llamada al proveedor** (corrige
  hueco real: si el primer intento de parseo falla y el reintento interno
  de QA sí funciona, antes se perdía el registro y el costo de la llamada
  fallida — ahora cada llamada, exitosa o no, inserta su propia fila en
  `evaluaciones_qa` vía `registrar_evaluacion_qa`). Devuelve el resultado
  final (el de la llamada que terminó definiendo la evaluación) para que
  el llamador decida el flujo de reintento de generación.

  **Límite honesto de esta garantía (no se resuelve en este plan, con
  justificación):** "cada llamada se audita" es cierto salvo por una
  ventana muy angosta — si el proceso muere o la escritura a SQLite falla
  en el instante exacto entre que el proveedor (de generación o de QA) ya
  respondió y devolvió éxito, y el `INSERT` correspondiente confirma, esa
  llamada pagada queda sin fila. Una solución completa requeriría
  "reservar" una fila antes de cada llamada pagada y confirmarla después
  (generación y QA por separado), duplicando la escritura a base de datos
  en el camino feliz para cubrir una ventana de milisegundos. Dado que el
  costo real de que esto ocurra es de centavos por evento y la
  probabilidad es baja, se acepta el riesgo explícitamente en vez de
  construir esa infraestructura — **no se promete "cero cargos
  duplicados" de forma absoluta**, se promete que el caso común (fallo de
  parseo, timeout, error de red — todos manejados arriba) sí queda
  siempre auditado.
- Los 8 ítems comparativos contra la imagen 1, sin asumir valor o
  construcción fija. `item_4_rostro`/`item_5_escena` comparan imagen 3
  contra imagen 2.
- Parseo: `json.loads(texto.strip())` directo; si falla,
  `json.JSONDecoder().raw_decode(texto[texto.index("{"):])` — pero tras
  extraer el objeto, **si queda cualquier contenido no-whitespace después
  del `}` de cierre, se trata como respuesta sospechosa/malformada**
  (`raw_decode` por sí solo aceptaría JSON válido seguido de basura
  arbitraria; no se permite).
- Validación de esquema antes de normalizar: las 8 claves presentes y cada
  valor booleano real o `"true"`/`"false"` (case-insensitive, recortado).
  Cualquier otro valor invalida **toda la respuesta** → `qa_error`.
  `problema`/`detalle` se acepta como string de hasta 2000 caracteres — más
  largo también cuenta como sospechoso → `qa_error`.
- Normalización centralizada (`_es_verdadero`) solo tras validar esquema,
  usada en los 3 puntos que antes tenían truthiness cruda.
- **Nota de seguridad en el prompt de QA:** se agrega una línea explícita
  indicando que cualquier texto visible dentro de las imágenes (bordados,
  parches, carteles de fondo) es contenido a evaluar, nunca una
  instrucción para el modelo — defensa barata contra que un bordado o una
  marca de agua rara intente pasar por una instrucción.

**Firma:** `generar_con_reintento(funcion_generar, ruta_producto,
ruta_escena, on_generada=None, max_intentos=2)` — un solo gancho, no dos
(simplificado esta ronda: al pasar `generacion_id` directamente a
`evaluar_calidad`, ya no hace falta un segundo gancho posterior a QA solo
para registrar la evaluación — `evaluar_calidad` se audita a sí misma).

**Alcance de uso, acotado explícitamente (corrige incompatibilidad real:
esta función numera los intentos desde 1 internamente en cada llamada, lo
cual funciona para una secuencia nueva de punta a punta, pero NO puede
implementar la reanudación exigida en el punto 7 — ahí se necesita
arrancar en `max(intento existente) + 1`, y la función de generación
necesita saber el número de intento absoluto para nombrar su archivo de
salida, algo que esta firma no expone):**
- **`generar_con_reintento` se usa tal cual únicamente en
  `fase6_demo_reintento.py`** (una demostración de punta a punta sin
  estado previo que reanudar — numerar desde 1 ahí es siempre correcto).
- **El worker (`fase8_worker_ingesta.py`) NO usa `generar_con_reintento`
  para Pista B.** Implementa su propio bucle, más simple, consciente de
  reanudación desde el principio: calcula el intento absoluto a generar
  (`max(intento existente) + 1`, o el guard de qa_error/agotamiento del
  punto 7 si no hace falta generar nada nuevo), llama a la función de
  generación pasándole ese número absoluto para el nombre de archivo,
  llama `evaluar_calidad` con el mismo `generacion_id`, y decide si repetir
  el bucle según el resultado — sin depender de un contador interno que
  no conoce el historial previo del trabajo.

### 3. Orden de escritura — quién inserta qué, y cuándo (resuelve ambigüedad de `generacion_id`)

**Archivo:** `src/db.py`

- **`registrar_generacion()` pasa a devolver `cursor.lastrowid`** (hoy no
  devuelve nada). Esto es lo único que permite que exista un
  `generacion_id` antes de poder registrar una evaluación sobre esa fila.
- **Orden correcto, en un solo gancho (simplificado respecto a la ronda
  anterior):**
  - `on_generada(ruta_generada, intento) -> generacion_id`: se llama
    **inmediatamente después de generar la imagen, antes de llamar a
    `evaluar_calidad`**. Hace `registrar_generacion(...)` (con
    `score_qa=NULL`, `problema=""`) y devuelve el id — así la generación
    queda registrada pase lo que pase con QA después.
  - `generar_con_reintento` llama `evaluar_calidad(..., generacion_id=...)`
    inmediatamente después — y como `evaluar_calidad` ya audita cada
    llamada al proveedor internamente (punto 2), no hace falta un segundo
    gancho: el registro de la evaluación ya ocurrió cuando
    `evaluar_calidad` devuelve.
  - Si no se pasa `on_generada` (caso de `fase6_demo_reintento.py` y
    `fase6_validacion_clasificador.py`, que no necesitan persistir nada),
    tampoco se llama `evaluar_calidad` con `generacion_id` — se usa un
    modo "solo evaluar, sin auditar" (`generacion_id=None` desactiva la
    escritura en `evaluaciones_qa` dentro de `evaluar_calidad`). No se
    escribe ninguna fila en ningún caso — resuelve el caso de los scripts
    de demo/validación que no crean trabajos reales.
- **`generaciones.score_qa`/`.problema` dejan de llenarse en filas nuevas**
  a partir de este cambio — quedan `NULL`/`""` siempre para todo lo
  generado de aquí en adelante, porque `evaluaciones_qa` es la única
  fuente de verdad para esas filas. Los valores que ya tienen esas
  columnas en las 69 filas históricas (Fases 2/3/6/7/8-pre-fix) **no se
  tocan** — siguen ahí como snapshot congelado de lo que dijo el
  clasificador sesgado en su momento, nunca más se vuelven a escribir.
- **`generar_con_reintento()` no toca la base directamente** más que a
  través de `on_generada` — `evaluar_calidad` es quien escribe
  `evaluaciones_qa` (punto 2), no `generar_con_reintento`.

**Esquema completo de `evaluaciones_qa` (faltaba especificar — la versión
anterior solo nombraba campos sueltos y perdía los 8 booleanos por ítem,
necesarios para poder reconstruir la corrección dirigida al reanudar):**

```sql
CREATE TABLE IF NOT EXISTS evaluaciones_qa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generacion_id INTEGER NOT NULL REFERENCES generaciones(id),
    timestamp TEXT NOT NULL,
    modelo_qa TEXT NOT NULL,
    version_prompt_qa TEXT NOT NULL,
    score INTEGER,
    aprobado INTEGER NOT NULL DEFAULT 0,
    qa_error INTEGER NOT NULL DEFAULT 0,
    detalle TEXT,
    resultado_json TEXT,
    costo_usd REAL NOT NULL DEFAULT 0.0
);
```

`resultado_json` guarda `json.dumps()` de los 8 booleanos normalizados
(`item_1_color`..`item_8_estructura`) — sin esto, reanudar un reintento
dirigido tras un corte no puede saber cuáles ítems específicos fallaron,
solo el score agregado.

```python
def registrar_evaluacion_qa(generacion_id, resultado_qa, modelo_qa, version_prompt_qa, costo_usd):
    """Unico punto de insercion en evaluaciones_qa. Llamado internamente
    por evaluar_calidad() en cada llamada al proveedor (exitosa o no), y
    por la re-QA historica."""
```

- Si `resultado_qa.get("qa_error")`: inserta con `qa_error=1`, `score=NULL`,
  `aprobado=0`, `detalle=resultado_qa["detalle"][:2000]` (largo máximo —
  ver punto 10 nuevo sobre parseo), `resultado_json=NULL`.
- Si no: inserta `score`, `aprobado`, `detalle=problema[:2000]` (puede ser
  vacío), `resultado_json=json.dumps({items normalizados})`.
- **Nunca** modifica `generaciones.score_qa`/`.problema`.

**`ultima_evaluacion_vigente(generacion_id, version=VERSION_QA)`** —
devuelve la fila de `evaluaciones_qa` más reciente para esa versión,
ordenando por `id DESC` (no por timestamp, que solo tiene precisión de
segundo y puede empatar). Devuelve `None` si no hay ninguna para esa
versión.

**Política explícita de respaldo (sin ambigüedad — antes dejaba "decidir
al llamador", ahora es una sola regla):**
- Para cualquier fila de `generaciones` con `trabajo_id IS NOT NULL`
  (pasó por el worker de Fase 8): si `ultima_evaluacion_vigente()`
  devuelve `None`, se trata como **"QA pendiente"** — nunca se muestra
  `generaciones.score_qa` como si fuera vigente, nunca cuenta como
  aprobado para ningún guard de idempotencia. El score congelado de esa
  fila es precisamente el que el clasificador sesgado calculó — mostrarlo
  como actual reintroduciría el bug que este plan corrige.
- Para filas con `trabajo_id IS NULL` (Fases 2/3/6/7, que nunca pasarán
  por re-QA): el panel y los reportes pueden mostrar
  `generaciones.score_qa` únicamente con una etiqueta explícita
  ("resultado histórico, no verificado con el clasificador corregido").
- Ningún guard de idempotencia (punto 7) cae nunca al score congelado,
  sin excepción.

**Invariante de consulta única (corrige riesgo real: una query que solo
busca "¿existe alguna evaluación aprobada?" puede colarse con una
aprobación vieja seguida de un fallo más reciente):** ningún código —
guards, panel, cálculo de estado de trabajo, reportes — consulta
`evaluaciones_qa` con una condición tipo "existe alguna fila con
`aprobado=1`". **Todo pasa por `ultima_evaluacion_vigente()`** (que ya
ordena por `id DESC LIMIT 1`) y decide sobre esa única fila devuelta,
nunca sobre el conjunto completo del historial de esa generación.

### 4. `qa_error` — comportamiento explícito de principio a fin, incluidas fallas de transporte

- **Cada llamada real al proveedor (`fal_client.subscribe(...)`) se envuelve
  en su propio `try/except`** — un timeout, un fallo de autenticación, o
  un error de red antes de que el proveedor devuelva nada se tratan igual
  que un JSON inválido: cuentan hacia el límite del punto 7, se sanitizan
  (punto 10) antes de guardarse, y se registran como fila `qa_error`.
  **Dos fronteras de excepción distintas, no una sola (corrige riesgo
  real: si el `try/except` de arriba también envolviera la llamada a
  `registrar_evaluacion_qa`, un fallo de escritura a SQLite —por ejemplo
  "database is locked" tras agotarse el `busy_timeout`— se interpretaría
  como "el proveedor falló" y dispararía una llamada pagada de más,
  cuando el problema real es local y no tiene nada que ver con el
  proveedor):**
  1. Fallo del proveedor o de parseo de su respuesta → se captura, se
     registra como `qa_error` vía `registrar_evaluacion_qa`, y el flujo
     normal de reintento de QA aplica.
  2. **Fallo al ejecutar `registrar_evaluacion_qa` en sí** (para
     cualquiera de los dos casos: registrar un resultado completo, o
     registrar el `qa_error` del punto 1) → **no se captura ni se
     reinterpreta como fallo del proveedor**. Se deja propagar tal cual.
     El llamador (el worker) no reintenta la llamada pagada al verla —
     la excepción sube hasta el `try/except` de `procesar_trabajo`, que
     marca el trabajo en `error` (correcto: es un problema real de
     infraestructura local, no algo que reintentar automáticamente
     gastando más dinero).
- **Límite simple, en filas, no en "invocaciones" (simplificado esta
  ronda — corrige ambigüedad real: contar "invocaciones de
  `evaluar_calidad`" requeriría campos nuevos en el esquema para agrupar
  qué filas pertenecen a la misma llamada externa; en vez de eso, el
  límite es directamente sobre filas persistidas):** antes de **cada**
  intento de llamar al proveedor — incluido el reintento interno de
  `evaluar_calidad` y cualquier intento disparado por la reconciliación
  del punto 7 — se cuentan las filas ya existentes en `evaluaciones_qa`
  para **`(generacion_id, version_prompt_qa=VERSION_QA)`**, no solo
  `generacion_id` a secas (corrige bug real de la ronda anterior: contar
  todas las filas sin filtrar por versión significa que si alguna vez se
  corrige el prompt/esquema de QA y sube `VERSION_QA`, una generación que
  ya agotó sus 6 filas bajo la versión vieja quedaría inevaluable para
  siempre bajo la versión nueva — el límite tiene que resetearse por
  versión, ese es justamente el propósito de tener `version_prompt_qa`).
  Si ya hay **6** o más filas para esa combinación exacta, no se hace la
  llamada — se trata como agotado sin gastar una séptima *bajo esa
  versión*. No hace falta un campo `origen`/`invocacion_id` nuevo: el
  conteo crudo de filas, ya filtrado por versión, acota el gasto real sin
  importar cómo se agrupen lógicamente las llamadas.
- Si tras el reintento interno (o por el límite de arriba) no hay un
  resultado válido: `evaluar_calidad` devuelve
  `{"qa_error": True, "detalle": "..."}` — sin `score` ni `aprobado`. Ya
  quedó registrado vía `registrar_evaluacion_qa` como parte de la llamada
  misma (punto 2), no hace falta un registro adicional aquí.
- Con `qa_error`, no se interpreta como aprobado ni como fallo — se
  detiene el reintento de esa escena, no se regenera imagen (aplica igual
  al bucle propio del worker que al de `generar_con_reintento` en el
  script de demo — es la misma regla, solo que implementada en dos
  lugares distintos según el punto anterior).
- `procesar_trabajo`: conserva la imagen, continúa con la siguiente
  escena. El estado final del trabajo sigue la regla única (ver
  "Conceptos clave").
- Panel: filas cuya evaluación vigente es `qa_error` se muestran con marca
  visual distinta ("⚠️ QA incompleto"); si además ya se llegó al límite de
  6 filas sin éxito, se muestra como agotada (punto 7).

### 5. `inicializar_db()` — esquema idempotente, separado del backfill de una sola vez

**Archivo:** `src/db.py`

**`conectar()` activa las foreign keys en cada conexión** (SQLite no las
aplica por defecto aunque estén declaradas con `REFERENCES` — confirmado,
las de `evaluaciones_qa.generacion_id` y `generaciones.trabajo_id` no se
estaban validando):

```python
def conectar():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    return con
```

**`DB_PATH` pasa a ser sobreescribible por variable de entorno (corrige
hallazgo real de Codex, ronda 4: las pruebas de concurrencia/subproceso
del worker necesitan un proceso hijo real —`filelock`, `inicializar_db()`
concurrente—, y en Windows esos subprocesos se crean con `spawn`, que
**reimporta `db.py` desde cero** en el proceso hijo; un `monkeypatch` en
el proceso de pytest padre no viaja a ese hijo, así que sin este cambio
las pruebas de subproceso seguirían tocando la base de datos real de
producción):**
```python
import os

DB_PATH = Path(os.environ.get("GORROLANDIA_DB_PATH", str(ROOT / "output" / "gorrolandia.db")))
```
El código de producción no pasa esta variable nunca (usa el valor por
defecto real); solo el arnés de pruebas la fija antes de lanzar cualquier
subproceso, para que el hijo la lea al importar `db.py` de cero.

```python
def inicializar_db():
    """Idempotente. Crea tablas/columnas/indices que falten. Segura en base
    nueva o existente. NO ejecuta el backfill historico (ver punto 6) -
    eso es una accion separada de una sola vez, no parte del arranque."""
    con = conectar()
    con.executescript(ESQUEMA)  # incluye trabajo_id y trabajos.drive_carpeta ya en los CREATE TABLE para bases nuevas
    _migrar_columna_si_hace_falta(con, "generaciones", "trabajo_id", "INTEGER REFERENCES trabajos(id)")
    _migrar_columna_si_hace_falta(con, "trabajos", "drive_carpeta", "TEXT")
    # el indice unico se crea DESPUES de la migracion de trabajo_id, nunca
    # dentro de ESQUEMA (corrige hallazgo real de Codex, ronda 4: ESQUEMA
    # se ejecuta primero contra una base que puede ser la real existente,
    # donde generaciones.trabajo_id todavia no existe hasta que la linea
    # de arriba termina de migrarla - crear el indice antes de esa migracion
    # fallaria con "no such column: trabajo_id" sobre cualquier base real)
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_generaciones_intento
        ON generaciones(trabajo_id, modelo_ia, escena_id, intento)
        WHERE trabajo_id IS NOT NULL
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_generaciones_trabajo ON generaciones(trabajo_id, timestamp)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_evaluaciones_generacion ON evaluaciones_qa(generacion_id, id)")
    con.commit()
    con.close()
```
La prueba de migración de esquema (sección de Testing) se corre dos
veces: una vez inicializando una base nueva desde cero, y otra vez
partiendo de una copia del esquema real actual (sin `trabajo_id` ni
`uq_generaciones_intento`) para confirmar que la migración —y no solo la
creación desde cero— deja el índice único creado sin lanzar
`OperationalError`.

`_migrar_columna_si_hace_falta(con, tabla, columna, definicion_sql)`:
chequeo de solo lectura (`PRAGMA table_info`) primero; si la columna
falta, `BEGIN IMMEDIATE` + doble chequeo tras tomar el lock + `ALTER
TABLE ... ADD COLUMN` + commit. Generalizada (antes era una función
específica solo para `trabajo_id`) para reusarla también con
`drive_carpeta`, en vez de duplicar la misma lógica de migración dos
veces. En una base nueva ninguna de las dos columnas hace falta migrar,
ya vienen en `ESQUEMA`.

**Backfill de `drive_carpeta` para los 10 trabajos históricos — los 10,
sin excluir el reabierto (corrige inconsistencia real señalada por Codex,
ronda 4: una versión anterior de este punto excluía al trabajo histórico
que la sección 6 reabre, como si su ubicación física en Drive dependiera
de su estado de negocio — pero `drive_carpeta` es solo una caché de dónde
está el archivo *físicamente*, completamente independiente de en qué
estado esté el trabajo; ese archivo sigue estando en `procesados` en
Drive sin importar que el trabajo se reabra o no):** los 10 trabajos ya
están efectivamente archivados en `procesados` en Drive (el worker real
ya corrió `marcar_como_procesado` en su momento) — el script de backfill
histórico (punto 6) hace `UPDATE trabajos SET drive_carpeta =
'procesados' WHERE id IN (3,4,...,12)` para los 10, dentro de la misma
transacción, para que la reconciliación de movimiento no intente
re-moverlos innecesariamente. Si el trabajo reabierto termina más tarde
en `rechazado`, la reconciliación normal (punto 7) lo relocalizará a
`rechazados` como a cualquier otro — el backfill no necesita anticipar
eso, solo registrar dónde está el archivo *hoy*.

**Se llama `inicializar_db()` únicamente desde los puntos de entrada
genuinamente persistentes: `fase8_worker_ingesta.py` `main()`,
`fase8_panel_revision.py` al cargar, y `fase8_backfill_historico.py`
(punto 6) — no dentro de `conectar()`, que sigue siendo solo abrir la
conexión.**

**Corrige contradicción real señalada por Codex (ronda 4): una versión
anterior de este plan también llamaba `inicializar_db()` desde
`fase6_validacion_clasificador.py` y `fase6_demo_reintento.py`.** Ambos
scripts existen específicamente para poder correrse en modo
"`generacion_id=None` → no persiste nada" (ver "Alcance de uso" en la
sección de `generar_con_reintento`, más arriba) — llamar
`inicializar_db()` en su arranque migra/crea el esquema de la base real
igual, incluso cuando el resto de la ejecución no toca ni una fila, lo
que contradice el propio diseño de "sin persistencia" de esos scripts y
además puede sorprender a alguien que corre el clasificador de
validación esperando que sea puramente de lectura. Esos dos scripts
**no** llaman `inicializar_db()`: si se los corre contra una base que
todavía no tiene el esquema nuevo (columnas `trabajo_id`,
`drive_carpeta`, los nuevos índices) y su modo sí necesita leer/escribir
en la base (uso con `generacion_id` real, no `None`), fallan con el error
nativo de SQLite (columna/tabla inexistente) en vez de crear
silenciosamente el esquema — aceptable porque ese es un uso secundario de
depuración, no un punto de entrada de producción, y el mensaje de error
nativo ya es suficientemente claro ("no such column: trabajo_id") para
que el operador sepa que debe correr primero el worker o el backfill.

**`fase7_poblar_registro.py` se retira, no se migra** (corrige hueco real:
decir "es historico" en la documentación no impide que alguien lo corra
de nuevo por accidente y vuelva a violar el nuevo invariante de
`score_qa`). **Salida incondicional, sin bandera de escape** (corrige
inconsistencia real: una bandera que "permite correrlo igual" prometía
algo que ya no funciona — el script llama
`evaluar_calidad(FOTO_GORRA_REAL, ruta_salida)` con la firma vieja de 2
argumentos, que con el cambio del punto 2 directamente lanza una
excepción; mantener una ruta de escape rota es peor que no tener
ninguna). Se le agrega al inicio de `main()`, sin condición:
```python
sys.exit("Este script es de la Fase 7, ya cerrada y documentada en "
         "resultados-fase7.md. No se actualizo a la firma nueva de "
         "evaluar_calidad() a proposito - no hay razon de negocio para "
         "volver a correrlo. Usa el worker de Fase 8 en su lugar.")
```
No requiere portar su lógica al patrón nuevo para un script que no se
necesita seguir manteniendo, y no deja una puerta trasera que rompería de
todos modos si alguien la usara.

**Excepción deliberada, igual que arriba: `fase7_consultas.py` no se
toca.** Es un reporte
de una sola vez ya generado y documentado (`resultados-fase7.md`), no
parte del flujo vigente; sus consultas siguen leyendo
`generaciones.score_qa` directamente, lo cual es correcto para los datos
que ya tiene pero quedaría desactualizado si alguien lo corriera de nuevo
sobre datos nuevos — se documenta esta limitación en vez de reescribir un
script histórico ya cerrado.

**Restricción de unicidad (red de seguridad barata contra bugs de lógica
propios — no protege contra dos workers concurrentes, porque solo corre
uno):** `uq_generaciones_intento` sobre `(trabajo_id, modelo_ia,
escena_id, intento)`. Se crea dentro de `inicializar_db()` (sección 5),
**después** de la migración de `generaciones.trabajo_id` — nunca dentro
de `ESQUEMA` directamente (ver ese código y la nota de orden que lo
acompaña; una versión anterior de este plan mostraba el `CREATE UNIQUE
INDEX` como bloque suelto aquí, sin conectarlo al código real de
`inicializar_db()`, lo que Codex señaló en la ronda 4 como un orden de
creación sin especificar). Convierte cualquier bug futuro en el guard de
idempotencia (punto 7) en un `IntegrityError` inmediato en vez de una
fila duplicada silenciosa.

### 6. Backfill histórico — script separado, de una sola vez, genuinamente resumible

**Archivo nuevo:** `src/fase8_backfill_historico.py` — **no** se ejecuta
como parte del arranque normal; se corre manualmente una vez.

**Secuencia operativa obligatoria (documentada como prerequisito impreso
al arrancar el script, y en el runbook del proyecto):** detener el worker
(`fase8_worker_ingesta.py`) y cerrar el panel de Streamlit **antes** de
correr este script. No se introduce un estado `reevaluando` nuevo en la
base para esto — es un proyecto de un solo operador con dos procesos
propios, no un servicio con usuarios concurrentes; parar los dos procesos
a mano antes de una migración de datos de una sola vez es proporcional.
El script imprime esta instrucción y espera confirmación (`input()`) antes
de continuar, para no depender de que el operador se acuerde solo.

1. **Backup con la API de backup de SQLite, no una copia de archivo cruda**
   (una copia a nivel de sistema de archivos puede capturar un estado
   inconsistente si hay un WAL/journal activo; la API de backup de
   `sqlite3` es segura sobre una base viva):
   ```python
   from db import DB_PATH  # ruta absoluta real, no un literal relativo -
                           # corrige bug real: un literal como "output/gorrolandia.db"
                           # depende del cwd desde donde se corra el script, y podria
                           # crear/respaldar una base distinta a la que db.py usa de verdad
   origen_path = DB_PATH.resolve()
   destino_path = origen_path.with_name(f"{origen_path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
   if not origen_path.is_file():
       abortar(f"no existe la base de datos en {origen_path} - nada que respaldar")
   # el chequeo de origen_path.is_file() es indispensable y va ANTES de
   # conectar (corrige hallazgo real de Codex, ronda 4): sqlite3.connect()
   # crea el archivo destino si no existe, y sin este chequeo tambien
   # "respaldaria" un origen inexistente creando y conectando una base
   # origen vacia nueva - el backup "tendria exito" (integrity_check pasa
   # sobre una base vacia valida) sin haber respaldado nada real
   if destino_path.exists():
       abortar("ya existe un backup con ese nombre - resolver antes de continuar")
   # el chequeo de existencia del destino va ANTES de conectar - sqlite3.connect()
   # crea el archivo si no existe, lo que haria que el chequeo posterior fuera
   # siempre verdadero (bug real detectado en una version anterior)
   # los handles se inicializan en None ANTES del try - si sqlite3.connect()
   # mismo falla (ej. origen bloqueado por otro proceso), el finally no debe
   # intentar cerrar algo que nunca se abrio, ni enmascarar el error real
   # (bug real detectado en una version anterior: ambos connect() estaban
   # fuera del try, asi que un fallo ahi se saltaba toda la limpieza)
   origen = None
   destino = None
   exito = False
   try:
       origen = sqlite3.connect(origen_path)
       destino = sqlite3.connect(destino_path)
       origen.backup(destino)
       resultado = destino.execute("PRAGMA integrity_check").fetchone()[0]
       if resultado != "ok":
           raise RuntimeError(f"backup corrupto: {resultado}")
       exito = True
   finally:
       # cerrar los handles SIEMPRE antes de intentar borrar el archivo -
       # en Windows no se puede eliminar un archivo con un handle abierto
       if origen is not None:
           origen.close()
       if destino is not None:
           destino.close()
       if not exito:
           destino_path.unlink(missing_ok=True)  # no dejar un backup a medias, si llego a crearse
   ```
   Reporta la ruta exacta del backup creado. Nunca reemplaza uno existente;
   si falla a mitad de camino, borra el backup incompleto en vez de
   dejarlo ahí dando falsa confianza.
2. Llama `inicializar_db()` (asegura columnas/tablas antes de tocar datos).
   **Nota de precisión (corrige afirmación inexacta señalada por Codex,
   ronda 4): esto ya es una modificación real del esquema** —
   `inicializar_db()` es idempotente (columnas/índices `IF NOT EXISTS`,
   segura de re-ejecutar), pero si el backfill aborta en el siguiente
   paso, el archivo ya tiene las columnas/índices nuevos aunque ningún
   dato de negocio haya cambiado. Eso es aceptable — el backup del paso 1
   ya se tomó antes de esto, así que restaurar el backup deshace incluso
   el cambio de esquema si hiciera falta — pero el plan no debe afirmar
   "sin modificar nada"; la afirmación correcta es "sin modificar ninguna
   fila de datos de negocio (trabajos/generaciones/evaluaciones_qa)".
   Hecho esto, y antes de tocar cualquier fila de datos, verifica que
   **cada una de las 69 filas elegibles** tiene su `ruta_output`
   existente en disco y decodificable como imagen — si alguna falta o
   está corrupta, aborta (sin haber tocado ninguna fila de datos; el
   esquema ya migrado permanece, cubierto por el backup) y reporta cuál.
   La escena real usada históricamente se identifica por el mismo
   `escena_id` numérico ya usado en Fase 4/7/8 (no ha cambiado desde
   entonces); no se agrega un manifiesto de hashes por escena — sería más
   infraestructura de la que este backfill de una sola vez justifica.
3. **Corregir `escena_id` de las filas históricas de Pista A Y asignar
   `trabajo_id`, en una sola transacción, cada paso con sus propios tres
   estados resumibles (fusiona lo que en la ronda anterior eran dos
   bloques separados con un bug de orden: el segundo abría `BEGIN
   IMMEDIATE` después de que el primero ya había ejecutado `UPDATE`s en
   autocommit, lo que revienta con "cannot start a transaction within a
   transaction"; y el primer bloque tampoco era resumible — en una
   segunda corrida, las 30 filas ya normalizadas no matchean `escena_id
   = 'n/a'`, así que `normalizadas` da 0 y el assert de "se esperaban 30"
   aborta por error):**
   ```python
   con.execute("BEGIN IMMEDIATE")

   # --- paso 3a: normalizar escena_id de Pista A, con sus 3 estados ---
   sin_normalizar = con.execute("""
       SELECT id, ruta_output FROM generaciones
       WHERE modelo_ia = 'compositing_local' AND escena_id = 'n/a'
   """).fetchall()
   ya_normalizadas = con.execute("""
       SELECT COUNT(*) FROM generaciones
       WHERE modelo_ia = 'compositing_local' AND escena_id IN ('4x5', '1x1', '9x16')
   """).fetchone()[0]

   if len(sin_normalizar) == 30 and ya_normalizadas == 0:
       for fila in sin_normalizar:
           match = re.search(r"_producto_(4x5|1x1|9x16)\.jpg$", fila["ruta_output"])
           if not match:
               con.rollback()
               abortar(f"fila {fila['id']}: ruta_output no matchea el patron "
                       f"esperado: {fila['ruta_output']}")
           con.execute("UPDATE generaciones SET escena_id = ? WHERE id = ?",
                       (match.group(1), fila["id"]))
   elif len(sin_normalizar) == 0 and ya_normalizadas == 30:
       pass  # ya normalizado en una corrida anterior, no hacer nada
   else:
       con.rollback()
       abortar(f"estado ambiguo de normalizacion: {len(sin_normalizar)} sin "
               f"normalizar, {ya_normalizadas} ya normalizadas - "
               "no es ni 'nada hecho' ni 'todo hecho', revisar antes de continuar")

   # --- paso 3b: backfill de trabajo_id, con sus propios 3 estados,
   #     MISMA transaccion (ya no se hace BEGIN de nuevo aqui) ---
   elegibles = contar_filas_elegibles(con)       # WHERE ruta_output LIKE fase8 AND sku sin ambiguedad
   ya_asignadas = contar_filas_elegibles_con_trabajo_id(con)
   sin_asignar = elegibles - ya_asignadas

   if elegibles != 69:
       con.rollback(); abortar(f"esperaba 69 filas elegibles, hay {elegibles}")
   elif sin_asignar == 0:
       pass  # backfill de trabajo_id ya completo en una corrida anterior
   elif ya_asignadas == 0:
       cur = con.execute(SQL_UPDATE_BACKFILL)
       if cur.rowcount != 69:
           con.rollback(); abortar(f"el UPDATE afecto {cur.rowcount} filas, se esperaban 69")
   else:
       con.rollback()
       abortar(f"estado ambiguo de trabajo_id: {ya_asignadas} ya asignadas, "
               f"{sin_asignar} sin asignar - revisar antes de continuar")

   con.commit()  # normalizacion + backfill, atomico, una sola vez
   ```
   Los dos sub-pasos son cada uno idempotente con sus propios tres estados
   (nada hecho / todo hecho / ambiguo → abortar), y comparten una única
   transacción — correr el script completo dos veces seguidas no falla ni
   duplica nada en ninguno de los dos.
4. Ya con `trabajo_id` poblado: para cada una de las **39** filas
   `nano_banana`, usa **`ultima_evaluacion_vigente(generacion_id)`** (la
   misma función que todo lo demás — corrige inconsistencia real: la
   versión anterior decía "si no existe ya una evaluación no-error",
   que no es lo mismo que "la última evaluación es completa"; una fila
   con una aprobación vieja seguida de un `qa_error` más reciente se
   habría saltado incorrectamente). Si `ultima_evaluacion_vigente()` ya
   devuelve una evaluación completa (no `qa_error`) para `VERSION_QA`, se
   salta. Si no, llama `evaluar_calidad` (3 imágenes: producto real,
   escena real ya en disco, la imagen ya generada) — que se audita a sí
   misma (punto 2). Esto es lo que hace al backfill realmente resumible
   ante una falla de red a mitad de las 39 llamadas.
5. Al terminar, para cada uno de los 10 trabajos aplica la **regla única
   de estado** ("Conceptos clave") usando las evaluaciones vigentes recién
   creadas — el trabajo en `aprobado` se reevalúa igual que los demás, sin
   trato especial.
6. El script imprime al final que es seguro reiniciar el worker y el
   panel.

Costo: 39 llamadas de QA (~$0.80), cero generación de imagen nueva.

### 7. Guard de idempotencia — Pista A y Pista B, con reanudación por intento

**Archivo:** `src/fase8_worker_ingesta.py`

**Rutas de salida por `trabajo_id` (esto se había especificado en una
ronda anterior y se perdió en una reescritura — confirmado que el código
actual sigue usando `output/fase8/{pista_a,pista_b}/<sku>/...`, sin
`trabajo_id`, lo cual sí permite que dos trabajos con el mismo SKU se
pisen los archivos entre sí):** las rutas de salida de Pista A y Pista B
pasan a `output/fase8/trabajos/<trabajo_id>/{pista_a,pista_b}/<sku>/...`.
Se prueba explícitamente que dos trabajos con el mismo `sku` producen
archivos físicos distintos, no solo que la consulta a la base los aísla.

**Instancia única del worker (corrige riesgo real: si alguien lanza el
worker dos veces por accidente, resetear todo `procesando` a `pendiente`
al arrancar — ver más abajo — deja que ambas instancias tomen el mismo
trabajo y hagan llamadas pagadas duplicadas antes de que el índice único
de la base detecte nada):** al arrancar, el worker toma un **lock real de
sistema operativo**, no un archivo marcador — corrige bug real: un lock
basado en "crear un archivo con `O_EXCL`" sobrevive a un crash (corte de
luz, `kill -9`) porque el archivo no desaparece solo, dejando el lock
trabado para siempre y bloqueando todo arranque futuro del worker hasta
que alguien borre el archivo a mano. La librería `filelock` (agregar a
`requirements.txt`; usa `msvcrt` en Windows y `fcntl.flock` en POSIX por
debajo) ata el lock al proceso vivo — el sistema operativo lo libera
automáticamente cuando el proceso muere, sin importar la causa:

**`LOCK_PATH` también es sobreescribible por variable de entorno
(`GORROLANDIA_LOCK_PATH`), con el mismo patrón que `DB_PATH` — necesario
para poder probar el lock sin depender de la ruta real de producción
(ver más abajo, "Prueba del lock, aislada del worker completo"):**
```python
from filelock import FileLock, Timeout
# ruta absoluta desde ROOT, no relativa al cwd - corrige bug real: dos
# arranques del worker desde directorios de trabajo distintos podrian
# resolver "output/fase8/worker.lock" a dos archivos diferentes y jamas
# detectarse entre si
LOCK_PATH = Path(os.environ.get(
    "GORROLANDIA_LOCK_PATH", str(ROOT / "output" / "fase8" / "worker.lock")
))
LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
lock = FileLock(str(LOCK_PATH), timeout=0)
try:
    lock.acquire()
except Timeout:
    sys.exit("Ya hay un worker corriendo (lock activo) - no se inicia una segunda instancia.")
```

No es un sistema de leases con expiración explícita — no hace falta:
al ser un lock real de SO, no necesita expirar, se libera solo.

**La función que adquiere el lock se extrae como una función propia y sin
efectos secundarios adicionales** (p. ej. `adquirir_lock_worker() ->
FileLock`, llamada por `main()` al arrancar) — no por diseño elegante,
sino porque es lo que permite probar el lock sin arrancar el worker
completo (ver más abajo).

- **Pista A, por formato individual — solo se regeneran los formatos que
  faltan, nunca los 3 (corrige bug real: la versión anterior llamaba
  `generar_imagen_producto` sin condición, que en el código actual escribe
  los 3 archivos directamente en sus rutas finales — si solo faltaba 1 de
  3, los otros 2 ya buenos se sobrescribían igual. Que hoy sea
  determinista y produzca bytes idénticos, confirmado en Fase 5, no es
  una base segura para asumir que siempre lo será — un cambio futuro de
  dependencia o de la foto de entrada rompería esa suposición en
  silencio):**
  - `generar_imagen_producto(foto_gorra, sku, output_dir, formatos=None)`
    gana un parámetro opcional `formatos` (subconjunto de `{"4x5", "1x1",
    "9x16"}`; `None` = los 3, comportamiento actual sin cambios para quien
    la llame sin el parámetro — la prueba de determinismo de Fase 5 sigue
    funcionando igual).
  - El worker, antes de llamarla, consulta qué formatos ya tienen fila
    `compositing_local` registrada para este `trabajo_id` y clasifica cada
    uno de los 3 en exactamente uno de tres casos — **distinción que
    faltaba y que importa por el índice único `uq_generaciones_intento`
    (`trabajo_id`, `modelo_ia`, `escena_id`/formato, `intento`) agregado
    en la sección 5: para Pista A `intento` siempre vale 1, así que
    "regenerar como intento nuevo" (la solución que sí sirve para Pista B)
    no aplica aquí — insertar una segunda fila para un formato que ya
    tiene una violaría ese índice**:
    - **Fila ausente** → generar el archivo y **insertar** una fila
      `compositing_local` nueva para ese formato (comportamiento sin
      cambios).
    - **Fila presente, archivo válido** (`PIL.Image.open(...).verify()` —
      mismo helper que Pista B) → no tocar nada, ni el archivo ni la fila.
    - **Fila presente, archivo faltante o corrupto** (corrige hueco real:
      la versión anterior solo chequeaba que el archivo existiera, y
      además no distinguía este caso del de "fila ausente") → **la ruta
      de salida de Pista A es determinista por `(trabajo_id, formato)`**
      (no depende de ningún dato que pueda cambiar), así que regenerar el
      archivo en el mismo `ruta_output` ya registrado (temporal +
      `os.replace()` atómico) resuelve el problema **sin tocar la fila de
      la base de datos en absoluto** — no hace falta insertar, no hace
      falta actualizar, el registro ya apuntaba al lugar correcto desde
      un principio.
  - Solo se le pide a `generar_imagen_producto` que produzca los formatos
    de los casos "ausente" y "corrupto" — nunca regenera (ni por lo tanto
    puede sobrescribir) un formato ya válido.
  - Para poder consultar "¿ya existe una fila para este formato?" sin
    agregar una columna nueva, las filas de Pista A guardan el formato
    (`"4x5"`/`"1x1"`/`"9x16"`) en la columna `escena_id` (hoy vale `"n/a"`
    para todas, sin usarse) en vez de `"n/a"`.
- **Pista B, por escena:** antes de generar, consultar los intentos ya
  registrados para `(trabajo_id, escena_id)`, ordenados por intento:
  - Si el más reciente tiene evaluación vigente completa (no `qa_error`) y
    `aprobado=1`, y su archivo existe y decodifica como imagen válida →
    saltar la escena por completo.
  - **Si el más reciente tiene imagen válida en disco pero su evaluación
    vigente es `qa_error` o no existe (corrige hueco real: la versión
    anterior generaba una imagen nueva en este caso, gastando dinero por
    un problema que era de QA, no de la imagen)** → **no se genera una
    imagen nueva**; se reintenta solo `evaluar_calidad` sobre esa misma
    imagen ya existente y se registra la evaluación. Esto no consume un
    número de intento nuevo.
  - Si el más reciente tiene evaluación vigente completa con
    `aprobado=0` (fallo real de producto, no de QA), **continuar desde
    `max(intento existente) + 1`**, sin exceder `MAX_INTENTOS` — nunca se
    reutiliza ni se sobrescribe el nombre de archivo de un intento ya
    registrado.
  - Si `max(intento existente) >= MAX_INTENTOS` y ninguno aprobó, la
    escena queda agotada — no se generan más intentos automáticos.
  - **Archivo perdido o corrupto del intento más reciente (rama nueva —
    faltaba especificar: los guards de arriba asumen que el archivo del
    intento más reciente siempre existe y es válido; si alguien borra
    `output/` a mano, o un disco falla, ninguna de las ramas anteriores
    aplica limpio):** un archivo faltante o que no decodifica como imagen
    **nunca se manda a QA** (no tiene sentido evaluar algo que no existe).
    Si `max(intento existente) < MAX_INTENTOS`, se genera un intento
    nuevo (`max(intento existente) + 1`) normalmente. Si ya está en
    `MAX_INTENTOS`, la escena queda en el mismo estado de "requiere
    revisión manual" que el agotamiento de QA (punto 7 más abajo), con su
    propia marca distinta en el panel ("🗑️ archivo perdido en el intento
    límite — requiere regenerar manualmente o rechazar el trabajo").

**`ciclo_una_vez()` pasa a tener tres pasadas, no una — las dos nuevas
resuelven casos que antes quedaban inalcanzables porque el worker solo
seleccionaba trabajos `pendiente`:**

1. **Trabajos `procesando` huérfanos por un crash:** al arrancar
   `main()`, antes de empezar a hacer polling, resetear a `pendiente`
   cualquier trabajo que esté en `procesando` — con el lock de instancia
   única de arriba, esto siempre es evidencia de un corte anterior, nunca
   de otro worker corriendo en paralelo.
2. **Trabajos `pendiente`/recién reseteados:** el flujo normal de
   `procesar_trabajo` ya descrito.
3. **Reconciliación de QA incompleta — únicamente `listo_para_revision`,
   NUNCA `rechazado` ni `aprobado`** (corrige dos huecos reales, uno ya
   corregido en una ronda anterior y otro señalado por Codex en esta: la
   versión original incluía trabajos ya rechazados por un humano,
   gastando dinero en re-evaluar algo que ya se decidió descartar; una
   corrección posterior agregó `aprobado` a la lista pensando en el único
   trabajo histórico mal aprobado que este plan necesita reabrir, pero eso
   convierte la aprobación humana en una decisión reversible por
   accidente: el día que `VERSION_QA` suba por cualquier motivo, TODOS los
   trabajos ya aprobados —no solo el histórico— dejarían de tener
   evaluación vigente para la nueva versión, la reconciliación los tomaría
   como incompletos, gastaría dinero re-evaluándolos, y en el peor caso
   uno de ellos podría terminar en `qa_error` sin que ningún humano haya
   pedido revisarlo de nuevo — un trabajo ya publicado no debería poder
   volver a moverse solo por un bump de versión de QA):** antes, un
   trabajo con 1 escena evaluada y 2 en `qa_error` llegaba a
   `listo_para_revision` y ya nada volvía a intentar esas 2, porque el
   worker nunca vuelve a mirar trabajos que no están `pendiente`. En cada
   ciclo, el worker consulta los trabajos en `listo_para_revision` (y
   solo ese estado) que tengan al menos una escena de Pista B sin
   evaluación vigente completa, y para esas escenas puntuales reintenta
   **solo QA** sobre la imagen ya generada (mismo guard del punto de
   arriba: "imagen válida + evaluación vigente `qa_error` o ausente →
   solo reintentar QA, sin generar de nuevo"). El único trabajo histórico
   que sí necesita reabrirse pese a estar `aprobado` se maneja
   **exclusivamente dentro del script de backfill de una sola vez**
   (sección 6 más abajo), nunca en esta reconciliación recurrente: si en
   el futuro se necesita revalidar trabajos ya aprobados tras un cambio de
   `VERSION_QA`, eso requiere una operación explícita y deliberada (otro
   script de una sola vez, no este ciclo automático), no un efecto
   secundario silencioso del worker.

   **Límite: el mismo de 6 filas del punto 4, reutilizado tal cual** — la
   reconciliación no lleva su propio contador separado; simplemente llama
   a `evaluar_calidad` normalmente, y es `evaluar_calidad` quien ya se
   niega a hacer una séptima llamada al proveedor para ese
   `generacion_id` (punto 4). La reconciliación no necesita saber si viene
   agotado por su propia cuenta o por el reintento interno de una llamada
   anterior — un solo lugar (punto 4) decide el límite, todo lo demás solo
   lo respeta.

   **QA agotado — definición consistente con "la última evaluación
   manda" (corrige contradicción real: definir agotado como "6 filas y
   ninguna completa" choca con el resto del plan, que en todos lados
   dice que solo la evaluación MÁS RECIENTE cuenta como vigente — un
   historial con una aprobación vieja seguida de varios `qa_error` más
   nuevos ya está agotado en la práctica (el guard de llamadas ya se
   niega a intentar una séptima), pero "ninguna es completa" da `False`
   porque esa aprobación vieja sigue estando ahí, así que el panel nunca
   lo habría marcado como agotado):** un `(generacion_id, VERSION_QA)`
   está agotado si tiene **al menos 6 filas para esa versión** Y **la más
   reciente de esas filas es `qa_error`** — sin importar si hay una
   completa más vieja en el medio, porque esa más vieja ya dejó de ser
   vigente. No se agrega un estado nuevo en `trabajos` — se infiere con
   esta misma consulta. El panel muestra esa escena con una marca distinta
   ("⛔ QA agotado tras 6 intentos — requiere revisión manual") en vez de
   la marca genérica de `qa_error`, y dado que la evaluación nunca se
   completa, la regla de bloqueo de "Aprobar" (Conceptos clave) sigue
   impidiendo aprobar ese trabajo indefinidamente — es una decisión
   deliberada: "rechazar" sigue disponible siempre, y forzar un reintento
   más allá del límite es una intervención manual fuera de este plan (no
   se construye una acción de "forzar" en el panel — si de verdad hace
   falta, se hace manualmente desde una consola Python, no vale la pena
   una función nueva para un caso que debería ser raro).
   - **Reconciliación de movimiento en Drive — requiere separar el manejo
     de errores en `procesar_trabajo` (corrige bug real y verificado en el
     código actual: `fase8_worker_ingesta.py` envuelve la generación, el
     `UPDATE` de estado, Y el movimiento a `procesados` en el MISMO
     `try/except`, así que un fallo transitorio de red justo al mover el
     archivo — después de que el trabajo YA llegó exitosamente a
     `listo_para_revision` — degrada todo el trabajo a `error`. Y como la
     reconciliación de esta misma sección excluye `error` a propósito,
     ese trabajo quedaría atrapado para siempre: ya no es elegible para
     re-generación (no está en `pendiente`), y tampoco para la
     reconciliación de movimiento):**
     - El movimiento a `procesados`/`rechazados` se envuelve en su **propio**
       `try/except`, separado del que cubre generación + QA. Si falla,
       **el estado del trabajo NO cambia** — se queda en el estado
       terminal que ya alcanzó (`listo_para_revision`/`aprobado`/`rechazado`),
       y solo el movimiento en Drive queda pendiente de reintento.
     - **`drive_archivado` (booleano) se reemplaza por `drive_carpeta`
       (columna `TEXT`, valores `NULL`/`'procesados'`/`'rechazados'`) —
       corrige hallazgo real de Codex, ronda 4: un booleano "ya se
       archivó sí/no" no puede representar que un trabajo que ya está en
       `procesados` necesita **relocalizarse** a `rechazados` si un humano
       lo rechaza después de que la reconciliación ya lo archivó como
       `listo_para_revision`. `drive_carpeta` es una **caché de la última
       ubicación confirmada, nunca la fuente de verdad** — la fuente de
       verdad siempre es la API de Drive:
       - `NULL` = según la caché, todavía en la carpeta de entrada (o
         nunca confirmado).
       - `'procesados'` / `'rechazados'` = según la caché, la última vez
         que se confirmó, el archivo estaba en esa carpeta.
     - **La reconciliación de movimiento calcula un "destino deseado" a
       partir del `estado` actual del trabajo, y compara contra la caché
       `drive_carpeta`:**
       ```
       destino_deseado(estado) =
           'procesados'   si estado in ('listo_para_revision', 'aprobado')
           'rechazados'   si estado == 'rechazado'
           None           si estado in ('pendiente', 'procesando', 'error')
       ```
       **Antes de mover nada, siempre se verifica la ubicación real
       (corrige hallazgo real de Codex, ronda 4: confiar en `drive_carpeta`
       como verdad salvo cuando un CAS falla no cubre el caso de un crash
       del worker justo después de que la llamada a la API de Drive tuvo
       éxito pero antes de que el `UPDATE` local se ejecutara o
       confirmara — al reiniciar, nada marca esa fila como "incierta", así
       que el worker seguiría creyendo la caché vieja indefinidamente. La
       corrección de Codex es más simple que el diseño anterior: no hace
       falta un estado especial de "sucio", basta con no confiar nunca en
       la caché para decidir, solo para saber si vale la pena mirar):**
       para cada trabajo donde `destino_deseado(estado) is not None` y
       `destino_deseado(estado) != drive_carpeta` (la caché sugiere que
       *podría* hacer falta mover algo — es solo una señal barata para no
       consultar la API en cada ciclo para cada trabajo terminal), se
       consulta primero `files.get(fileId=..., fields="parents")` para
       leer la carpeta real. Si la carpeta real ya coincide con
       `destino_deseado`, no se mueve nada — solo se actualiza la caché
       (`drive_carpeta`) para que el próximo ciclo no vuelva a consultar
       de balde; esto autocura exactamente el caso de crash post-movimiento
       descrito arriba, sin necesitar un estado "sucio" nuevo. Si la
       carpeta real es distinta de `destino_deseado`, se mueve el archivo
       (quitándolo de la carpeta real observada, agregándolo a
       `destino_deseado`), y luego persiste con el mismo patrón CAS que el
       resto del plan: `UPDATE trabajos SET drive_carpeta = ? WHERE id = ?
       AND estado = ?` usando el `estado` leído al calcular
       `destino_deseado`. Si ese `UPDATE` afecta 0 filas (un humano cambió
       el `estado` mientras tanto), no hace falta ninguna recuperación
       especial: la caché queda desactualizada, pero el próximo ciclo la
       trata igual que cualquier otra caché desactualizada — vuelve a
       consultar `files.get()` antes de decidir, como siempre. La consulta
       de solo lectura a Drive antes de mover es la única garantía real
       (`drive_carpeta` nunca decide un movimiento por sí sola, solo evita
       consultar en el camino feliz donde ya coincide).
     - La reconciliación de movimiento consulta trabajos en los tres
       estados terminales de **éxito** únicamente:
       `listo_para_revision`/`aprobado`/`rechazado` — sí incluye
       `rechazado`, a diferencia de la reconciliación de QA, porque
       archivar en Drive no cuesta dinero. **Los trabajos en `error` se
       excluyen deliberadamente** (fijado esta ronda tras una
       contradicción real: una versión anterior de este mismo plan decía
       en la implementación que sí se incluían, pero la sección de
       pruebas seguía asumiendo que no — quedan excluidos porque el
       procesamiento de un trabajo en `error` está incompleto por
       definición, y el archivo original en Drive puede hacer falta si se
       necesita reintentar o inspeccionar manualmente; una vez que un
       trabajo en `error` se reintenta (vía "Reintentar", punto 4 más
       abajo) y llega a un estado terminal de éxito, ahí sí se archiva
       como cualquier otro).
4. **Recuperación manual de trabajos en `error`, y rechazo — ambos con el
   mismo patrón CAS que `aprobar_trabajo()`, no un `UPDATE` incondicional
   (corrige contradicción real: una versión anterior de este plan exigía
   "ninguna acción del panel hace un `UPDATE` incondicional" pero el botón
   "Reintentar" seguía llamando `actualizar_estado_trabajo()` sin
   condición — la misma función genérica que no verifica nada):**
   ```python
   def reintentar_trabajo(trabajo_id) -> bool:
       con = conectar()
       cur = con.execute(
           "UPDATE trabajos SET estado = 'pendiente' WHERE id = ? AND estado = 'error'",
           (trabajo_id,)
       )
       con.commit()
       con.close()
       return cur.rowcount == 1

   def rechazar_trabajo(trabajo_id) -> bool:
       con = conectar()
       cur = con.execute(
           "UPDATE trabajos SET estado = 'rechazado' WHERE id = ? AND estado = 'listo_para_revision'",
           (trabajo_id,)
       )
       con.commit()
       con.close()
       return cur.rowcount == 1
   ```
   `reintentar_trabajo()` es una transición segura porque los guards de
   Pista A/B (punto 7) y el lock de instancia única ya hacen que
   reprocesar un trabajo desde `pendiente` nunca rehaga ni cobre de más
   nada que ya esté completo. No resetea contadores de reintentos de QA
   agotados (ver arriba) — para ese caso específico, "Reintentar" no ayuda
   por diseño.

   **El propio worker también necesita el mismo cuidado, no solo los
   botones del panel (corrige el mismo problema en el otro sentido: un
   humano puede rechazar un trabajo justo mientras la reconciliación de
   QA sigue trabajando sobre él):** cuando `procesar_trabajo` o la
   reconciliación terminan de evaluar y van a recalcular/escribir el
   estado del trabajo (la "regla única de estado"), el `UPDATE` incluye
   siempre una condición sobre el estado esperado
   (`WHERE id = ? AND estado IN ('pendiente', 'procesando',
   'listo_para_revision')`) — **nunca** sobre `'rechazado'` ni
   `'aprobado'`. Si un humano ya rechazó o aprobó el trabajo mientras el
   worker seguía trabajando, esa decisión humana gana: el `UPDATE` del
   worker afecta 0 filas y no hace nada más. **El destino del archivo de
   Drive en esa misma carrera se resuelve con el mecanismo de
   `drive_carpeta`/relocalización descrito en el punto 7 más abajo, no
   solo con "leer el estado justo antes de mover" (corrige afirmación
   real señalada por Codex, ronda 4: leer el estado inmediatamente antes
   de la llamada a la API de Drive reduce la ventana de la carrera pero
   no la cierra — un humano puede rechazar el trabajo en el instante
   exacto entre esa lectura y el `UPDATE` que registra el movimiento, así
   que ninguna lectura "justo antes" es, por sí sola, suficiente)**: si
   eso ocurre, el `UPDATE` de `drive_carpeta` con CAS falla (0 filas), y
   es el ciclo de reconciliación **siguiente** el que corrige la
   ubicación real, releyendo primero el estado físico verdadero desde la
   API de Drive antes de decidir a dónde debe ir — no una única lectura
   que se asume suficiente, sino un proceso que converge solo, ciclo tras
   ciclo, sin importar cuántas veces se repita la carrera.

### 8. Ingesta de Drive — dedup antes de descargar, límite de tamaño real, rutas únicas

**Archivos:** `src/fase8_worker_ingesta.py`, `src/fase8_drive_cliente.py`

- `encolar_archivos_nuevos()` consulta primero los `drive_file_id` ya
  existentes en `trabajos`, filtra la listing contra ese conjunto, y solo
  descarga los genuinamente nuevos.
- **`listar_archivos_nuevos()` pagina el listado completo** (sigue
  `nextPageToken` hasta agotarlo) — corrige hueco real: con el límite de
  página por defecto, archivos rechazables en la primera página podían
  "tapar" archivos válidos de páginas siguientes que nunca se llegaban a
  ver. Pide también el campo `size`; se rechaza antes de descargar si
  supera 20MB. **Límite real durante la descarga:** `MediaIoBaseDownload`
  se configura con `chunksize` pequeño y explícito (ej. 256KB); tras cada
  `next_chunk()` se compara `buffer.tell()` contra el límite y se aborta +
  se borra el archivo/buffer parcial si se excede.
- `drive_file_id` se valida contra un patrón de caracteres esperado antes
  de usarse como componente de ruta; se verifica que la ruta resuelta siga
  dentro de `assets/skus_pendientes`. Descarga a un archivo temporal +
  `os.replace()` atómico en `assets/skus_pendientes/<drive_file_id>/<nombre_saneado>`
  (mismo patrón atómico que la salida de fal.ai, punto 9 — antes solo se
  aplicaba a la salida, no a la entrada).
- **El `sku` (usado en las rutas de salida del punto 7, no solo el nombre
  de archivo de entrada) se deriva del nombre saneado con su propia
  validación explícita** (corrige hueco real: sanear el nombre de archivo
  para la ruta de *entrada* no garantizaba que el `sku` derivado de ese
  mismo nombre fuera seguro para las rutas de *salida* de Pista A/B): el
  stem del nombre saneado se restringe a un patrón
  `^[A-Za-z0-9_-]{1,64}$`; si no matchea (vacío, con puntos al final,
  nombre reservado de Windows como `CON`/`NUL`/`AUX`, caracteres fuera de
  ese conjunto), el archivo se rechaza igual que un contenido inválido
  (mueve a `rechazados`, se anota en el log) — no se le asigna un SKU
  genérico ni se adivina uno.
- **Validación de contenido tras descargar:** tamaño, `PIL.Image.open(...).verify()`,
  y un chequeo barato de dimensiones (`Image.open(ruta).size`, sin cargar
  el pixel buffer completo) — rechazar si `ancho * alto` supera un límite
  generoso (ej. 100 megapixeles). Esto no es una defensa completa contra
  bombas de descompresión (fuera de alcance, ver justificación), pero sí
  cubre el caso de un archivo corrupto o con metadata de dimensiones
  disparatada, sin importar si la causa fue accidental o no.

  **Rechazo durable, no solo un log de texto (corrige hueco real: si
  mover el archivo a `rechazados` en Drive falla — otro hiccup de red —,
  no había ningún registro de que ya se había evaluado y rechazado, así
  que el siguiente ciclo de polling lo vuelve a descargar, re-validar, y
  re-rechazar para siempre, sin nunca lograr archivarlo):**
  ```sql
  CREATE TABLE IF NOT EXISTS archivos_rechazados (
      drive_file_id TEXT PRIMARY KEY,
      razon TEXT NOT NULL,
      timestamp TEXT NOT NULL,
      movido INTEGER NOT NULL DEFAULT 0
  );
  ```
  Al fallar cualquier validación, se inserta (o actualiza) esta fila
  **antes** de intentar mover el archivo en Drive — así el registro de
  "esto ya se evaluó y se rechazó" sobrevive aunque el movimiento mismo
  falle. `encolar_archivos_nuevos()` filtra también contra
  `archivos_rechazados` además de contra `trabajos`, para no
  re-descargarlo ni re-validarlo. Una pasada de reconciliación (junto con
  la de movimiento de trabajos terminales, punto 7 de más abajo) reintenta
  mover a `rechazados` cualquier fila con `movido = 0` — mover un archivo
  que ya está movido es seguro de reintentar (la API de Drive no falla de
  forma dañina ante un archivo que ya no está donde se esperaba, solo
  reporta "no encontrado", que se trata como éxito para efectos de marcar
  `movido = 1`).

### 9. Validación de salida (descarga del resultado de fal.ai)

`resp.raise_for_status()`. **Descarga en streaming con tope de bytes real**
(corrige hueco: la versión anterior cargaba `resp.content` completo sin
límite antes de poder rechazar nada) — `requests.get(..., stream=True)`,
acumular en chunks, abortar y borrar lo parcial si se supera un límite
generoso (ej. 50MB, la salida de un modelo de imagen no debería
acercarse a eso). Verificar que decodifica como imagen; escribir a
temporal + `os.replace()` atómico.

### 10. Operación local — Streamlit en localhost, redacción de secretos en errores

- **Localhost-only forzado por un archivo de configuración commiteado en
  el repo, no solo por una instrucción en la documentación (corrige
  hallazgo real de Codex, ronda 4: una versión anterior de este plan solo
  *describía* la restricción en prosa, pero el comando real usado tanto
  en `fase8_panel_revision.py` como en el runbook —
  `brief-fase8-google-drive.md` — seguía siendo `streamlit run
  src/fase8_panel_revision.py` sin ninguna bandera, así que un operador
  que siguiera la documentación tal cual quedaba expuesto en la red local
  sin darse cuenta):** se agrega **`.streamlit/config.toml`** (nuevo
  archivo, commiteado, en la raíz del repo — Streamlit lo lee
  automáticamente sin necesidad de pasar flags):
  ```toml
  [server]
  address = "127.0.0.1"
  headless = true
  ```
  Con esto, `streamlit run src/fase8_panel_revision.py` (el comando que ya
  aparece en el runbook, sin cambios) escucha solo en loopback por
  defecto — la restricción ya no depende de que el operador recuerde
  agregar una bandera cada vez. **Verificación manual, no automatizada
  (corrige contradicción real señalada por Codex, ronda 4: una versión
  anterior de esta sección prometía que "la prueba correspondiente
  verifica la interfaz real en la que escucha el proceso", pero la
  sección de Testing declara explícitamente que ninguna prueba
  automatizada levanta un servidor Streamlit real — las dos afirmaciones
  no pueden ser ciertas a la vez):** dado que este es un proyecto de un
  solo operador y la sección de Testing ya decidió deliberadamente no
  levantar Streamlit en pruebas automatizadas (ver "Pruebas de
  Streamlit"), esta verificación se hace **manualmente, una sola vez
  después de implementar**, como parte del Paso 2 del plan de validación:
  arrancar el panel con el comando real del runbook y confirmar con
  `netstat -ano | findstr :8501` (o el puerto que Streamlit asigne) que
  el proceso escucha en `127.0.0.1`, no en `0.0.0.0` ni en la IP de la
  red local. No se construye un smoke test de subproceso para esto solo
  para evitar la verificación manual — sería la misma clase de
  infraestructura de integración que ya se decidió no construir para el
  resto del panel.
- **Un solo sanitizador, usado en los tres lugares — base de datos, panel,
  Y consola/logs (corrige alcance real: la versión anterior solo cubría
  lo que se guarda o se muestra en el panel; el worker actual imprime
  excepciones crudas por consola, y una respuesta de error de fal.ai/Drive
  puede traer tokens fuera de una URL — en un encabezado `Authorization`,
  en el cuerpo de la respuesta):** una función `sanitizar(texto) -> str`
  aplicada a cualquier valor antes de: guardarlo en
  `problema`/`detalle`/`error` (`generaciones`, `evaluaciones_qa`,
  `trabajos`, `archivos_rechazados`), mostrarlo en el panel, o
  imprimirlo/loguearlo desde el worker. Redacta:
  - Cualquier substring que empiece con `http://`/`https://` → `[URL redactada]`.
  - Patrones `Authorization: Bearer ...` o similares → `[header redactado]`.
  - Substrings largos (20+ caracteres alfanuméricos/`-`/`_`) que aparecen
    después de palabras como `key`/`token`/`secret`/`password`
    (case-insensitive) → `[valor redactado]`.
  - Si el cuerpo completo de una respuesta del proveedor no se pudo
    parsear como JSON válido, **nunca se persiste crudo** — se guarda solo
    un resumen truncado y sanitizado, no la respuesta completa.
- La clave de la cuenta de servicio ya está fuera del repositorio
  (`credentials/` en `.gitignore`, confirmado) — sin cambios ahí.

**Fórmula explícita de costo total por trabajo (faltaba especificar —
corrige ambigüedad real: sumar generación y evaluación con un `JOIN`
directo multiplicaría filas si un `generacion_id` tiene varias
evaluaciones, dando un total inflado):** el panel calcula el costo de un
trabajo como dos sumas **separadas**, nunca con un `JOIN` entre las dos
tablas:
```sql
SELECT
  (SELECT COALESCE(SUM(costo_usd), 0) FROM generaciones WHERE trabajo_id = ?) +
  (SELECT COALESCE(SUM(costo_usd), 0) FROM evaluaciones_qa
     WHERE generacion_id IN (SELECT id FROM generaciones WHERE trabajo_id = ?))
```
Esto incluye automáticamente el costo de las llamadas de QA internas
fallidas (punto 2) y de las de reconciliación (punto 4) — todo lo que
tiene su propia fila en `evaluaciones_qa` cuenta hacia el total real.

## Plan de validación

**Paso 0 — Fixtures, con valores esperados por ítem crítico (sin costo):**

`assets/escenas_base/escena_001.jpg`, `escena_002.jpg`, `escena_003.jpg`
confirmado que ya no existen — se descartan los ejemplos de
`fase6_validacion_clasificador.py` que dependían de ellas. Manifiesto:

- 8 ejemplos de `fase4_validacion_muestra_{04,05,09,11,16,22,29,33}.jpg`.
- Los 5 archivos reales de `TEST-SKU-004` (negativos confirmados):
  `escena04_intento1.jpg`, `escena04_intento2.jpg`, `escena09_intento1.jpg`,
  `escena29_intento1.jpg`, `escena29_intento2.jpg` (los 5 únicos que
  existen — verificado, sin combinación 6ta inexistente).
- 2 fixtures negativos sintéticos locales con Pillow (sin API de
  generación): región de rostro alterada sobre `muestra_29` (negativo de
  `item_4_rostro`) y región de fondo recoloreada (negativo de
  `item_5_escena`), comparados contra la escena original real.

Total: 15 fixtures, cero archivos faltantes.

**Paso 1 — Regresión sobre fixtures, sin generar nada nuevo (~$0.50-0.65,
15 llamadas de QA). Criterios de aprobación explícitos (restaurados —
se habían perdido en una reescritura anterior):**

- Las 5 salidas de `TEST-SKU-004` marcan `item_1_color=False` — las 5, sin
  excepción. Si alguna sale `qa_error` en vez de un resultado firme, se
  reintenta la llamada de QA (no cuenta ni como pass ni como fail hasta
  tener un resultado firme o agotar el reintento).
- Los 2 fixtures sintéticos (rostro/fondo alterado) marcan su ítem
  correspondiente (`item_4_rostro`/`item_5_escena`) en `False`.
- Los 8 ejemplos de Fase 4 coinciden con su etiqueta humana ya registrada
  en al menos 7 de 8 (mismo umbral que el original de Fase 6).
- Ningún `qa_error` persistente se cuenta como acierto — si tras el
  reintento de QA un fixture sigue en `qa_error`, se excluye del cálculo
  de aciertos y se reporta aparte explícitamente, nunca se cuenta en
  silencio como si hubiera pasado.
- **Si cualquiera de los criterios de arriba no se cumple, el plan se
  detiene aquí** — no se avanza al Paso 1.5 ni al Paso 2 hasta ajustar el
  prompt/esquema de QA y repetir el Paso 1.

**Paso 1.5 — Backfill histórico completo** (punto 6, solo si el Paso 1
aprobó): ~$0.80, 39 llamadas de QA, cero generación nueva.

**Paso 2 — Confirmación end-to-end mínima (~$0.15-0.30, 2-3 generaciones
nuevas):** regenerar `TEST-SKU-004` contra 1 escena con el prompt
corregido; confirmar color/marca correctos. **También incluye la
verificación manual de localhost del panel** (ver "Operación local" más
arriba): arrancar `fase8_panel_revision.py` con el comando real del
runbook y confirmar con `netstat -ano | findstr :8501` que escucha en
`127.0.0.1`, no en `0.0.0.0` ni en la IP de red local — una sola vez,
después de agregar `.streamlit/config.toml`, no en cada corrida futura.

Solo si el paso 2 falla de forma no trivial se considera escalar al plan
completo (`PLAN-MEJORA-CALIDAD.md`).

## Testing

**Infraestructura de pruebas (corrige hallazgo real de Codex, ronda 4: la
versión anterior listaba comportamientos a probar sin especificar con qué
correrlos — no hay hoy ningún directorio de pruebas ni dependencia de
testing en el repo):**

- **Runner y dependencia nueva:** `pytest` (agregado a `requirements.txt`
  junto con `pytest` puro, sin plugins adicionales — no hace falta
  `pytest-asyncio` ni `pytest-xdist` para el volumen de pruebas de este
  plan). Se agrega un `tests/` en la raíz, un archivo por módulo cubierto
  (`tests/test_db.py`, `tests/test_fase6_qa_reintento.py`,
  `tests/test_fase8_worker_ingesta.py`, `tests/test_fase8_backfill.py`,
  `tests/test_fase8_drive_cliente.py`, `tests/test_fase8_panel_revision.py`).
  Se corren con `pytest tests/` desde la raíz del proyecto.
- **Inyección de `DB_PATH` a través de módulos ya importados (el punto
  concreto que faltaba resolver: `db.py` fija `DB_PATH` como constante de
  módulo al importarse, y otros módulos hacen `from db import DB_PATH`,
  así que sobreescribir `db.DB_PATH` después de importar no cambia la
  referencia que ya tienen los demás módulos):** un fixture de `pytest`
  con alcance de función crea un archivo temporal
  (`tempfile.NamedTemporaryFile` o `tmp_path` de `pytest`), y en vez de
  reasignar la constante, hace `monkeypatch.setattr(db, "DB_PATH",
  ruta_temporal)` **y además** `monkeypatch.setattr(modulo_bajo_prueba,
  "DB_PATH", ruta_temporal)` para cada módulo que haya hecho el `from db
  import DB_PATH` directo — evita depender de que todo el código pase a
  usar `db.DB_PATH` calificado (cambio de alcance mayor, innecesario para
  este plan). El fixture llama `db.inicializar_db()` sobre esa ruta antes
  de entregar el control a la prueba, y no requiere limpieza explícita del
  archivo (`tmp_path` de pytest se limpia solo).
- **Mocks de clientes externos:** `fal_client` y las llamadas HTTP a
  Drive/OpenRouter se mockean con `unittest.mock.patch`, nunca golpean la
  red real en una prueba automatizada — se parametrizan con
  respuestas/excepciones fijas para cubrir los casos de esta lista
  (timeouts, cuerpos no-JSON, códigos no-2xx, tamaños límite).
- **Pruebas que arrancan un subproceso real — nunca el worker completo,
  siempre un ayudante mínimo dedicado (corrige hallazgo real de Codex,
  ronda 4: una versión anterior de este punto lanzaba
  `[sys.executable, "-m", "fase8_worker_ingesta"]` como subproceso de
  prueba — eso arranca el módulo real completo, que intenta cargar
  credenciales reales de Drive/fal.ai y contactar esas APIs; los mocks
  del proceso padre de pytest, hechos con `unittest.mock.patch`, no
  existen dentro de ese subproceso —viven en el proceso padre, el hijo
  reimporta todo desde cero—, así que solo redirigir `GORROLANDIA_DB_PATH`
  no bastaba: la prueba de "instancia única del lock" quedaba a merced de
  que ese primer proceso lograra pasar la carga de credenciales/llamada de
  red reales antes de llegar siquiera a intentar el lock, y además podía
  interferir con un worker de producción real corriendo en la misma
  máquina):**
  - **Prueba del lock, aislada del worker completo:** un script ayudante
    nuevo y mínimo, `tests/_ayudante_lock.py` — importa únicamente
    `adquirir_lock_worker()` de `fase8_worker_ingesta` (la función
    extraída sin efectos secundarios, ver sección 7), la llama, y luego
    espera (`time.sleep` largo o una señal) sin tocar Drive, fal.ai, ni
    hacer polling de nada. La prueba lanza este ayudante con
    `subprocess.Popen([sys.executable, "tests/_ayudante_lock.py"], env=
    {**os.environ, "GORROLANDIA_LOCK_PATH": str(ruta_lock_temporal)})`,
    espera a que confirme por stdout que adquirió el lock, y entonces
    intenta adquirir el mismo lock (mismo `GORROLANDIA_LOCK_PATH`) desde
    el propio proceso de pytest — debe fallar con `Timeout`. Terminar el
    ayudante (`proc.terminate()`/`proc.kill()` en un `finally`) y repetir
    la adquisición debe ahora tener éxito. La prueba de "una terminación
    abrupta libera el lock" mata el ayudante con `proc.kill()` (no
    `terminate()`, para simular un crash real, no un cierre ordenado) y
    confirma que el lock queda libre igual.
  - **Prueba de concurrencia de `inicializar_db()`:** otro ayudante
    mínimo, `tests/_ayudante_inicializar_db.py` — solo hace `import db;
    db.inicializar_db()` y termina. Se lanzan dos copias simultáneas con
    `subprocess.Popen(..., env={**os.environ, "GORROLANDIA_DB_PATH":
    str(ruta_temporal)})` apuntando a la misma base, y se confirma que
    ninguna termina con una excepción no manejada y que el esquema final
    es idéntico al de correrlo una sola vez.
  - Ambos ayudantes son los únicos subprocesos que las pruebas
    automatizadas lanzan — **ninguna prueba automatizada arranca
    `fase8_worker_ingesta.py` como proceso completo**; eso sería una
    prueba de integración de red real, fuera de alcance de este plan (ver
    "Fuera de alcance"), y ya está cubierto por la confirmación en vivo
    del Paso 2 del plan de validación.
  - Ambos ayudantes se lanzan con un timeout explícito
    (`proc.wait(timeout=10)`) y un bloque `finally` que termina el
    proceso (`proc.terminate()` seguido de `proc.kill()` si no responde)
    — ninguna prueba puede dejar un proceso huérfano corriendo tras
    fallar. Cada prueba de este tipo empieza con una aserción explícita
    de que la ruta resuelta (`ruta_temporal.resolve()`) está dentro de
    `tmp_path` de pytest, antes de dejar que el subproceso escriba nada —
    una salvaguarda barata contra que un error de configuración futuro
    vuelva a apuntar accidentalmente a la base o al lock reales.
- **Pruebas de Streamlit (panel):** no se levanta un servidor Streamlit
  real para las pruebas automatizadas — sería una dependencia de
  integración desproporcionada para este plan. En su lugar, las funciones
  de transición (`aprobar_trabajo`, `rechazar_trabajo`,
  `reintentar_trabajo`) y de consulta que alimentan al panel
  (`generaciones_de_trabajo`, etc.) se prueban directamente como funciones
  Python contra la base temporal — el panel en sí (código de UI de
  Streamlit) queda fuera de la cobertura automatizada y se verifica
  manualmente en el Paso 2 del plan de validación (confirmación en vivo),
  igual que ya se hacía antes de este plan.
- Las dos condiciones de carrera del punto 3 (rechazo humano contra
  reconciliación de QA en curso, y rechazo humano contra el movimiento a
  Drive en curso) y el caso de recuperación de Pista A con archivo
  existente-pero-corrupto (punto 1) se agregan explícitamente a esta
  lista, no solo se mencionan en prosa — están cubiertas más abajo, en
  las pruebas de `aprobar_trabajo()`/CAS y en la de recuperación de Pista
  A.

Todas las pruebas automatizadas de esta lista corren contra el archivo
SQLite temporal inyectado como se describe arriba, y mockean
`fal_client`/`requests` — ninguna prueba automatizada gasta dinero real.
Los pasos 1, 1.5 y 2 del plan de validación son la única parte que sí
llama a la API real, deliberadamente.

- **Migración de esquema:** aplicar `inicializar_db()` dos veces seguidas
  sobre la misma base (idempotencia); lanzarla desde dos hilos/procesos
  concurrentes y confirmar que ninguno lanza excepción no manejada.
- **Backfill (script separado), los 3 estados:** (a) 0 filas asignadas,
  69 elegibles → hace el `UPDATE`, verifica 69 afectadas, confirma; (b)
  69 ya asignadas, 0 sin asignar → no reintenta el `UPDATE`, sigue directo
  a re-QA (esto es lo que hace al script resumible de verdad); (c) estado
  intermedio/ambiguo (ni 0 ni 69 asignadas) → `ROLLBACK` y aborta con
  diagnóstico, nunca continúa a ciegas. Confirmar que correr el script dos
  veces seguidas no duplica evaluaciones (resumible por `VERSION_QA`) ni
  intenta re-backfillear. Confirmar que un backup con el mismo nombre ya
  existente hace abortar el script en vez de sobrescribirlo.
- **Auditoría de QA:** confirmar que `registrar_evaluacion_qa` nunca
  modifica `generaciones.score_qa`/`.problema`; confirmar que
  `ultima_evaluacion_vigente` usa orden por `id DESC` y no se confunde con
  empates de timestamp.
- **Regla de estado:** trabajo con todas sus evaluaciones vigentes en
  `qa_error` → `error`; con al menos una completa → `listo_para_revision`
  (incluyendo el caso del trabajo que hoy está en `aprobado`).
- **Normalización estricta + validación de esquema:** `True`, `False`,
  `"true"`, `"false"`, `"True"`, `" false "` → válidos; `None`, ausente,
  `0`, `1`, `[]`, `"si"` → `qa_error`, nunca `False` silencioso.
- **Reanudación por intento:** un `(trabajo_id, escena)` con un intento 1
  ya registrado y no aprobado → el siguiente intento usa el número 2, sin
  sobrescribir el archivo del intento 1.
- **Reanudación de Pista A:** con 2 de 3 formatos ya registrados y su
  archivo en disco, solo se inserta la fila faltante del tercero — nunca
  se duplican los 2 ya existentes.
- **Recuperación de Pista A con un archivo corrupto (no solo faltante):**
  registrar los 3 formatos con sus archivos válidos, corromper el archivo
  de uno de ellos (ej. truncarlo), correr la recuperación, y confirmar:
  (a) solo se regenera el archivo del formato corrupto, **sin insertar
  ninguna fila nueva ni actualizar la existente** — la fila original de
  ese formato sigue siendo la misma fila (mismo `id`), solo cambian los
  bytes del archivo en su `ruta_output`; (b) los otros 2 archivos
  conservan exactamente el mismo hash que antes de correr la
  recuperación; (c) la cuenta total de filas `compositing_local` para el
  trabajo sigue siendo 3, no 4.
- **Foreign keys:** confirmar que un intento de insertar en
  `evaluaciones_qa` con un `generacion_id` inexistente falla (con
  `PRAGMA foreign_keys = ON` activo) en vez de insertarse silenciosamente.
- **Orden de escritura:** confirmar que `registrar_generacion()` devuelve
  un id usable antes de que exista ninguna evaluación para esa fila, y que
  `generar_con_reintento()` sin `on_generada` no escribe nada en la base
  (caso de los scripts de demo/validación).
- **Descarga de resultados de fal.ai:** no-2xx, cuerpo HTML, imagen
  truncada, y un archivo de exactamente 50MB (pasa) vs 50MB+1 byte
  (abortado a mitad de descarga, sin dejar parcial) → ninguno deja un
  archivo final inválido.
- **Descarga de entrada desde Drive:** mismos casos, con el límite real de
  20MB (no 50MB — son límites distintos, uno por cada lado): exactamente
  20MB pasa, 20MB+1 byte se rechaza antes de completar la descarga.
- **Panel por trabajo:** dos trabajos con el mismo `sku` →
  `generaciones_de_trabajo` de cada uno devuelve solo sus propias filas.
- **`aprobar_trabajo()` con 0, 1, 2 y 3 escenas generadas de las 3
  esperadas:** solo con las 3 presentes y las 3 con una evaluación vigente
  **completa** (sin `qa_error`, sin importar si `aprobado` es 0 o 1)
  devuelve `"aprobado"` y cambia el estado; con cualquier escena faltante
  (nunca generada) devuelve `"escena_faltante"` y con alguna en `qa_error`
  devuelve `"qa_incompleto"` — ninguno de los dos cambia el estado.
- **QA falló pero el humano igual puede aprobar:** las 3 escenas con
  evaluación vigente completa y `aprobado=0` en al menos una →
  `aprobar_trabajo()` devuelve `"aprobado"` de todas formas — la falla
  automática no bloquea la decisión humana, solo la ausencia de una
  evaluación o un `qa_error` la bloquean.
- **Archivo borrado o corrupto después de `listo_para_revision`:** un
  trabajo con QA completo en las 3 escenas y los 3 formatos de Pista A,
  al que se le borra o corrompe (a) un formato de Pista A, o (b) el
  artefacto vigente de una escena de Pista B, **después** de llegar a
  `listo_para_revision` → `aprobar_trabajo()` devuelve `"artefacto_invalido"`
  en ambos casos, el trabajo permanece en `listo_para_revision` (no pasa a
  `aprobado` ni desaparece), y el panel muestra el mensaje de reparación
  manual correspondiente a ese código, no el genérico de "el trabajo
  cambió" que usan los otros códigos de fallo.
- **`aprobar_trabajo()` ante un cambio entre render y click:** marcar una
  escena en `qa_error` justo antes de llamar `aprobar_trabajo()` sobre un
  trabajo que el panel había mostrado como aprobable → devuelve
  `"qa_incompleto"`, el estado no cambia a `aprobado`.
- **Dos sesiones del panel aprobando/rechazando el mismo trabajo a la
  vez:** disparar `aprobar_trabajo()` y `rechazar_trabajo()` casi
  simultáneamente sobre el mismo `trabajo_id` (ambas parten de
  `listo_para_revision`) → exactamente una de las dos transiciones se
  aplica; la que pierde la carrera devuelve su código de "no aplicado"
  (`"estado_invalido"` para `aprobar_trabajo()`, `False` para
  `rechazar_trabajo()`) sin dejar el trabajo en un estado intermedio.
- **Rechazo humano contra reconciliación de QA en curso:** un trabajo en
  `listo_para_revision` con una escena pendiente de re-evaluación; se
  dispara `rechazar_trabajo()` justo antes de que la reconciliación
  termine de escribir la evaluación pendiente → el trabajo queda en
  `rechazado`, y cuando la reconciliación intenta luego recalcular/escribir
  el estado del trabajo, su `UPDATE ... WHERE estado IN (...)` no incluye
  `rechazado` como estado de origen, así que no afecta ninguna fila y el
  trabajo permanece `rechazado`.
- **Rechazo humano contra el movimiento a Drive en curso:** un trabajo que
  acaba de llegar a `listo_para_revision` y todavía tiene
  `drive_carpeta = NULL`; se dispara `rechazar_trabajo()` antes de que la
  reconciliación de movimiento (punto 7) procese ese trabajo → cuando la
  reconciliación sí lo procesa, relee el estado actual (`rechazado`, no
  el `listo_para_revision` que tenía cuando se encoló) inmediatamente
  antes de mover el archivo, y lo archiva en `rechazados`, nunca en
  `procesados`.
- **Intento máximo por escena decide, no cualquier intento:** una escena
  con intento 1 aprobado e intento 2 en `qa_error` no se cuenta como
  completa en `aprobar_trabajo()` ni en la regla de estado.
- **Fallo al persistir no dispara una llamada pagada de más:** simular que
  `registrar_evaluacion_qa` lanza una excepción (a) cuando el proveedor sí
  respondió con éxito, y (b) cuando el proveedor falló y se intentaba
  registrar el `qa_error` — en ambos casos la excepción se propaga sin que
  se dispare una llamada adicional al proveedor.
- **Sanitizador, cobertura completa:** valores con
  `Authorization: Bearer ...`, `token=...`/`api_key=...`/contraseñas, un
  cuerpo de respuesta malformado que contiene un secreto, y un valor que
  no es string (ej. `None`, una excepción) — todos redactados
  correctamente al persistir en base de datos, al mostrarse en el panel, y
  al imprimirse por consola/log del worker.
- **`drive_carpeta` sobrevive un fallo de generación:** un trabajo que
  llega a `listo_para_revision` pero cuyo movimiento a `procesados` lanza
  una excepción simulada se queda en `listo_para_revision` (no pasa a
  `error`), y la reconciliación lo archiva en un ciclo posterior.
- **Relocalización tras un rechazo posterior al archivado (corrige el
  caso central señalado por Codex, ronda 4):** un trabajo ya en
  `listo_para_revision` con `drive_carpeta = 'procesados'` (ya archivado
  normalmente); se le aplica `rechazar_trabajo()` → en el siguiente ciclo
  de reconciliación de movimiento, `destino_deseado('rechazado') =
  'rechazados' != 'procesados'`, así que el archivo se mueve de
  `procesados` a `rechazados` en Drive y `drive_carpeta` pasa a
  `'rechazados'` — nunca se queda archivado permanentemente en la carpeta
  equivocada solo porque ya se había archivado una vez.
- **La reconciliación de movimiento nunca decide con la caché sola:**
  mockear `files.get()` para que devuelva una carpeta real distinta de lo
  que dice `drive_carpeta` en la base (simulando una caché desactualizada
  por cualquier motivo — un CAS fallido anterior, o un crash entre el
  movimiento real y el `UPDATE` que lo registraba) → la reconciliación
  siempre consulta `files.get()` antes de decidir, nunca mueve ni dos
  veces (si la carpeta real ya es la deseada, no llama al movimiento, solo
  actualiza la caché) ni dejar de mover cuando hace falta.
- **Recuperación de un crash entre el movimiento real y el `UPDATE` local
  (corrige el caso central señalado por Codex, ronda 4):** simular que el
  movimiento en Drive tuvo éxito pero el proceso terminó (crash) antes de
  ejecutar o confirmar el `UPDATE` de `drive_carpeta` — la fila en la base
  queda con la caché vieja. Al reiniciar el worker y correr la
  reconciliación de nuevo, la consulta a `files.get()` (mockeada para
  devolver la ubicación real ya movida) revela que el archivo ya está
  donde debía, así que no se repite el movimiento — solo se actualiza la
  caché para que quede consistente. Confirma que no hace falta ningún
  estado "sucio" nuevo: la regla de "nunca confiar en la caché para
  decidir" ya cubre este caso sin tratamiento especial.
- **Relocalización con carrera genuina (rechazo humano entre el
  `UPDATE` con CAS y la siguiente pasada):** simular que el `UPDATE` de
  `drive_carpeta` con CAS falla (el `estado` cambió entre la lectura y el
  `UPDATE`, mockeando el cambio concurrente) → la siguiente pasada de
  reconciliación consulta `files.get()` (mockeada) antes de decidir,
  recalcula `destino_deseado` con el `estado` ya actualizado, y mueve el
  archivo a su destino correcto — sin quedar nunca en un bucle ni en una
  carpeta incorrecta de forma permanente.
- **Archivo de Pista B corrupto o borrado en el intento más reciente:**
  por debajo de `MAX_INTENTOS`, genera un intento nuevo; en el límite,
  queda marcado para revisión manual sin reintentar automáticamente.
- **`archivos_rechazados` evita re-descarga:** un archivo cuyo movimiento
  a `rechazados` falla la primera vez no se vuelve a descargar ni
  re-validar en el ciclo siguiente, solo se reintenta el movimiento.
- **Trabajos `procesando` huérfanos:** un trabajo dejado en `procesando`
  al reiniciar el worker vuelve a `pendiente` y se retoma.
- **`qa_error` no gasta un intento de generación:** con un intento
  existente en `qa_error` y su imagen válida en disco, el siguiente ciclo
  reintenta solo QA (no llama `funcion_generar`, no incrementa el número
  de intento).
- **Bloqueo de aprobación:** un trabajo con 1 de 3 escenas evaluadas no
  permite click en "Aprobar" en el panel; con las 3 evaluadas, sí.
- **`UNIQUE` de generaciones:** un intento de insertar dos filas para el
  mismo `(trabajo_id, modelo_ia, escena_id, intento)` falla con
  `IntegrityError`.
- **Redacción de URLs:** un mensaje de error que contiene una URL firmada
  se guarda y se muestra con `[URL redactada]`, nunca con la URL original.
- **Backfill sobre la forma real de los datos, corrido dos veces
  seguidas:** correr el backfill contra una copia de la base con
  exactamente las 30 filas de Pista A duplicadas en
  `(compositing_local, 'n/a', 1)` por trabajo (la forma real verificada) y
  confirmar que el paso de corrección de `escena_id` corre antes que el
  `UPDATE` de `trabajo_id` (misma transacción) y que el índice único no
  falla. Correrlo una **segunda** vez sobre el resultado y confirmar que
  detecta "ya normalizado / ya asignado" en ambos sub-pasos sin abortar
  por conteos en cero.
- **Lock desde distintos directorios de trabajo:** arrancar el worker dos
  veces con distinto `cwd` cada vez y confirmar que el segundo arranque
  falla igual (la ruta del lock se resuelve desde `ROOT`, no desde el
  directorio actual).
- **SKU inválido derivado del nombre de archivo:** un archivo de Drive con
  nombre vacío tras sanear, con solo puntos, o con un nombre reservado de
  Windows (`CON.jpg`) se rechaza y se mueve a `rechazados`, sin crear un
  trabajo con un SKU inventado.
- **Import de `VERSION_QA` sin ciclo:** importar `db.py` y
  `fase6_qa_reintento.py` en cualquier orden no falla — confirma que
  ninguno de los dos depende circularmente del otro para obtener
  `VERSION_QA`.
- **Rutas distintas por trabajo:** dos trabajos con el mismo `sku`
  producen archivos físicos en directorios distintos, con contenido
  verificado, no solo aislamiento en la consulta.
- **Instancia única:** arrancar un segundo proceso worker mientras el
  primero corre falla inmediatamente por el lock de archivo.
- **Reconciliación alcanzable desde `ciclo_una_vez()`:** un trabajo en
  `listo_para_revision` con una escena en `qa_error` se recupera (llega a
  tener las 3 escenas evaluadas y se vuelve aprobable) en un ciclo
  posterior, sin necesidad de llamar el guard directamente. Un trabajo en
  `error` no se mueve en Drive durante la reconciliación.
- **Última evaluación completa gana:** una evaluación aprobada vieja
  seguida de un `qa_error` más reciente para la misma generación hace que
  `ultima_evaluacion_vigente()` devuelva el `qa_error`, no la aprobación
  vieja — y que el backfill NO la salte como si ya estuviera resuelta.
- **Auditoría de llamadas internas de QA:** si el primer intento de
  parseo falla y el reintento interno tiene éxito, quedan **dos** filas en
  `evaluaciones_qa` para esa generación (una `qa_error`, una completa), y
  el costo total sumado (fórmula de dos sumas separadas) incluye ambas.
- **Lock crash-safe:** matar el proceso worker abruptamente (no un cierre
  ordenado) y confirmar que un arranque posterior adquiere el lock sin
  intervención manual.
- **Reintentar trabajo en error:** un trabajo en `error` con generaciones
  parciales ya registradas, al pasar a `pendiente` vía el botón del panel,
  no rehace ni duplica lo que ya estaba completo.
- **Reconciliación excluye rechazados:** un trabajo `rechazado` con una
  escena en `qa_error` no genera nuevas llamadas de QA en ciclos
  posteriores; un trabajo `error` no se mueve en la reconciliación de
  Drive.
- **QA agotado, acotado por versión:** tras 6 filas en `evaluaciones_qa`
  para `(generacion_id, VERSION_QA)` con la más reciente en `qa_error`,
  ninguna llamada adicional al proveedor se dispara para esa versión, y el
  panel la marca como agotada.
- **Una versión de QA nueva no hereda el agotamiento de la vieja:** una
  `generacion_id` con 6 filas agotadas bajo `VERSION_QA="v1"` sí permite
  una llamada nueva si se sube `VERSION_QA` a `"v2"` — el límite es por
  versión, no global para la generación.
- **Aprobación vieja no enmascara agotamiento reciente:** una `generacion_id`
  con una fila completa seguida de 6 `qa_error` (misma versión) se marca
  agotada igual — la fila completa vieja no cuenta como "todavía tiene
  esperanza", porque ya no es la evaluación vigente.
- **Excepción de transporte durante QA:** simular que `fal_client.subscribe`
  lanza (timeout/red/auth) en vez de devolver una respuesta malformada, y
  confirmar que igual se registra una fila `qa_error` con la URL/detalle
  redactado, sin propagar la excepción cruda hacia arriba.
- Los pasos 1, 1.5 y 2 de validación son la prueba de integración real
  contra la API.

## Rollback

Sin despliegue ni tráfico en producción — rollback de **código** es `git
revert`, y es seguro por sí solo para todo excepto el punto siguiente.

**El rollback de código NO deshace el backfill/re-QA** (aclaración —
la versión anterior decía que la base "queda intacta", lo cual no es del
todo cierto): después de correr `fase8_backfill_historico.py`, el trabajo
que estaba en `aprobado` pasa a `listo_para_revision` como parte normal
del proceso — eso es un cambio de dato real, no solo de esquema. Revertir
el código no revierte esa invalidación. Si específicamente se necesita
deshacer el backfill (no solo el código), la única vía es restaurar el
backup de SQLite tomado en el punto 6 (`output/gorrolandia.db.bak-*`,
verificado con `PRAGMA integrity_check` al crearse) — con el worker y el
panel detenidos, igual que al aplicar la migración. No hay
"down-migration" automática, ni se justifica una dado el tamaño del
proyecto.

## Fuera de alcance / no aplica (con justificación)

- **Defensa completa contra decompression bombs** (validación progresiva
  de codecs, límites de memoria a nivel de proceso, etc.): carpeta de
  Drive privada, compartida solo con la cuenta de servicio del propio
  dueño de la tienda — no hay adversario externo subiendo archivos
  maliciosos a propósito. Ajustado respecto a la ronda anterior: sí se
  agrega un chequeo barato de dimensiones de píxeles (punto 8) porque
  cubre también el caso accidental (un archivo corrupto o con metadata
  rara), no solo el malicioso — la razón para no ir más lejos es de
  costo/beneficio, no de "no hay riesgo en absoluto".
- **Lease con expiración para múltiples workers concurrentes:** en vez de
  eso, un lock de archivo simple (punto 7) hace que un segundo arranque
  accidental falle rápido — proporcional para "un solo worker por diseño",
  sin construir coordinación entre workers que no están destinados a
  coexistir.
- **Reescribir `fase7_consultas.py`** contra el nuevo esquema de
  `evaluaciones_qa`: es un reporte de una sola vez ya generado y cerrado
  (`resultados-fase7.md`). Si se necesita ese tipo de reporte agregado de
  nuevo en el futuro, se escribe contra `evaluaciones_qa` en ese momento.
- **Migrar `fase7_poblar_registro.py` al patrón nuevo:** se retira en vez
  de migrarse (ver punto 5) — no hay razón de negocio para que vuelva a
  correr, y retirarlo es más simple y más seguro que portarlo.
- **Tabla de versión de esquema formal** más allá de `evaluaciones_qa` y
  la columna `trabajo_id`: desproporcionado para este cambio.
- **Máquina de estados de resumibilidad completa** (un estado explícito
  por cada combinación de generación/QA/movimiento en Drive, con
  transiciones formales): las tres pasadas de `ciclo_una_vez()` (punto 7 —
  trabajos huérfanos, trabajos pendientes, reconciliación de QA
  incompleta y movimiento en Drive) cubren los casos reales que importan
  ahora sin necesitar una máquina de estados formal separada.
- **Ficha estructurada por SKU, catálogo de escenas por dificultad,
  reserva de presupuesto, reconciliación con facturación del proveedor,
  estados `no_verificable`/`no_aplica`, panel con recortes/diffs:** siguen
  fuera de alcance, del plan original más amplio.
- No se toca la lógica interna de composición de
  `fase5_pista_a_produccion.py` (recorte, fondo, sombra) — el único cambio
  es agregarle un parámetro `formatos` opcional para poder generar un
  subconjunto (punto 7), con `None` como default que preserva el
  comportamiento y la prueba de determinismo de Fase 5 sin cambios.
- Autenticación/autorización más allá de restringir el panel a localhost
  (punto 10): no hay servidor público ni usuarios externos.
