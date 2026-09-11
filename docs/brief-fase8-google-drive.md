# Fase 8 — Automatización end-to-end (Drive → cola → generación → QA → panel)

## Estado

Arquitectura completa y probada, **excepto la conexión real a Google Drive**
(pendiente de credenciales del usuario).

| Pieza | Archivo | Estado |
|---|---|---|
| Cola de trabajos (SQLite, tabla `trabajos`) | `src/db.py` | ✅ Probado |
| Cliente de Google Drive (cuenta de servicio) | `src/fase8_drive_cliente.py` | ⏳ Escrito, sin probar (falta credencial) |
| Worker de polling (Drive → cola → Pista A/B → QA) | `src/fase8_worker_ingesta.py` | ⏳ Escrito, sin probar end-to-end |
| Panel de revisión (Streamlit) | `src/fase8_panel_revision.py` | ✅ Probado en navegador (aprobar/rechazar, costo/score por ítem) |

## Qué falta del usuario

1. Crear proyecto en Google Cloud + habilitar Drive API + cuenta de servicio
   con clave JSON (pasos detallados ya compartidos en el chat).
2. Compartir la carpeta de Drive de ingesta con el `client_email` de la cuenta
   de servicio (permiso Editor).
3. Pasar la ruta del archivo JSON descargado y el ID de la carpeta de Drive.

## Cómo configurar una vez se tengan las credenciales

1. Guardar el JSON descargado en `credentials/service-account.json` (la
   carpeta `credentials/` ya está en `.gitignore`, nunca se sube a git).
2. En `.env`, completar:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=credentials/service-account.json
   GOOGLE_DRIVE_FOLDER_ID=<el id de la carpeta>
   ```

## Cómo correr

**Worker de ingesta** (procesa la cola continuamente, cada 60s revisa Drive):
```bash
python src/fase8_worker_ingesta.py
```
Para una sola pasada (útil para probar sin dejarlo corriendo):
```bash
python src/fase8_worker_ingesta.py --once
```

**Panel de revisión:**
```bash
streamlit run src/fase8_panel_revision.py
```

## Diseño de decisiones ya tomadas

- **Polling, no webhook** — decisión del usuario, evita necesitar un servidor
  público expuesto a internet.
- **Escenas fijas de producción** (`ESCENAS_PRODUCCION = ["04", "09", "29"]`
  en `fase8_worker_ingesta.py`): correr Pista B contra las 33 escenas del
  banco por cada SKU nuevo sería caro y lento. Se usa un subconjunto fijo de 3
  como muestra representativa para el panel de revisión — ajustar esta lista
  cuando se pase a volumen real.
- **sku derivado del nombre de archivo**: el SKU de cada trabajo es el nombre
  del archivo subido a Drive sin extensión (ej. `HOMIE-BLK-002.jpg` →
  `HOMIE-BLK-002`). Asumido, no confirmado con el usuario — avisar si el
  proceso real de nombrado de archivos es distinto.
- **Archivos procesados se mueven a una subcarpeta `procesados` dentro de
  Drive** (creada automáticamente la primera vez) para no reprocesarlos en
  el siguiente ciclo de polling.

## Criterio de aprobación de la fase (pendiente de validar)

Subir 10 SKU nuevos a la carpeta de Drive sin tocar código ni consola, y
verse aparecer en el panel de revisión como listos para aprobar, con costo y
score visibles por ítem. Como no hay 10 fotos de producto reales distintas,
se seguirá el mismo criterio que en Fase 7: simular con la misma foto de
HOMIE-BLK-001 subida 10 veces con nombres de archivo distintos, salvo que el
usuario prefiera conseguir fotos reales.
