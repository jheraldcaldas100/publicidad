"""
Fase 8 - Backfill historico, de una sola vez, genuinamente resumible.

Corrige la base de datos real para que las filas historicas (previas a este
plan de correccion) queden compatibles con las nuevas invariantes:
- Pista A: la columna escena_id pasa de 'n/a' a el formato real (4x5/1x1/9x16),
  derivado del nombre de archivo ya guardado en ruta_output.
- generaciones.trabajo_id se asigna por sku (cada sku historico corresponde a
  exactamente un trabajo).
- trabajos.drive_carpeta se marca 'procesados' para los trabajos historicos
  (el worker viejo ya los archivo alli en su momento).
- Las 39 generaciones de Pista B se re-evaluan con el prompt/esquema de QA
  nuevo (VERSION_QA) - esto SI hace llamadas reales y pagadas a fal.ai.
- La regla unica de estado se re-aplica a los trabajos afectados, incluyendo
  el que hoy esta 'aprobado' (reabierto explicitamente aqui - la
  reconciliacion recurrente del worker nunca vuelve a tocar un trabajo
  aprobado, a proposito; este backfill es la unica excepcion, y solo corre
  una vez).

Prerequisito obligatorio: detener fase8_worker_ingesta.py y cerrar el panel
de Streamlit ANTES de correr este script - no hay un estado "reevaluando"
nuevo en la base para esto, es proporcional pedirle al operador que pare los
dos procesos a mano antes de una migracion de datos de una sola vez.

Uso: python fase8_backfill_historico.py
"""
import sys
from datetime import datetime
from pathlib import Path

import db
from fase6_qa_reintento import evaluar_calidad
from fase8_worker_ingesta import _calcular_estado_final, _ruta_escena
from prompts import VERSION_QA

ROOT = Path(__file__).resolve().parent.parent


def abortar(mensaje: str) -> None:
    sys.exit(f"[backfill] ABORTADO: {mensaje}")


def confirmar_prerequisitos() -> None:
    print(
        "Antes de continuar, confirma que:\n"
        "  1. fase8_worker_ingesta.py NO esta corriendo.\n"
        "  2. El panel de Streamlit (fase8_panel_revision.py) esta cerrado.\n"
    )
    respuesta = input("Escribe 'si' para confirmar y continuar: ").strip().lower()
    if respuesta != "si":
        abortar("no se confirmaron los prerequisitos")


# ---------------------------------------------------------------------------
# Paso 1: backup con la API de backup de SQLite (segura sobre una base viva,
# a diferencia de una copia cruda de archivo que puede capturar un WAL a
# medias)
# ---------------------------------------------------------------------------

def hacer_backup() -> Path:
    import sqlite3

    origen_path = db.DB_PATH.resolve()
    carpeta_backups = origen_path.parent / "backups"
    destino_path = carpeta_backups / f"{origen_path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}"

    if not origen_path.is_file():
        abortar(f"no existe la base de datos en {origen_path} - nada que respaldar")
    carpeta_backups.mkdir(parents=True, exist_ok=True)
    if destino_path.exists():
        abortar("ya existe un backup con ese nombre - resolver antes de continuar")

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
        if origen is not None:
            origen.close()
        if destino is not None:
            destino.close()
        if not exito:
            destino_path.unlink(missing_ok=True)

    print(f"[backfill] Backup creado en: {destino_path}")
    return destino_path


# ---------------------------------------------------------------------------
# Paso 2: inicializar esquema + validar artefactos historicos ANTES de tocar
# cualquier fila de datos
# ---------------------------------------------------------------------------

def inicializar_y_validar_artefactos() -> None:
    # Nota de precision: esto YA modifica el esquema (columnas/indices
    # nuevos, idempotentes) aunque el paso siguiente aborte - el backup del
    # paso 1 ya se tomo antes, asi que restaurarlo deshace tambien el
    # cambio de esquema si hiciera falta. Lo que NO se modifica si este
    # paso aborta es ninguna fila de datos de negocio.
    db.inicializar_db()

    con = db.conectar()
    try:
        filas = con.execute(
            "SELECT id, ruta_output FROM generaciones WHERE ruta_output IS NOT NULL"
        ).fetchall()
    finally:
        con.close()

    invalidas = [(fid, ruta) for fid, ruta in filas if not db.archivo_es_imagen_valida(ruta)]
    if invalidas:
        detalle = "\n".join(f"  generacion #{fid}: {ruta}" for fid, ruta in invalidas)
        abortar(
            f"{len(invalidas)} fila(s) de generaciones tienen ruta_output faltante o "
            f"corrupta - resolver antes de continuar:\n{detalle}"
        )
    print(f"[backfill] {len(filas)} archivos historicos verificados OK.")


# ---------------------------------------------------------------------------
# Paso 3: normalizar escena_id de Pista A + asignar trabajo_id, en una sola
# transaccion
# ---------------------------------------------------------------------------

def _formato_desde_ruta(ruta_output: str) -> str | None:
    """El formato (4x5/1x1/9x16) vive en el nombre de archivo historico:
    '<sku>_producto_<formato>.jpg' - mismo parseo que ya usaba el panel
    viejo (Path(ruta).stem.split('_')[-1])."""
    formato = Path(ruta_output).stem.split("_")[-1]
    return formato if formato in ("4x5", "1x1", "9x16") else None


def migrar_escena_id_y_trabajo_id() -> None:
    con = db.conectar()
    con.execute("BEGIN IMMEDIATE")
    try:
        # --- 3a: normalizar escena_id de Pista A ---
        # idempotente por fila: una fila con escena_id != 'n/a' ya esta
        # normalizada y no vuelve a matchear el WHERE, asi que correr esto
        # dos veces no la toca de nuevo.
        pendientes_pista_a = con.execute(
            "SELECT id, ruta_output FROM generaciones WHERE modelo_ia = 'compositing_local' AND escena_id = 'n/a'"
        ).fetchall()
        for gen_id, ruta_output in pendientes_pista_a:
            formato = _formato_desde_ruta(ruta_output)
            if formato is None:
                con.rollback()
                abortar(f"no se pudo derivar el formato desde ruta_output de la generacion #{gen_id}: {ruta_output!r}")
            con.execute("UPDATE generaciones SET escena_id = ? WHERE id = ?", (formato, gen_id))
        print(f"[backfill] Pista A: {len(pendientes_pista_a)} fila(s) normalizadas (escena_id -> formato).")

        # --- 3b: asignar trabajo_id por sku, con los 3 estados resumibles ---
        sin_asignar = con.execute("SELECT COUNT(*) FROM generaciones WHERE trabajo_id IS NULL").fetchone()[0]
        con_asignar = con.execute("SELECT COUNT(*) FROM generaciones WHERE trabajo_id IS NOT NULL").fetchone()[0]

        if sin_asignar == 0:
            print("[backfill] trabajo_id: ya estaba asignado en una corrida anterior, no se hace nada.")
        elif con_asignar == 0:
            skus_pendientes = [
                fila[0] for fila in con.execute(
                    "SELECT DISTINCT sku FROM generaciones WHERE trabajo_id IS NULL"
                ).fetchall()
            ]
            for sku in skus_pendientes:
                trabajos_del_sku = con.execute(
                    "SELECT id FROM trabajos WHERE sku = ?", (sku,)
                ).fetchall()
                if len(trabajos_del_sku) != 1:
                    con.rollback()
                    abortar(
                        f"sku {sku!r} tiene {len(trabajos_del_sku)} trabajo(s) coincidentes "
                        f"(se esperaba exactamente 1) - resolver manualmente antes de continuar"
                    )
                trabajo_id = trabajos_del_sku[0][0]
                con.execute(
                    "UPDATE generaciones SET trabajo_id = ? WHERE sku = ? AND trabajo_id IS NULL",
                    (trabajo_id, sku),
                )
            print(f"[backfill] trabajo_id: asignado para {sin_asignar} fila(s) en {len(skus_pendientes)} sku(s).")
        else:
            con.rollback()
            abortar(
                f"estado ambiguo de trabajo_id: {con_asignar} fila(s) ya asignadas y {sin_asignar} sin asignar "
                f"- ni 'nada hecho' ni 'todo hecho', requiere revision manual antes de continuar"
            )

        # --- 4: drive_carpeta = 'procesados' para los trabajos historicos,
        # SIN excluir el que esta en 'aprobado' - la ubicacion fisica en
        # Drive es independiente del estado de negocio, y ese archivo ya
        # esta fisicamente en 'procesados' sin importar que este backfill
        # lo reabra o no.
        cur = con.execute("UPDATE trabajos SET drive_carpeta = 'procesados' WHERE drive_carpeta IS NULL")
        print(f"[backfill] drive_carpeta: marcado 'procesados' para {cur.rowcount} trabajo(s) historico(s).")

        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Paso 5: re-QA de las generaciones de Pista B bajo VERSION_QA - llamadas
# reales y pagadas a fal.ai, genuinamente resumible via
# ultima_evaluacion_vigente()
# ---------------------------------------------------------------------------

def reevaluar_pista_b() -> None:
    con = db.conectar()
    con.row_factory = db.sqlite3.Row
    try:
        filas = con.execute(
            "SELECT * FROM generaciones WHERE modelo_ia = 'nano_banana' ORDER BY id"
        ).fetchall()
    finally:
        con.close()

    total = len(filas)
    saltadas = 0
    evaluadas = 0
    fallidas = 0

    for fila in filas:
        ya_vigente = db.ultima_evaluacion_vigente(fila["id"], VERSION_QA)
        if ya_vigente is not None:
            saltadas += 1
            continue

        if not db.archivo_es_imagen_valida(fila["ruta_output"]):
            print(f"[backfill] generacion #{fila['id']} (sku={fila['sku']}, escena={fila['escena_id']}): "
                  f"archivo invalido, no se puede re-evaluar - requiere reparacion manual, se omite.")
            fallidas += 1
            continue

        trabajo = db.obtener_trabajo(fila["trabajo_id"])
        if trabajo is None:
            print(f"[backfill] generacion #{fila['id']}: sin trabajo_id valido, se omite.")
            fallidas += 1
            continue

        ruta_producto = Path(trabajo["ruta_local_foto"])
        ruta_escena = _ruta_escena(fila["escena_id"])
        qa = evaluar_calidad(ruta_producto, ruta_escena, Path(fila["ruta_output"]), generacion_id=fila["id"])
        estado_txt = "qa_error" if qa.get("qa_error") else f"score={qa['score']}"
        print(f"[backfill] generacion #{fila['id']} (sku={fila['sku']}, escena={fila['escena_id']}): {estado_txt}")
        evaluadas += 1

    print(f"[backfill] Re-QA de Pista B: {total} fila(s) totales, {saltadas} ya vigentes (saltadas), "
          f"{evaluadas} re-evaluadas, {fallidas} omitidas por archivo/trabajo invalido.")


# ---------------------------------------------------------------------------
# Paso 6: re-aplicar la regla unica de estado a los trabajos afectados,
# incluyendo el que hoy esta 'aprobado' (reabierto explicitamente)
# ---------------------------------------------------------------------------

def reaplicar_regla_de_estado() -> None:
    afectados = list(db.listar_trabajos(estado="listo_para_revision")) + list(db.listar_trabajos(estado="aprobado"))
    for trabajo in afectados:
        nuevo_estado = _calcular_estado_final(trabajo["id"])
        if nuevo_estado != trabajo["estado"]:
            print(f"[backfill] trabajo #{trabajo['id']} ({trabajo['sku']}): "
                  f"{trabajo['estado']} -> {nuevo_estado} (recalculado con VERSION_QA={VERSION_QA})")
        db.actualizar_estado_trabajo(trabajo["id"], nuevo_estado)


def main():
    print(f"[backfill] Base de datos: {db.DB_PATH}")
    confirmar_prerequisitos()

    hacer_backup()
    inicializar_y_validar_artefactos()
    migrar_escena_id_y_trabajo_id()

    print(
        "\n[backfill] A continuacion se re-evaluaran con QA las generaciones de Pista B "
        "bajo el prompt/esquema nuevo. Esto hace llamadas REALES y PAGADAS a fal.ai "
        "(~$0.02 por fila no evaluada todavia).\n"
    )
    respuesta = input("Escribe 'si' para continuar con la re-evaluacion de QA: ").strip().lower()
    if respuesta != "si":
        print("[backfill] Re-evaluacion de QA omitida por el operador. El resto de la migracion ya se aplico.")
        return

    reevaluar_pista_b()
    reaplicar_regla_de_estado()
    print("\n[backfill] Completado.")


if __name__ == "__main__":
    main()
