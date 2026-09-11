import sqlite3

import db


def test_inicializar_db_es_idempotente(db_temporal):
    db.inicializar_db()
    db.inicializar_db()
    con = db.conectar()
    columnas_generaciones = {f[1] for f in con.execute("PRAGMA table_info(generaciones)")}
    columnas_trabajos = {f[1] for f in con.execute("PRAGMA table_info(trabajos)")}
    con.close()
    assert "trabajo_id" in columnas_generaciones
    assert "drive_carpeta" in columnas_trabajos


def test_migracion_desde_esquema_real_preexistente(db_path_temporal):
    """Simula la base real antes de este plan: sin trabajo_id, sin
    drive_carpeta, sin el indice unico - inicializar_db() debe migrarla sin
    lanzar OperationalError, no solo crear una base nueva desde cero."""
    con = sqlite3.connect(db_path_temporal)
    con.executescript("""
        CREATE TABLE trabajos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL,
            drive_file_id TEXT NOT NULL UNIQUE,
            drive_file_name TEXT NOT NULL,
            sku TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            ruta_local_foto TEXT,
            error TEXT
        );
        CREATE TABLE generaciones (
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
            ruta_output TEXT
        );
    """)
    con.commit()
    con.close()

    db.inicializar_db()  # no debe lanzar

    con = db.conectar()
    columnas = {f[1] for f in con.execute("PRAGMA table_info(generaciones)")}
    indices = {f[1] for f in con.execute("PRAGMA index_list(generaciones)")}
    con.close()
    assert "trabajo_id" in columnas
    assert "uq_generaciones_intento" in indices


def test_archivo_es_imagen_valida(db_temporal, imagen_valida, tmp_path):
    ruta = imagen_valida("ok.jpg")
    assert db.archivo_es_imagen_valida(ruta) is True
    assert db.archivo_es_imagen_valida(tmp_path / "no_existe.jpg") is False

    corrupto = tmp_path / "corrupto.jpg"
    corrupto.write_bytes(b"no es una imagen")
    assert db.archivo_es_imagen_valida(corrupto) is False


def test_registrar_generacion_devuelve_id_usable_antes_de_qa(db_temporal):
    gid = db.registrar_generacion(
        sku="SKU1", escena_id="04", modelo_ia="nano_banana", prompt="p", seed="n/a",
        intento=1, ruta_output="x.jpg", costo_usd=0.06,
    )
    assert isinstance(gid, int)
    assert db.ultima_evaluacion_vigente(gid) is None


def test_ultima_evaluacion_vigente_usa_id_desc(db_temporal):
    gid = db.registrar_generacion(
        sku="SKU1", escena_id="04", modelo_ia="nano_banana", prompt="p", seed="n/a",
        intento=1, ruta_output="x.jpg",
    )
    db.registrar_evaluacion_qa(gid, modelo_qa="m", version_prompt_qa="v1", score=50, aprobado=False, qa_error=False)
    db.registrar_evaluacion_qa(gid, modelo_qa="m", version_prompt_qa="v1", score=90, aprobado=True, qa_error=False)
    vigente = db.ultima_evaluacion_vigente(gid, "v1")
    assert vigente["score"] == 90


def test_qa_agotado_requiere_ultima_vigente_qa_error(db_temporal):
    gid = db.registrar_generacion(
        sku="SKU1", escena_id="04", modelo_ia="nano_banana", prompt="p", seed="n/a",
        intento=1, ruta_output="x.jpg",
    )
    for _ in range(5):
        db.registrar_evaluacion_qa(gid, modelo_qa="m", version_prompt_qa="v1", qa_error=True)
    assert db.qa_agotado(gid, "v1") is False  # solo 5 filas, limite es 6

    db.registrar_evaluacion_qa(gid, modelo_qa="m", version_prompt_qa="v1", score=90, aprobado=True, qa_error=False)
    assert db.qa_agotado(gid, "v1") is False  # 6 filas pero la mas reciente NO es qa_error

    db.registrar_evaluacion_qa(gid, modelo_qa="m", version_prompt_qa="v1", qa_error=True)
    assert db.qa_agotado(gid, "v1") is True  # 7 filas, la mas reciente SI es qa_error


def _crear_trabajo_completo(db_temporal, imagen_valida, aprobado_por_qa=True):
    """Helper: crea un trabajo con Pista A completa y las 3 escenas de
    produccion con evaluacion vigente completa."""
    tid = db.crear_trabajo("d1", "foto.jpg", "SKU1", str(imagen_valida("foto.jpg")))
    for fmt in ("4x5", "1x1", "9x16"):
        db.registrar_generacion(
            sku="SKU1", escena_id=fmt, modelo_ia="compositing_local", prompt="n/a", seed="n/a",
            intento=1, ruta_output=str(imagen_valida(f"pista_a_{fmt}.jpg")), trabajo_id=tid,
        )
    from prompts import ESCENAS_PRODUCCION, VERSION_QA
    for escena in ESCENAS_PRODUCCION:
        gid = db.registrar_generacion(
            sku="SKU1", escena_id=escena, modelo_ia="nano_banana", prompt="p", seed="n/a",
            intento=1, ruta_output=str(imagen_valida(f"pista_b_{escena}.jpg")), trabajo_id=tid,
        )
        db.registrar_evaluacion_qa(
            gid, modelo_qa="m", version_prompt_qa=VERSION_QA,
            score=90 if aprobado_por_qa else 50, aprobado=aprobado_por_qa, qa_error=False,
        )
    db.actualizar_estado_trabajo(tid, "listo_para_revision")
    return tid


def test_aprobar_trabajo_exito(db_temporal, imagen_valida):
    tid = _crear_trabajo_completo(db_temporal, imagen_valida)
    assert db.aprobar_trabajo(tid) == "aprobado"
    assert db.obtener_trabajo(tid)["estado"] == "aprobado"


def test_aprobar_trabajo_permite_override_humano_de_qa_fallido(db_temporal, imagen_valida):
    """El punto central del panel: QA que dijo 'no aprobado' en las 3
    escenas NO bloquea a un humano que decide aprobar - solo qa_error o una
    evaluacion ausente deberian bloquear."""
    tid = _crear_trabajo_completo(db_temporal, imagen_valida, aprobado_por_qa=False)
    assert db.aprobar_trabajo(tid) == "aprobado"


def test_aprobar_trabajo_escena_faltante(db_temporal, imagen_valida):
    tid = db.crear_trabajo("d1", "foto.jpg", "SKU1", str(imagen_valida("foto.jpg")))
    for fmt in ("4x5", "1x1", "9x16"):
        db.registrar_generacion(
            sku="SKU1", escena_id=fmt, modelo_ia="compositing_local", prompt="n/a", seed="n/a",
            intento=1, ruta_output=str(imagen_valida(f"pista_a_{fmt}.jpg")), trabajo_id=tid,
        )
    db.actualizar_estado_trabajo(tid, "listo_para_revision")
    assert db.aprobar_trabajo(tid) == "escena_faltante"


def test_aprobar_trabajo_qa_incompleto_por_qa_error(db_temporal, imagen_valida):
    tid = _crear_trabajo_completo(db_temporal, imagen_valida)
    from prompts import ESCENAS_PRODUCCION, VERSION_QA
    reciente = db.generacion_mas_reciente(tid, "nano_banana", ESCENAS_PRODUCCION[0])
    db.registrar_evaluacion_qa(reciente["id"], modelo_qa="m", version_prompt_qa=VERSION_QA, qa_error=True)
    assert db.aprobar_trabajo(tid) == "qa_incompleto"


def test_aprobar_trabajo_artefacto_invalido_pista_a(db_temporal, imagen_valida, tmp_path):
    tid = _crear_trabajo_completo(db_temporal, imagen_valida)
    # corromper un formato de Pista A despues de listo_para_revision
    con = db.conectar()
    fila = con.execute(
        "SELECT id, ruta_output FROM generaciones WHERE trabajo_id = ? AND modelo_ia = 'compositing_local' LIMIT 1",
        (tid,),
    ).fetchone()
    con.close()
    ruta = fila[1]
    from pathlib import Path
    Path(ruta).write_bytes(b"corrupto")
    assert db.aprobar_trabajo(tid) == "artefacto_invalido"


def test_aprobar_trabajo_estado_invalido_si_no_esta_listo(db_temporal, imagen_valida):
    tid = db.crear_trabajo("d1", "foto.jpg", "SKU1", str(imagen_valida("foto.jpg")))
    assert db.aprobar_trabajo(tid) == "estado_invalido"


def test_rechazar_y_reintentar_son_cas(db_temporal, imagen_valida):
    tid = db.crear_trabajo("d1", "foto.jpg", "SKU1", str(imagen_valida("foto.jpg")))

    # rechazar solo funciona desde listo_para_revision
    assert db.rechazar_trabajo(tid) is False
    db.actualizar_estado_trabajo(tid, "listo_para_revision")
    assert db.rechazar_trabajo(tid) is True
    assert db.obtener_trabajo(tid)["estado"] == "rechazado"
    # una segunda vez ya no aplica (ya no esta en listo_para_revision)
    assert db.rechazar_trabajo(tid) is False

    # reintentar solo funciona desde error
    assert db.reintentar_trabajo(tid) is False
    db.actualizar_estado_trabajo(tid, "error")
    assert db.reintentar_trabajo(tid) is True
    assert db.obtener_trabajo(tid)["estado"] == "pendiente"


def test_dos_transiciones_compitiendo_solo_una_aplica(db_temporal, imagen_valida):
    tid = _crear_trabajo_completo(db_temporal, imagen_valida)
    resultado_aprobar = db.aprobar_trabajo(tid)
    resultado_rechazar = db.rechazar_trabajo(tid)
    # exactamente una de las dos transiciones aplico
    assert (resultado_aprobar == "aprobado") != resultado_rechazar
    assert db.obtener_trabajo(tid)["estado"] in ("aprobado", "rechazado")


def test_crear_trabajo_duplicado_devuelve_none(db_temporal, imagen_valida):
    ruta = str(imagen_valida("foto.jpg"))
    assert db.crear_trabajo("d1", "foto.jpg", "SKU1", ruta) is not None
    assert db.crear_trabajo("d1", "foto.jpg", "SKU1", ruta) is None


def test_generaciones_de_trabajo_aisla_por_trabajo_no_por_sku(db_temporal, imagen_valida):
    t1 = db.crear_trabajo("d1", "a.jpg", "SKU-COMPARTIDO", str(imagen_valida("a.jpg")))
    t2 = db.crear_trabajo("d2", "b.jpg", "SKU-COMPARTIDO", str(imagen_valida("b.jpg")))
    db.registrar_generacion(sku="SKU-COMPARTIDO", escena_id="4x5", modelo_ia="compositing_local",
                             prompt="n/a", seed="n/a", intento=1, ruta_output="x1.jpg", trabajo_id=t1)
    db.registrar_generacion(sku="SKU-COMPARTIDO", escena_id="4x5", modelo_ia="compositing_local",
                             prompt="n/a", seed="n/a", intento=1, ruta_output="x2.jpg", trabajo_id=t2)
    assert len(db.generaciones_de_trabajo(t1)) == 1
    assert len(db.generaciones_de_trabajo(t2)) == 1


def test_archivos_rechazados_dedup(db_temporal):
    assert db.existe_rechazo("f1") is False
    db.registrar_rechazo("f1", razon="tamano excedido")
    assert db.existe_rechazo("f1") is True
    assert db.archivos_rechazados_pendientes() == ["f1"]
    db.marcar_rechazo_movido("f1")
    assert db.archivos_rechazados_pendientes() == []
    # registrar de nuevo sobre el mismo id actualiza en vez de duplicar
    db.registrar_rechazo("f1", razon="otra razon")
    con = db.conectar()
    total = con.execute("SELECT COUNT(*) FROM archivos_rechazados").fetchone()[0]
    con.close()
    assert total == 1
