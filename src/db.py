"""
Fase 7/8 - Registro y trazabilidad + transiciones de estado de trabajos.

Base de datos SQLite: generaciones (cada llamada de generacion, Pista A o
Pista B), evaluaciones_qa (cada evaluacion de calidad sobre una generacion,
versionada por VERSION_QA), y trabajos (una fila por foto ingresada desde
Drive, con su estado en el flujo de revision humana).
"""
import datetime
import os
import sqlite3
from pathlib import Path

from PIL import Image

from prompts import ESCENAS_PRODUCCION, VERSION_QA

ROOT = Path(__file__).resolve().parent.parent

# Sobreescribible por variable de entorno - el codigo de produccion nunca la
# fija (usa el valor por defecto real); solo el arnes de pruebas la fija
# antes de lanzar un subproceso, para que ese subproceso la lea al importar
# este modulo desde cero (necesario en Windows, donde subprocess.Popen no
# hereda un monkeypatch hecho en el proceso padre).
DB_PATH = Path(os.environ.get("GORROLANDIA_DB_PATH", str(ROOT / "output" / "gorrolandia.db")))

# limite de filas de evaluaciones_qa por (generacion_id, VERSION_QA) antes de
# considerar la escena "agotada" - ver qa_agotado() mas abajo.
LIMITE_INTENTOS_QA_POR_VERSION = 6

ESQUEMA = """
CREATE TABLE IF NOT EXISTS trabajos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creado_en TEXT NOT NULL,
    actualizado_en TEXT NOT NULL,
    drive_file_id TEXT NOT NULL UNIQUE,
    drive_file_name TEXT NOT NULL,
    sku TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    ruta_local_foto TEXT,
    error TEXT,
    drive_carpeta TEXT
);

CREATE TABLE IF NOT EXISTS generaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    sku TEXT NOT NULL,
    escena_id TEXT,
    modelo_ia TEXT NOT NULL,
    prompt TEXT,
    seed TEXT,
    intento INTEGER NOT NULL DEFAULT 1,
    score_qa INTEGER,
    problema TEXT,
    costo_usd REAL NOT NULL DEFAULT 0.0,
    ruta_output TEXT,
    trabajo_id INTEGER REFERENCES trabajos(id)
);

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

CREATE TABLE IF NOT EXISTS archivos_rechazados (
    drive_file_id TEXT PRIMARY KEY,
    razon TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    movido INTEGER NOT NULL DEFAULT 0
);
"""

# estados posibles de un trabajo, en orden del flujo:
# pendiente -> procesando -> listo_para_revision -> aprobado | rechazado
# (o -> error si algo falla en el procesamiento; "Reintentar" regresa un
# trabajo en error a pendiente)


def _ahora() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def conectar() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def _migrar_columna_si_hace_falta(con: sqlite3.Connection, tabla: str, columna: str, definicion_sql: str) -> None:
    columnas = [fila[1] for fila in con.execute(f"PRAGMA table_info({tabla})").fetchall()]
    if columna in columnas:
        return
    con.execute("BEGIN IMMEDIATE")
    try:
        columnas = [fila[1] for fila in con.execute(f"PRAGMA table_info({tabla})").fetchall()]
        if columna not in columnas:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion_sql}")
        con.commit()
    except Exception:
        con.rollback()
        raise


def inicializar_db() -> None:
    """Idempotente. Crea tablas/columnas/indices que falten. Segura en base
    nueva o existente. NO ejecuta el backfill historico (ver
    fase8_backfill_historico.py) - esa es una accion separada de una sola
    vez, no parte del arranque."""
    con = conectar()
    try:
        con.executescript(ESQUEMA)  # incluye trabajo_id y trabajos.drive_carpeta en los CREATE TABLE para bases nuevas
        _migrar_columna_si_hace_falta(con, "generaciones", "trabajo_id", "INTEGER REFERENCES trabajos(id)")
        _migrar_columna_si_hace_falta(con, "trabajos", "drive_carpeta", "TEXT")
        # el indice unico se crea DESPUES de la migracion de trabajo_id, nunca
        # dentro de ESQUEMA: ESQUEMA se ejecuta primero contra una base que
        # puede ser la real existente, donde generaciones.trabajo_id todavia
        # no existe hasta que la migracion de arriba termina - crear el
        # indice antes fallaria con "no such column: trabajo_id".
        con.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_generaciones_intento
            ON generaciones(trabajo_id, modelo_ia, escena_id, intento)
            WHERE trabajo_id IS NOT NULL
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_generaciones_trabajo ON generaciones(trabajo_id, timestamp)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_evaluaciones_generacion ON evaluaciones_qa(generacion_id, id)")
        con.commit()
    finally:
        con.close()


def archivo_es_imagen_valida(ruta) -> bool:
    """True si la ruta existe y decodifica como una imagen valida."""
    try:
        ruta = Path(ruta)
        if not ruta.is_file():
            return False
        with Image.open(ruta) as img:
            img.verify()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# generaciones
# ---------------------------------------------------------------------------

def registrar_generacion(*, sku: str, escena_id, modelo_ia: str, prompt: str, seed: str,
                          intento: int, ruta_output, costo_usd: float = 0.0,
                          trabajo_id: int | None = None) -> int:
    """Registra una generacion y devuelve su id - necesario para poder
    asociarle despues una evaluacion de QA con registrar_evaluacion_qa().
    Las columnas score_qa/problema (heredadas de antes de que
    evaluaciones_qa existiera) ya no se llenan en filas nuevas; quedan como
    snapshot congelado en las filas historicas."""
    con = conectar()
    try:
        cur = con.execute(
            """INSERT INTO generaciones
               (timestamp, sku, escena_id, modelo_ia, prompt, seed, intento,
                costo_usd, ruta_output, trabajo_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_ahora(), sku, escena_id, modelo_ia, prompt, seed, intento,
             costo_usd, str(ruta_output) if ruta_output else None, trabajo_id),
        )
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def generaciones_de_sku(sku: str) -> list[sqlite3.Row]:
    con = conectar()
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            "SELECT * FROM generaciones WHERE sku = ? ORDER BY timestamp ASC", (sku,)
        ).fetchall()
    finally:
        con.close()


def generaciones_de_trabajo(trabajo_id: int) -> list[sqlite3.Row]:
    """A diferencia de generaciones_de_sku, aisla correctamente dos trabajos
    que comparten el mismo sku."""
    con = conectar()
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            "SELECT * FROM generaciones WHERE trabajo_id = ? ORDER BY timestamp ASC", (trabajo_id,)
        ).fetchall()
    finally:
        con.close()


def generaciones_pista_a(trabajo_id: int) -> list[sqlite3.Row]:
    con = conectar()
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            "SELECT * FROM generaciones WHERE trabajo_id = ? AND modelo_ia = 'compositing_local'",
            (trabajo_id,),
        ).fetchall()
    finally:
        con.close()


def generacion_mas_reciente(trabajo_id: int, modelo_ia: str, escena_id: str) -> sqlite3.Row | None:
    con = conectar()
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            """SELECT * FROM generaciones WHERE trabajo_id = ? AND modelo_ia = ? AND escena_id = ?
               ORDER BY intento DESC LIMIT 1""",
            (trabajo_id, modelo_ia, escena_id),
        ).fetchone()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# evaluaciones_qa
# ---------------------------------------------------------------------------

def registrar_evaluacion_qa(generacion_id: int, *, modelo_qa: str, version_prompt_qa: str = None,
                             score: int | None = None, aprobado: bool = False, qa_error: bool = False,
                             detalle: str = "", resultado_json: str = "", costo_usd: float = 0.0) -> int:
    con = conectar()
    try:
        cur = con.execute(
            """INSERT INTO evaluaciones_qa
               (generacion_id, timestamp, modelo_qa, version_prompt_qa, score,
                aprobado, qa_error, detalle, resultado_json, costo_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (generacion_id, _ahora(), modelo_qa, version_prompt_qa or VERSION_QA, score,
             int(bool(aprobado)), int(bool(qa_error)), detalle, resultado_json, costo_usd),
        )
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def ultima_evaluacion_vigente(generacion_id: int, version: str = None) -> sqlite3.Row | None:
    """La UNICA evaluacion que cuenta para cualquier decision (aprobar,
    regla de estado, agotamiento) - siempre la de id mas alto para esta
    version, nunca "alguna evaluacion que diga X"."""
    con = conectar()
    con.row_factory = sqlite3.Row
    try:
        return con.execute(
            """SELECT * FROM evaluaciones_qa
               WHERE generacion_id = ? AND version_prompt_qa = ?
               ORDER BY id DESC LIMIT 1""",
            (generacion_id, version or VERSION_QA),
        ).fetchone()
    finally:
        con.close()


def contar_evaluaciones(generacion_id: int, version: str = None) -> int:
    con = conectar()
    try:
        return con.execute(
            "SELECT COUNT(*) FROM evaluaciones_qa WHERE generacion_id = ? AND version_prompt_qa = ?",
            (generacion_id, version or VERSION_QA),
        ).fetchone()[0]
    finally:
        con.close()


def qa_agotado(generacion_id: int, version: str = None) -> bool:
    """Agotado = al menos LIMITE_INTENTOS_QA_POR_VERSION filas para esta
    version Y la mas reciente de esas filas es qa_error - consistente con
    "la ultima evaluacion vigente manda", nunca "ninguna es completa"."""
    version = version or VERSION_QA
    if contar_evaluaciones(generacion_id, version) < LIMITE_INTENTOS_QA_POR_VERSION:
        return False
    ultima = ultima_evaluacion_vigente(generacion_id, version)
    return ultima is not None and ultima["qa_error"] == 1


# ---------------------------------------------------------------------------
# trabajos - creacion y transiciones no disputadas (solo el worker las llama,
# nunca compiten con una accion del panel porque el panel solo actua sobre
# listo_para_revision)
# ---------------------------------------------------------------------------

def crear_trabajo(drive_file_id: str, drive_file_name: str, sku: str, ruta_local_foto: str) -> int | None:
    """Crea un trabajo nuevo si el drive_file_id no existe todavia. Devuelve el
    id del trabajo, o None si ya existia (evita reprocesar el mismo archivo)."""
    con = conectar()
    ahora = _ahora()
    try:
        cur = con.execute(
            """INSERT INTO trabajos
               (creado_en, actualizado_en, drive_file_id, drive_file_name, sku,
                estado, ruta_local_foto)
               VALUES (?, ?, ?, ?, ?, 'pendiente', ?)""",
            (ahora, ahora, drive_file_id, drive_file_name, sku, ruta_local_foto),
        )
        con.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # drive_file_id ya registrado
    finally:
        con.close()


def actualizar_estado_trabajo(trabajo_id: int, estado: str, error: str = "") -> None:
    """Solo para transiciones lineales exclusivas del worker (pendiente ->
    procesando, procesando -> listo_para_revision/error, reseteo de
    huerfanos procesando -> pendiente al arrancar) - el panel nunca actua
    sobre esos estados de origen, asi que no hay con quien competir. Las
    transiciones que SI puede disparar un humano (aprobar/rechazar/
    reintentar) usan las funciones con CAS de abajo, nunca esta."""
    con = conectar()
    con.execute(
        "UPDATE trabajos SET estado = ?, actualizado_en = ?, error = ? WHERE id = ?",
        (estado, _ahora(), error, trabajo_id),
    )
    con.commit()
    con.close()


def actualizar_drive_carpeta(trabajo_id: int, carpeta: str, estado_esperado: str) -> bool:
    """CAS: solo persiste si el trabajo sigue en estado_esperado (el que se
    leyo antes de llamar a la API de Drive). Si el estado cambio mientras
    tanto (0 filas afectadas), el llamador no necesita hacer nada especial -
    drive_carpeta es solo una cache; el proximo ciclo de reconciliacion
    vuelve a consultar la ubicacion real antes de decidir, nunca confia en
    esta columna para decidir un movimiento."""
    con = conectar()
    try:
        cur = con.execute(
            "UPDATE trabajos SET drive_carpeta = ? WHERE id = ? AND estado = ?",
            (carpeta, trabajo_id, estado_esperado),
        )
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def actualizar_drive_carpeta_observada(trabajo_id: int, carpeta: str) -> None:
    """Persiste sin condicion la ubicacion fisica real observada via la API
    de Drive - es un hecho fisico, no una decision de negocio, asi que no
    compite con ninguna transicion de estado humana."""
    con = conectar()
    con.execute("UPDATE trabajos SET drive_carpeta = ? WHERE id = ?", (carpeta, trabajo_id))
    con.commit()
    con.close()


def listar_trabajos(estado: str | None = None) -> list[sqlite3.Row]:
    con = conectar()
    con.row_factory = sqlite3.Row
    try:
        if estado:
            return con.execute(
                "SELECT * FROM trabajos WHERE estado = ? ORDER BY creado_en DESC", (estado,)
            ).fetchall()
        return con.execute("SELECT * FROM trabajos ORDER BY creado_en DESC").fetchall()
    finally:
        con.close()


def obtener_trabajo(trabajo_id: int) -> sqlite3.Row | None:
    con = conectar()
    con.row_factory = sqlite3.Row
    try:
        return con.execute("SELECT * FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# trabajos - transiciones disputadas por el panel (CAS: verifican el estado
# de origen esperado en el mismo UPDATE, nunca un UPDATE incondicional)
# ---------------------------------------------------------------------------

def aprobar_trabajo(trabajo_id: int) -> str:
    """Devuelve un codigo, no un bool, para que el panel pueda distinguir
    POR QUE fallo sin tener que volver a consultar la base (una segunda
    consulta no atomica podria ver un estado distinto al que realmente
    causo el fallo):
      "aprobado"            -> exito
      "estado_invalido"     -> el trabajo ya no estaba en listo_para_revision
      "escena_faltante"     -> falta una escena de Pista B por completo
      "qa_incompleto"       -> alguna escena tiene evaluacion vigente con qa_error o ausente
      "artefacto_invalido"  -> un archivo (Pista A o B) esta perdido o corrupto

    Exige unicamente que la evaluacion vigente de cada escena este COMPLETA
    (sin qa_error), NUNCA que haya dicho "aprobado". Un humano en el panel
    puede anular un fallo automatico de QA - ese es el sentido del panel.
    """
    con = conectar()
    con.execute("BEGIN IMMEDIATE")
    try:
        fila = con.execute("SELECT estado FROM trabajos WHERE id = ?", (trabajo_id,)).fetchone()
        if fila is None or fila[0] != "listo_para_revision":
            con.rollback()
            return "estado_invalido"

        # Pista A: los 3 formatos deben existir en disco y decodificar -
        # corrige hueco real: la reconciliacion de QA solo revisita
        # escenas de Pista B, un archivo de Pista A borrado/corrupto
        # despues de listo_para_revision nunca se detectaria si no se
        # revalida aqui.
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
                return "escena_faltante"
            generacion_id, ruta_output = generacion
            if not archivo_es_imagen_valida(ruta_output):
                con.rollback()
                return "artefacto_invalido"

            evaluacion = con.execute("""
                SELECT aprobado, qa_error FROM evaluaciones_qa
                WHERE generacion_id = ? AND version_prompt_qa = ?
                ORDER BY id DESC LIMIT 1
            """, (generacion_id, VERSION_QA)).fetchone()
            # Solo exige qa_error=0, NUNCA aprobado=1 - un humano en el
            # panel puede anular un fallo automatico de QA.
            if evaluacion is None or evaluacion[1] == 1:
                con.rollback()
                return "qa_incompleto"

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


def rechazar_trabajo(trabajo_id: int) -> bool:
    con = conectar()
    try:
        cur = con.execute(
            "UPDATE trabajos SET estado = 'rechazado', actualizado_en = ? WHERE id = ? AND estado = 'listo_para_revision'",
            (_ahora(), trabajo_id),
        )
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


# ---------------------------------------------------------------------------
# archivos_rechazados - dedup durable de rechazos de ingesta (sobrevive un
# fallo de red al mover el archivo en Drive, sin volver a descargar/
# re-validar el mismo archivo en cada ciclo de polling)
# ---------------------------------------------------------------------------

def existe_trabajo_drive_file_id(drive_file_id: str) -> bool:
    con = conectar()
    try:
        return con.execute(
            "SELECT 1 FROM trabajos WHERE drive_file_id = ?", (drive_file_id,)
        ).fetchone() is not None
    finally:
        con.close()


def existe_rechazo(drive_file_id: str) -> bool:
    con = conectar()
    try:
        return con.execute(
            "SELECT 1 FROM archivos_rechazados WHERE drive_file_id = ?", (drive_file_id,)
        ).fetchone() is not None
    finally:
        con.close()


def registrar_rechazo(drive_file_id: str, razon: str) -> None:
    """Se inserta (o actualiza) ANTES de intentar mover el archivo en Drive -
    asi el registro de "esto ya se evaluo y se rechazo" sobrevive aunque el
    movimiento mismo falle."""
    con = conectar()
    con.execute(
        """INSERT INTO archivos_rechazados (drive_file_id, razon, timestamp, movido)
           VALUES (?, ?, ?, 0)
           ON CONFLICT(drive_file_id) DO UPDATE SET razon = excluded.razon, timestamp = excluded.timestamp""",
        (drive_file_id, razon, _ahora()),
    )
    con.commit()
    con.close()


def archivos_rechazados_pendientes() -> list[str]:
    con = conectar()
    try:
        filas = con.execute(
            "SELECT drive_file_id FROM archivos_rechazados WHERE movido = 0"
        ).fetchall()
        return [fila[0] for fila in filas]
    finally:
        con.close()


def marcar_rechazo_movido(drive_file_id: str) -> None:
    con = conectar()
    con.execute(
        "UPDATE archivos_rechazados SET movido = 1 WHERE drive_file_id = ?", (drive_file_id,)
    )
    con.commit()
    con.close()


def reintentar_trabajo(trabajo_id: int) -> bool:
    """Transicion segura: los guards de idempotencia de Pista A/B y el lock
    de instancia unica del worker ya hacen que reprocesar un trabajo desde
    pendiente nunca rehaga ni cobre de mas nada que ya este completo. No
    resetea contadores de reintentos de QA agotados - para ese caso
    especifico, "Reintentar" no ayuda por diseno."""
    con = conectar()
    try:
        cur = con.execute(
            "UPDATE trabajos SET estado = 'pendiente', actualizado_en = ? WHERE id = ? AND estado = 'error'",
            (_ahora(), trabajo_id),
        )
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


if __name__ == "__main__":
    inicializar_db()
    print(f"Base de datos lista en {DB_PATH}")
