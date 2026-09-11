import io
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import db
import fase8_worker_ingesta as w


def _bytes_imagen_valida() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="JPEG")
    return buf.getvalue()


def test_destino_deseado():
    assert w._destino_deseado("listo_para_revision") == "procesados"
    assert w._destino_deseado("aprobado") == "procesados"
    assert w._destino_deseado("rechazado") == "rechazados"
    assert w._destino_deseado("pendiente") is None
    assert w._destino_deseado("procesando") is None
    assert w._destino_deseado("error") is None


def test_calcular_estado_final_error_si_todas_qa_error_o_ausentes(db_temporal, imagen_valida):
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))
    assert w._calcular_estado_final(tid) == "error"  # ninguna generacion todavia

    gid = db.registrar_generacion(sku="SKU1", escena_id="04", modelo_ia="nano_banana",
                                   prompt="p", seed="n/a", intento=1,
                                   ruta_output=str(imagen_valida("e04.jpg")), trabajo_id=tid)
    db.registrar_evaluacion_qa(gid, modelo_qa="m", version_prompt_qa=db.VERSION_QA, qa_error=True)
    assert w._calcular_estado_final(tid) == "error"


def test_calcular_estado_final_listo_si_al_menos_una_completa(db_temporal, imagen_valida):
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))
    gid1 = db.registrar_generacion(sku="SKU1", escena_id="04", modelo_ia="nano_banana",
                                    prompt="p", seed="n/a", intento=1,
                                    ruta_output=str(imagen_valida("e04.jpg")), trabajo_id=tid)
    gid2 = db.registrar_generacion(sku="SKU1", escena_id="09", modelo_ia="nano_banana",
                                    prompt="p", seed="n/a", intento=1,
                                    ruta_output=str(imagen_valida("e09.jpg")), trabajo_id=tid)
    db.registrar_evaluacion_qa(gid1, modelo_qa="m", version_prompt_qa=db.VERSION_QA, qa_error=True)
    db.registrar_evaluacion_qa(gid2, modelo_qa="m", version_prompt_qa=db.VERSION_QA,
                                score=40, aprobado=False, qa_error=False)
    # una completa (aunque no aprobada) basta para listo_para_revision
    assert w._calcular_estado_final(tid) == "listo_para_revision"


def test_pista_a_no_regenera_formato_ya_valido(db_temporal, imagen_valida, tmp_path):
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))
    # la ruta exacta no importa para este guard - solo que la fila exista
    # y el archivo decodifique como imagen valida.
    ruta_4x5 = imagen_valida("pista_a/SKU1_producto_4x5.jpg")
    db.registrar_generacion(sku="SKU1", escena_id="4x5", modelo_ia="compositing_local",
                             prompt="n/a", seed="n/a", intento=1, ruta_output=str(ruta_4x5),
                             trabajo_id=tid)

    with patch("fase8_worker_ingesta.generar_imagen_producto") as mock_generar:
        w._procesar_pista_a(tid, "SKU1", Path("f.jpg"))
        # solo debe pedir los 2 formatos faltantes (1x1, 9x16), nunca 4x5
        assert mock_generar.called
        _, kwargs = mock_generar.call_args
        formatos_pedidos = mock_generar.call_args.kwargs.get("formatos") or mock_generar.call_args.args[-1]
        assert "4x5" not in formatos_pedidos
        assert set(formatos_pedidos) == {"1x1", "9x16"}


def test_pista_a_regenera_formato_corrupto_sin_insertar_fila_nueva(db_temporal, imagen_valida, tmp_path):
    """Los 3 formatos ya tienen fila registrada (a diferencia de la prueba
    de reanudacion de arriba, donde 2 de 3 nunca se generaron) - solo uno
    de los 3 archivos esta corrupto. Debe regenerarse SOLO ese archivo, sin
    insertar ni actualizar ninguna fila."""
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))
    ruta_corrupta = tmp_path / "corrupto_4x5.jpg"
    ruta_corrupta.write_bytes(b"no es imagen")
    db.registrar_generacion(sku="SKU1", escena_id="4x5", modelo_ia="compositing_local",
                             prompt="n/a", seed="n/a", intento=1, ruta_output=str(ruta_corrupta),
                             trabajo_id=tid)
    for fmt in ("1x1", "9x16"):
        db.registrar_generacion(sku="SKU1", escena_id=fmt, modelo_ia="compositing_local",
                                 prompt="n/a", seed="n/a", intento=1,
                                 ruta_output=str(imagen_valida(f"{fmt}.jpg")), trabajo_id=tid)

    def fake_generar(foto_gorra, sku, output_dir, formatos=None):
        assert formatos == ["4x5"]  # nunca regenera un formato ya valido
        return {f: ruta_corrupta for f in formatos}

    with patch("fase8_worker_ingesta.generar_imagen_producto", side_effect=fake_generar):
        w._procesar_pista_a(tid, "SKU1", Path("f.jpg"))

    filas = db.generaciones_pista_a(tid)
    assert len(filas) == 3  # nunca se inserta una fila nueva para un formato que ya tenia una


def test_pista_a_no_hace_nada_si_los_3_formatos_ya_son_validos(db_temporal, imagen_valida):
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))
    for fmt in ("4x5", "1x1", "9x16"):
        db.registrar_generacion(sku="SKU1", escena_id=fmt, modelo_ia="compositing_local",
                                 prompt="n/a", seed="n/a", intento=1,
                                 ruta_output=str(imagen_valida(f"{fmt}.jpg")), trabajo_id=tid)
    with patch("fase8_worker_ingesta.generar_imagen_producto") as mock_generar:
        w._procesar_pista_a(tid, "SKU1", Path("f.jpg"))
        mock_generar.assert_not_called()


def test_reconciliar_movimiento_drive_no_mueve_si_cache_ya_coincide(db_temporal, imagen_valida):
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))
    db.actualizar_estado_trabajo(tid, "listo_para_revision")
    db.actualizar_drive_carpeta_observada(tid, "procesados")

    with patch("fase8_worker_ingesta.drive.ubicacion_actual") as mock_ubicacion, \
         patch("fase8_worker_ingesta.drive.mover_a") as mock_mover:
        w.reconciliar_movimiento_drive()
        mock_ubicacion.assert_not_called()  # la cache ya coincide, ni siquiera se verifica
        mock_mover.assert_not_called()


def test_reconciliar_movimiento_drive_relocaliza_tras_rechazo(db_temporal, imagen_valida):
    """El caso central: un trabajo ya archivado en 'procesados' que un
    humano rechaza despues debe terminar en 'rechazados', no quedarse
    archivado para siempre en el lugar viejo."""
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))
    db.actualizar_estado_trabajo(tid, "listo_para_revision")
    db.actualizar_drive_carpeta_observada(tid, "procesados")
    assert db.rechazar_trabajo(tid) is True

    with patch("fase8_worker_ingesta.drive.ubicacion_actual", return_value="procesados"), \
         patch("fase8_worker_ingesta.drive.mover_a") as mock_mover:
        w.reconciliar_movimiento_drive()
        mock_mover.assert_called_once_with("d1", "rechazados")

    assert db.obtener_trabajo(tid)["drive_carpeta"] == "rechazados"


def test_reconciliar_movimiento_drive_autocura_tras_crash_antes_del_update(db_temporal, imagen_valida):
    """Simula: el movimiento remoto tuvo exito pero el proceso murio antes
    de persistir drive_carpeta - la cache sigue diciendo NULL aunque el
    archivo ya este fisicamente en 'procesados'. La reconciliacion debe
    darse cuenta sin volver a mover nada."""
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))
    db.actualizar_estado_trabajo(tid, "listo_para_revision")
    # drive_carpeta sigue NULL a proposito

    with patch("fase8_worker_ingesta.drive.ubicacion_actual", return_value="procesados"), \
         patch("fase8_worker_ingesta.drive.mover_a") as mock_mover:
        w.reconciliar_movimiento_drive()
        mock_mover.assert_not_called()  # ya estaba donde debia, no se repite el movimiento

    assert db.obtener_trabajo(tid)["drive_carpeta"] == "procesados"  # la cache se corrigio


def test_reconciliar_movimiento_drive_excluye_error_y_pendiente(db_temporal, imagen_valida):
    tid_error = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f1.jpg")))
    db.actualizar_estado_trabajo(tid_error, "error")
    tid_pendiente = db.crear_trabajo("d2", "f.jpg", "SKU2", str(imagen_valida("f2.jpg")))

    with patch("fase8_worker_ingesta.drive.ubicacion_actual") as mock_ubicacion:
        w.reconciliar_movimiento_drive()
        mock_ubicacion.assert_not_called()


def test_reconciliar_qa_incompleta_excluye_rechazado_y_aprobado(db_temporal, imagen_valida):
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))
    gid = db.registrar_generacion(sku="SKU1", escena_id="04", modelo_ia="nano_banana",
                                   prompt="p", seed="n/a", intento=1,
                                   ruta_output=str(imagen_valida("e04.jpg")), trabajo_id=tid)
    db.actualizar_estado_trabajo(tid, "rechazado")

    with patch("fase8_worker_ingesta.evaluar_calidad") as mock_qa:
        w.reconciliar_qa_incompleta()
        mock_qa.assert_not_called()


def test_pista_b_reintenta_automaticamente_dentro_del_mismo_procesamiento(db_temporal, imagen_valida, monkeypatch):
    """Regresion real (encontrada procesando los primeros 10 trabajos
    reales del negocio): un trabajo nuevo solo pasa por procesar_trabajo()
    UNA vez (pasa de pendiente a listo_para_revision/error en esa misma
    llamada, nunca vuelve a pendiente solo) - sin un bucle dentro de
    _procesar_pista_b, una escena que fallaba en su primer intento se
    quedaba asi para siempre, sin la segunda oportunidad que MAX_INTENTOS=2
    promete. El fix llama a _procesar_escena_pista_b hasta MAX_INTENTOS
    veces por escena dentro de la misma pasada - la funcion ya es
    idempotente (no hace nada si la escena ya esta aprobada), asi que esto
    implementa el reintento real sin duplicar logica."""
    monkeypatch.setattr(w, "ESCENAS_PRODUCCION", ["04"])
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))

    llamadas_generacion = {"n": 0}

    def fake_run(modelo, arguments):
        llamadas_generacion["n"] += 1
        return {"images": [{"url": "http://fake/img.jpg"}]}

    resultados_qa = [
        {"score": 50, "aprobado": False, "qa_error": False, "problema": "no aprobado"},
        {"score": 100, "aprobado": True, "qa_error": False, "problema": ""},
    ]

    def fake_evaluar_calidad(ruta_producto, ruta_escena, ruta_generada, generacion_id=None, **kwargs):
        # replica el efecto real de evaluar_calidad(): persiste en
        # evaluaciones_qa, no solo devuelve un valor - si no, la siguiente
        # vuelta del bucle no encuentra ninguna evaluacion registrada y el
        # guard toma la rama equivocada ("aun no evaluado", no "no aprobado").
        resultado = resultados_qa.pop(0)
        db.registrar_evaluacion_qa(generacion_id, modelo_qa="m", version_prompt_qa=db.VERSION_QA,
                                    score=resultado["score"], aprobado=resultado["aprobado"], qa_error=False)
        return resultado

    class FakeResp:
        content = _bytes_imagen_valida()

    with patch("fase8_worker_ingesta.fal_client.upload_file", return_value="url://x"), \
         patch("fase8_worker_ingesta.fal_client.run", side_effect=fake_run), \
         patch("fase8_worker_ingesta.requests.get", return_value=FakeResp()), \
         patch("fase8_worker_ingesta._ruta_escena", return_value=imagen_valida("escena04.jpg")), \
         patch("fase8_worker_ingesta.evaluar_calidad", side_effect=fake_evaluar_calidad):
        w._procesar_pista_b(tid, "SKU1", imagen_valida("foto.jpg"))

    assert llamadas_generacion["n"] == 2  # intento 1 (no aprobado) + intento 2 (aprobado), en una sola pasada
    filas_b = [f for f in db.generaciones_de_trabajo(tid) if f["modelo_ia"] == "nano_banana"]
    assert len(filas_b) == 2
    assert filas_b[-1]["intento"] == 2


def test_pista_b_no_excede_max_intentos_aunque_nunca_apruebe(db_temporal, imagen_valida, monkeypatch):
    monkeypatch.setattr(w, "ESCENAS_PRODUCCION", ["04"])
    tid = db.crear_trabajo("d1", "f.jpg", "SKU1", str(imagen_valida("f.jpg")))

    llamadas_generacion = {"n": 0}

    def fake_run(modelo, arguments):
        llamadas_generacion["n"] += 1
        return {"images": [{"url": "http://fake/img.jpg"}]}

    class FakeResp:
        content = _bytes_imagen_valida()

    def fake_evaluar_calidad_nunca_aprueba(ruta_producto, ruta_escena, ruta_generada, generacion_id=None, **kwargs):
        db.registrar_evaluacion_qa(generacion_id, modelo_qa="m", version_prompt_qa=db.VERSION_QA,
                                    score=50, aprobado=False, qa_error=False)
        return {"score": 50, "aprobado": False, "qa_error": False, "problema": "nunca aprueba"}

    with patch("fase8_worker_ingesta.fal_client.upload_file", return_value="url://x"), \
         patch("fase8_worker_ingesta.fal_client.run", side_effect=fake_run), \
         patch("fase8_worker_ingesta.requests.get", return_value=FakeResp()), \
         patch("fase8_worker_ingesta._ruta_escena", return_value=imagen_valida("escena04.jpg")), \
         patch("fase8_worker_ingesta.evaluar_calidad", side_effect=fake_evaluar_calidad_nunca_aprueba):
        w._procesar_pista_b(tid, "SKU1", imagen_valida("foto.jpg"))

    assert llamadas_generacion["n"] == w.MAX_INTENTOS
    filas_b = [f for f in db.generaciones_de_trabajo(tid) if f["modelo_ia"] == "nano_banana"]
    assert len(filas_b) == w.MAX_INTENTOS
