"""
Fase 8 - Worker de ingesta: Drive (polling) -> cola de trabajos -> generacion.
Revisa la carpeta de Drive cada INTERVALO_SEGUNDOS, encola archivos nuevos que
no se hayan visto antes (por drive_file_id), procesa los pendientes (Pista A
+ Pista B con reintento dirigido + QA sobre un set fijo de escenas), y
reconcilia en cada ciclo: QA incompleta, movimiento a Drive, y rechazos
pendientes de archivar - para que un fallo transitorio en cualquiera de esos
pasos nunca deje un trabajo atascado permanentemente.

Instancia unica: usa un lock real de sistema operativo (filelock), no un
archivo marcador - se libera solo si el proceso muere por cualquier causa.
"""
import json
import os
import sys
import time
from pathlib import Path

import fal_client
import requests
from dotenv import load_dotenv
from filelock import FileLock, Timeout
from PIL import Image

import db
import fase8_drive_cliente as drive
from fase5_pista_a_produccion import FORMATOS, generar_imagen_producto
from fase6_qa_reintento import construir_prompt_reintento, evaluar_calidad
from fase8_drive_cliente import ArchivoRechazado, derivar_sku_o_generar, descargar_archivo, listar_archivos_nuevos
from prompts import ESCENAS_PRODUCCION, PROMPT_V3
from seguridad import sanitizar

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

INTERVALO_SEGUNDOS = 60
SKUS_PENDIENTES_DIR = ROOT / "assets" / "skus_pendientes"
OUTPUT_DIR = ROOT / "output" / "fase8"
ESCENAS_DIR = ROOT / "assets" / "escenas_base_mejoradas"

MAX_INTENTOS = 2
LIMITE_MEGAPIXELES = 100  # rechazo barato de imagenes con metadata de dimensiones disparatada

# Sobreescribible por variable de entorno, mismo patron que db.DB_PATH -
# necesario para poder probar el lock sin depender de la ruta real de
# produccion (ver tests/_ayudante_lock.py).
LOCK_PATH = Path(os.environ.get(
    "GORROLANDIA_LOCK_PATH", str(ROOT / "output" / "fase8" / "worker.lock")
))


def adquirir_lock_worker() -> FileLock:
    """Lock real de sistema operativo (msvcrt en Windows, fcntl.flock en
    POSIX por debajo de filelock) - a diferencia de un archivo marcador con
    O_CREAT|O_EXCL, el sistema operativo lo libera solo si el proceso muere
    por cualquier causa (corte de luz, kill -9), nunca queda trabado."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(LOCK_PATH), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        sys.exit("Ya hay un worker corriendo (lock activo) - no se inicia una segunda instancia.")
    return lock


def _ruta_escena(numero: str) -> Path:
    return next(ESCENAS_DIR.glob(f"{numero}_lanczos_*.png"))


def _destino_deseado(estado: str) -> str | None:
    if estado in ("listo_para_revision", "aprobado"):
        return "procesados"
    if estado == "rechazado":
        return "rechazados"
    return None


def _fila_evaluacion_a_dict(fila: "db.sqlite3.Row") -> dict:
    """Reconstruye el dict de items (para construir_prompt_reintento) a
    partir de una fila de evaluaciones_qa ya guardada."""
    if fila["qa_error"]:
        return {"qa_error": True, "detalle": fila["detalle"]}
    try:
        return json.loads(fila["resultado_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"qa_error": True, "detalle": "no se pudo reconstruir el resultado QA anterior"}


# ---------------------------------------------------------------------------
# Ingesta
# ---------------------------------------------------------------------------

def encolar_archivos_nuevos() -> int:
    archivos = listar_archivos_nuevos()
    nuevos = 0
    for archivo in archivos:
        file_id = archivo["id"]
        if db.existe_trabajo_drive_file_id(file_id) or db.existe_rechazo(file_id):
            continue

        try:
            tamano = int(archivo.get("size") or 0)
            if tamano > drive.LIMITE_BYTES_ENTRADA:
                raise ArchivoRechazado(f"tamano reportado ({tamano} bytes) excede el limite de entrada")

            # nunca rechaza solo por el nombre - si no produce un SKU real
            # (caso comun: fotos reenviadas por WhatsApp sin codigo de
            # producto en el nombre), genera un identificador interno a
            # partir del drive_file_id en vez de descartar la foto.
            sku, sku_generado = derivar_sku_o_generar(archivo["name"], file_id)
            destino = descargar_archivo(file_id, archivo["name"], SKUS_PENDIENTES_DIR)

            if not db.archivo_es_imagen_valida(destino):
                raise ArchivoRechazado("el archivo descargado no decodifica como imagen valida")
            with Image.open(destino) as img:
                ancho, alto = img.size
            if ancho * alto > LIMITE_MEGAPIXELES * 1_000_000:
                raise ArchivoRechazado(f"dimensiones sospechosas: {ancho}x{alto}")

        except ArchivoRechazado as exc:
            razon = sanitizar(str(exc))
            db.registrar_rechazo(file_id, razon=razon)
            try:
                drive.marcar_como_rechazado(file_id)
                db.marcar_rechazo_movido(file_id)
            except Exception as exc2:
                print(f"[ingesta] {archivo['name']}: rechazado ({razon}), pero fallo "
                      f"moviendolo en Drive (se reintentara en la reconciliacion): {sanitizar(exc2)}")
            print(f"[ingesta] Rechazado: {archivo['name']} ({razon})")
            continue

        trabajo_id = db.crear_trabajo(
            drive_file_id=file_id, drive_file_name=archivo["name"],
            sku=sku, ruta_local_foto=str(destino),
        )
        if trabajo_id:
            nuevos += 1
            aviso_generado = " (sku generado automaticamente, no es un codigo de producto real)" if sku_generado else ""
            print(f"[ingesta] Nuevo: {archivo['name']} -> trabajo #{trabajo_id} (sku={sku}){aviso_generado}")
    return nuevos


# ---------------------------------------------------------------------------
# Pista A - por formato individual, solo se regeneran los formatos que faltan
# ---------------------------------------------------------------------------

def _procesar_pista_a(trabajo_id: int, sku: str, foto_gorra: Path) -> None:
    dir_salida = OUTPUT_DIR / "trabajos" / str(trabajo_id) / "pista_a" / sku
    # el formato (4x5/1x1/9x16) se guarda en la columna escena_id de las
    # filas de Pista A, en vez de "n/a" - es lo que permite consultar "ya
    # existe una fila para este formato" sin agregar una columna nueva.
    existentes = {fila["escena_id"]: fila for fila in db.generaciones_pista_a(trabajo_id)}

    formatos_a_generar = []
    for formato in FORMATOS:
        fila = existentes.get(formato)
        if fila is None:
            formatos_a_generar.append(formato)
        elif not db.archivo_es_imagen_valida(fila["ruta_output"]):
            # fila presente, archivo faltante o corrupto: la ruta de salida
            # de Pista A es deterministica por (trabajo_id, formato), asi
            # que regenerar el archivo en el mismo ruta_output ya
            # registrado resuelve el problema sin tocar la fila de la base
            # en absoluto - no hace falta insertar ni actualizar.
            formatos_a_generar.append(formato)
        # fila presente + archivo valido -> no tocar nada

    if not formatos_a_generar:
        return

    salidas = generar_imagen_producto(foto_gorra, sku, dir_salida, formatos=formatos_a_generar)

    for formato in formatos_a_generar:
        if existentes.get(formato) is None:
            db.registrar_generacion(
                sku=sku, escena_id=formato, modelo_ia="compositing_local",
                prompt="n/a", seed="n/a", intento=1, ruta_output=str(salidas[formato]),
                costo_usd=0.0, trabajo_id=trabajo_id,
            )
        # si la fila ya existia (caso "archivo corrupto"), el archivo ya se
        # regenero en el mismo ruta_output - nada mas que hacer.


# ---------------------------------------------------------------------------
# Pista B - por escena, con reanudacion por intento absoluto
# ---------------------------------------------------------------------------

def _procesar_pista_b(trabajo_id: int, sku: str, foto_gorra: Path) -> None:
    dir_salida = OUTPUT_DIR / "trabajos" / str(trabajo_id) / "pista_b" / sku
    dir_salida.mkdir(parents=True, exist_ok=True)

    urls_cache: dict[str, str] = {}

    def url_gorra() -> str:
        if "gorra" not in urls_cache:
            urls_cache["gorra"] = fal_client.upload_file(str(foto_gorra))
        return urls_cache["gorra"]

    def url_escena(escena_num: str) -> str:
        if escena_num not in urls_cache:
            urls_cache[escena_num] = fal_client.upload_file(str(_ruta_escena(escena_num)))
        return urls_cache[escena_num]

    for escena_num in ESCENAS_PRODUCCION:
        # Corrige bug real: procesar_trabajo() solo se llama UNA vez por
        # trabajo nuevo (pasa de pendiente a listo_para_revision/error en
        # la misma llamada, nunca vuelve a pendiente solo) - sin este
        # bucle, cada escena solo recibia un intento real durante el
        # procesamiento normal, y MAX_INTENTOS=2 nunca se ejercia salvo
        # que el trabajo se reiniciara por un crash o un "Reintentar"
        # manual. _procesar_escena_pista_b() ya es idempotente (no hace
        # nada si la escena ya esta aprobada o agotada), asi que llamarla
        # hasta MAX_INTENTOS veces seguidas aqui mismo implementa el
        # reintento real sin duplicar la logica de reanudacion.
        for _ in range(MAX_INTENTOS):
            _procesar_escena_pista_b(trabajo_id, sku, foto_gorra, escena_num, dir_salida, url_gorra, url_escena)


def _procesar_escena_pista_b(trabajo_id, sku, foto_gorra, escena_num, dir_salida, url_gorra, url_escena) -> None:
    reciente = db.generacion_mas_reciente(trabajo_id, "nano_banana", escena_num)

    if reciente is None:
        intento_a_generar = 1
        qa_previo = None
    else:
        archivo_valido = db.archivo_es_imagen_valida(reciente["ruta_output"])

        if not archivo_valido:
            # archivo perdido/corrupto del intento mas reciente - nunca se
            # manda a QA algo que no existe.
            if reciente["intento"] >= MAX_INTENTOS:
                print(f"  escena {escena_num}: archivo perdido en el intento limite - requiere revision manual")
                return
            intento_a_generar = reciente["intento"] + 1
            qa_previo = None
        else:
            evaluacion = db.ultima_evaluacion_vigente(reciente["id"])
            if evaluacion is not None and evaluacion["qa_error"] == 0 and evaluacion["aprobado"] == 1:
                return  # completo y aprobado, nada que hacer
            if evaluacion is None or evaluacion["qa_error"] == 1:
                # imagen valida pero evaluacion vigente ausente o qa_error:
                # no se genera una imagen nueva, se reintenta solo QA sobre
                # la misma imagen - esto no consume un numero de intento nuevo.
                if db.qa_agotado(reciente["id"]):
                    print(f"  escena {escena_num}: QA agotado tras {db.LIMITE_INTENTOS_QA_POR_VERSION} intentos - requiere revision manual")
                    return
                qa = evaluar_calidad(foto_gorra, _ruta_escena(escena_num), Path(reciente["ruta_output"]),
                                      generacion_id=reciente["id"])
                estado_txt = "qa_error" if qa.get("qa_error") else f"score={qa['score']}"
                print(f"  escena {escena_num} (solo QA, intento {reciente['intento']}): {estado_txt}")
                return
            # evaluacion vigente completa con aprobado=0: fallo real de
            # producto, no de QA - continuar desde el siguiente intento.
            if reciente["intento"] >= MAX_INTENTOS:
                print(f"  escena {escena_num}: agotada tras {MAX_INTENTOS} intentos sin aprobar - requiere revision manual")
                return
            intento_a_generar = reciente["intento"] + 1
            qa_previo = evaluacion

    prompt = PROMPT_V3
    if qa_previo is not None:
        prompt = construir_prompt_reintento(PROMPT_V3, _fila_evaluacion_a_dict(qa_previo))

    resultado = fal_client.run(
        "fal-ai/nano-banana/edit",
        arguments={
            "prompt": prompt,
            "image_urls": [url_escena(escena_num), url_gorra()],
            "num_images": 1,
        },
    )
    url_img = resultado["images"][0]["url"]
    resp = requests.get(url_img, timeout=90)
    ruta_salida = dir_salida / f"escena{escena_num}_intento{intento_a_generar}.jpg"
    ruta_salida.write_bytes(resp.content)

    generacion_id = db.registrar_generacion(
        sku=sku, escena_id=escena_num, modelo_ia="nano_banana", prompt=prompt, seed="n/a",
        intento=intento_a_generar, ruta_output=str(ruta_salida), costo_usd=0.06, trabajo_id=trabajo_id,
    )
    qa = evaluar_calidad(foto_gorra, _ruta_escena(escena_num), ruta_salida, generacion_id=generacion_id)
    estado_txt = "qa_error" if qa.get("qa_error") else f"score={qa['score']} aprobado={qa['aprobado']}"
    print(f"  escena {escena_num} intento {intento_a_generar}: {estado_txt}")


def _calcular_estado_final(trabajo_id: int) -> str:
    """Regla unica de estado: listo_para_revision si al menos una escena de
    Pista B tiene evaluacion vigente completa; error solo si TODAS son
    qa_error (o nunca se generaron)."""
    for escena in ESCENAS_PRODUCCION:
        reciente = db.generacion_mas_reciente(trabajo_id, "nano_banana", escena)
        if reciente is None:
            continue
        evaluacion = db.ultima_evaluacion_vigente(reciente["id"])
        if evaluacion is not None and evaluacion["qa_error"] == 0:
            return "listo_para_revision"
    return "error"


def procesar_trabajo(trabajo: "db.sqlite3.Row") -> None:
    trabajo_id = trabajo["id"]
    sku = trabajo["sku"]
    foto_gorra = Path(trabajo["ruta_local_foto"])

    print(f"[procesar] trabajo #{trabajo_id} ({sku})...")
    db.actualizar_estado_trabajo(trabajo_id, "procesando")

    try:
        _procesar_pista_a(trabajo_id, sku, foto_gorra)
        _procesar_pista_b(trabajo_id, sku, foto_gorra)
        estado_final = _calcular_estado_final(trabajo_id)
        db.actualizar_estado_trabajo(trabajo_id, estado_final)
        print(f"[procesar] trabajo #{trabajo_id} -> {estado_final}")
        # El movimiento a Drive NO se intenta aqui - lo hace exclusivamente
        # reconciliar_movimiento_drive() en cada ciclo (incluido este mismo,
        # justo despues), que siempre verifica la ubicacion real antes de
        # mover. Un solo camino de codigo para mover, en vez de duplicar la
        # logica "intentar ya, reintentar despues si falla" en dos lugares.
    except Exception as exc:
        db.actualizar_estado_trabajo(trabajo_id, "error", error=sanitizar(str(exc)))
        print(f"[procesar] trabajo #{trabajo_id} ERROR: {sanitizar(exc)}")


# ---------------------------------------------------------------------------
# Reconciliacion - 3 pasadas ademas del flujo normal de pendientes, para
# cubrir casos que antes quedaban inalcanzables porque el worker solo
# revisitaba trabajos en 'pendiente'.
# ---------------------------------------------------------------------------

def resetear_huerfanos_procesando() -> None:
    """Al arrancar, antes de hacer polling: con el lock de instancia unica,
    un trabajo en 'procesando' siempre es evidencia de un corte anterior,
    nunca de otro worker corriendo en paralelo."""
    for trabajo in db.listar_trabajos(estado="procesando"):
        db.actualizar_estado_trabajo(trabajo["id"], "pendiente")
        print(f"[worker] trabajo #{trabajo['id']} estaba huerfano en 'procesando' - reseteado a 'pendiente'")


def reconciliar_qa_incompleta() -> None:
    """Unicamente listo_para_revision, NUNCA rechazado ni aprobado - un
    trabajo ya aprobado no debe volver a moverse solo por un bump de
    VERSION_QA, y uno rechazado no vale la pena seguir evaluando."""
    for trabajo in db.listar_trabajos(estado="listo_para_revision"):
        trabajo_id = trabajo["id"]
        foto_gorra = Path(trabajo["ruta_local_foto"])
        for escena_num in ESCENAS_PRODUCCION:
            reciente = db.generacion_mas_reciente(trabajo_id, "nano_banana", escena_num)
            if reciente is None or not db.archivo_es_imagen_valida(reciente["ruta_output"]):
                continue
            evaluacion = db.ultima_evaluacion_vigente(reciente["id"])
            if evaluacion is not None and evaluacion["qa_error"] == 0:
                continue
            if db.qa_agotado(reciente["id"]):
                continue
            qa = evaluar_calidad(foto_gorra, _ruta_escena(escena_num), Path(reciente["ruta_output"]),
                                  generacion_id=reciente["id"])
            estado_txt = "qa_error" if qa.get("qa_error") else "completa"
            print(f"[reconciliacion QA] trabajo #{trabajo_id} escena {escena_num}: {estado_txt}")


def reconciliar_movimiento_drive() -> None:
    """drive_carpeta es solo una cache barata para no consultar la API en
    cada ciclo para cada trabajo terminal - nunca decide un movimiento por
    si sola. Antes de mover cualquier cosa, siempre se verifica la
    ubicacion real via la API de Drive. Esto autocura tanto una carrera con
    una decision humana concurrente como un crash del worker justo entre el
    movimiento remoto y el UPDATE local."""
    for estado in ("listo_para_revision", "aprobado", "rechazado"):
        for trabajo in db.listar_trabajos(estado=estado):
            destino = _destino_deseado(trabajo["estado"])
            if destino is None or trabajo["drive_carpeta"] == destino:
                continue

            try:
                ubicacion_real = drive.ubicacion_actual(trabajo["drive_file_id"])
            except Exception as exc:
                print(f"[reconciliacion Drive] trabajo #{trabajo['id']}: no se pudo verificar la "
                      f"ubicacion real: {sanitizar(exc)}")
                continue

            if ubicacion_real == destino:
                # ya esta donde debe (crash previo entre mover y persistir,
                # u otra corrida ya lo movio) - solo se actualiza la cache.
                db.actualizar_drive_carpeta_observada(trabajo["id"], destino)
                continue

            try:
                drive.mover_a(trabajo["drive_file_id"], destino)
            except Exception as exc:
                print(f"[reconciliacion Drive] trabajo #{trabajo['id']}: fallo moviendo a "
                      f"{destino}: {sanitizar(exc)}")
                continue

            # CAS: si el estado cambio entre la lectura de arriba y este
            # UPDATE (un humano decidio algo mientras tanto), no hace falta
            # ninguna recuperacion especial - el proximo ciclo relee el
            # estado actualizado y vuelve a verificar la ubicacion real
            # antes de decidir, como siempre.
            db.actualizar_drive_carpeta(trabajo["id"], destino, estado_esperado=trabajo["estado"])


def reconciliar_rechazos_pendientes() -> None:
    for file_id in db.archivos_rechazados_pendientes():
        try:
            drive.marcar_como_rechazado(file_id)
            db.marcar_rechazo_movido(file_id)
        except Exception as exc:
            print(f"[reconciliacion rechazos] {file_id}: fallo moviendo a rechazados en Drive: {sanitizar(exc)}")


def ciclo_una_vez() -> None:
    encolar_archivos_nuevos()
    for trabajo in db.listar_trabajos(estado="pendiente"):
        procesar_trabajo(trabajo)
    reconciliar_qa_incompleta()
    reconciliar_movimiento_drive()
    reconciliar_rechazos_pendientes()


def main():
    lock = adquirir_lock_worker()
    try:
        db.inicializar_db()
        resetear_huerfanos_procesando()

        una_vez = "--once" in sys.argv
        print(f"[worker] Iniciando. Carpeta de ingesta revisada cada {INTERVALO_SEGUNDOS}s.")
        while True:
            ciclo_una_vez()
            if una_vez:
                break
            time.sleep(INTERVALO_SEGUNDOS)
    finally:
        lock.release()


if __name__ == "__main__":
    main()
