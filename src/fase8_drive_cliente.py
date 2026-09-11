"""
Fase 8 - Cliente de Google Drive (cuenta de servicio).
Lista archivos nuevos en la carpeta de ingesta (paginando el listado
completo), los descarga localmente con un limite de tamano real, y mueve los
ya procesados/rechazados a subcarpetas dentro de Drive - siempre verificando
la ubicacion real del archivo antes de moverlo, nunca confiando en una
cache local para decidir.
"""
import io
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from seguridad import sanitizar

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SCOPES = ["https://www.googleapis.com/auth/drive"]

EXTENSIONES_VALIDAS = {".jpg", ".jpeg", ".png", ".webp"}
LIMITE_BYTES_ENTRADA = 20 * 1024 * 1024  # 20MB - descarga desde Drive
TAMANO_CHUNK = 256 * 1024

# el sku se deriva del nombre de archivo saneado, pero necesita su propia
# validacion explicita: sanear el nombre para la ruta de *entrada* no
# garantiza que el sku derivado sea seguro para las rutas de *salida* de
# Pista A/B (seccion 7 del plan) - un componente de ruta vacio, con puntos
# al final, o un nombre reservado de Windows (CON, NUL, AUX, ...) puede
# colarse igual.
RE_SKU_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
NOMBRES_RESERVADOS_WINDOWS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# drive_file_id tal como lo devuelve la API de Google - alfanumerico con
# guion y guion bajo, nunca separadores de ruta.
RE_DRIVE_FILE_ID_VALIDO = re.compile(r"^[A-Za-z0-9_-]{10,128}$")


class ArchivoRechazado(Exception):
    """El archivo descargado (o su nombre) no paso validacion - se mueve a
    la carpeta 'rechazados' de Drive en vez de encolarse como trabajo."""

    def __init__(self, razon: str):
        super().__init__(razon)
        self.razon = razon


def _cliente():
    ruta_credenciales = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not ruta_credenciales:
        raise SystemExit(
            "Falta GOOGLE_SERVICE_ACCOUNT_FILE en .env. "
            "Ver docs/brief-fase8-google-drive.md para los pasos de configuracion."
        )
    ruta = Path(ruta_credenciales)
    if not ruta.is_absolute():
        ruta = ROOT / ruta
    if not ruta.exists():
        raise SystemExit(
            f"No existe el archivo de credenciales: {ruta}. "
            "Ver docs/brief-fase8-google-drive.md para los pasos de configuracion."
        )
    credenciales = service_account.Credentials.from_service_account_file(
        str(ruta), scopes=SCOPES
    )
    return build("drive", "v3", credentials=credenciales)


def _carpeta_id() -> str:
    carpeta_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not carpeta_id:
        raise SystemExit("Falta GOOGLE_DRIVE_FOLDER_ID en .env")
    return carpeta_id


_cache_subcarpetas: dict[str, str] = {}


def _subcarpeta_id(servicio, nombre: str) -> str:
    """Obtiene o crea una subcarpeta directa de la carpeta raiz de ingesta
    (p.ej. 'procesados', 'rechazados'). Cacheada en memoria del proceso - el
    id de una carpeta no cambia durante la vida de un ciclo del worker."""
    if nombre in _cache_subcarpetas:
        return _cache_subcarpetas[nombre]

    carpeta_padre_id = _carpeta_id()
    query = (
        f"'{carpeta_padre_id}' in parents and name = '{nombre}' "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    resultado = servicio.files().list(q=query, fields="files(id, name)").execute()
    archivos = resultado.get("files", [])
    if archivos:
        _cache_subcarpetas[nombre] = archivos[0]["id"]
        return archivos[0]["id"]

    metadata = {
        "name": nombre,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [carpeta_padre_id],
    }
    carpeta = servicio.files().create(body=metadata, fields="id").execute()
    _cache_subcarpetas[nombre] = carpeta["id"]
    return carpeta["id"]


def listar_archivos_nuevos() -> list[dict]:
    """Lista imagenes en la carpeta de ingesta (sin bajar a las subcarpetas
    'procesados'/'rechazados'), paginando el listado completo - con el
    tamano de pagina por defecto, archivos rechazables en la primera pagina
    podian "tapar" archivos validos de paginas siguientes que nunca se
    llegaban a ver."""
    servicio = _cliente()
    carpeta_id = _carpeta_id()

    query = f"'{carpeta_id}' in parents and trashed = false"
    archivos = []
    page_token = None
    while True:
        resultado = servicio.files().list(
            q=query, fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=100, pageToken=page_token,
        ).execute()
        for archivo in resultado.get("files", []):
            if archivo["mimeType"] == "application/vnd.google-apps.folder":
                continue
            if Path(archivo["name"]).suffix.lower() not in EXTENSIONES_VALIDAS:
                continue
            archivos.append(archivo)
        page_token = resultado.get("nextPageToken")
        if not page_token:
            break
    return archivos


def _sanear_nombre_archivo(nombre: str) -> str:
    """Solo para el nombre de archivo de la ruta de *entrada* - no valida
    que el stem resultante sea un sku seguro, eso lo hace derivar_sku()."""
    stem = Path(nombre).stem
    sufijo = Path(nombre).suffix.lower()
    stem_saneado = re.sub(r"[^A-Za-z0-9_-]", "_", stem)
    return f"{stem_saneado}{sufijo}"


def derivar_sku(nombre_archivo_original: str) -> str:
    """Deriva y valida el sku contra el stem ORIGINAL, sin sanear primero -
    sanear antes de validar (reemplazando '.', espacios, etc. por '_')
    dejaria pasar como sku valido justo los nombres que se supone deben
    rechazarse (p.ej. '...jpg' -> stem '..' -> saneado '__', que si
    matchea el patron). Lanza ArchivoRechazado si el stem no matchea
    exactamente [A-Za-z0-9_-]{1,64} o es un nombre reservado de Windows -
    no se le asigna un sku generico ni se adivina uno."""
    stem = Path(nombre_archivo_original).stem
    if not RE_SKU_VALIDO.match(stem):
        raise ArchivoRechazado(f"nombre de archivo no produce un SKU valido: {nombre_archivo_original!r}")
    if stem.upper() in NOMBRES_RESERVADOS_WINDOWS:
        raise ArchivoRechazado(f"nombre de archivo reservado de Windows: {stem!r}")
    return stem


def _validar_file_id(file_id: str) -> None:
    if not RE_DRIVE_FILE_ID_VALIDO.match(file_id):
        raise ValueError(f"drive_file_id con formato inesperado, rechazado por seguridad: {file_id!r}")


def descargar_archivo(file_id: str, nombre_archivo_original: str, directorio_base: Path) -> Path:
    """Descarga a directorio_base/<drive_file_id>/<nombre_saneado> (el
    drive_file_id como componente de ruta hace la ruta colision-proof: dos
    archivos con el mismo nombre nunca se pisan). Streaming con limite real
    de bytes - aborta y borra el archivo/buffer parcial si se supera
    LIMITE_BYTES_ENTRADA durante la descarga, no solo si el campo `size`
    reportado por la API ya lo superaba. Escribe a un temporal y usa
    os.replace() atomico."""
    _validar_file_id(file_id)
    servicio = _cliente()

    nombre_saneado = _sanear_nombre_archivo(nombre_archivo_original)
    directorio_destino = (directorio_base / file_id).resolve()
    directorio_base_resuelto = directorio_base.resolve()
    if directorio_base_resuelto not in directorio_destino.parents and directorio_destino != directorio_base_resuelto:
        raise ValueError("ruta de destino fuera del directorio esperado - rechazado por seguridad")
    directorio_destino.mkdir(parents=True, exist_ok=True)
    destino = directorio_destino / nombre_saneado

    request = servicio.files().get_media(fileId=file_id)
    temporal = destino.with_suffix(destino.suffix + ".tmp")

    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request, chunksize=TAMANO_CHUNK)
    try:
        listo = False
        while not listo:
            _, listo = downloader.next_chunk()
            if buffer.tell() > LIMITE_BYTES_ENTRADA:
                raise ArchivoRechazado(
                    f"excede el limite de {LIMITE_BYTES_ENTRADA} bytes durante la descarga"
                )
        temporal.write_bytes(buffer.getvalue())
        os.replace(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)

    return destino


def renombrar_archivo(file_id: str, nuevo_nombre: str) -> None:
    _validar_file_id(file_id)
    servicio = _cliente()
    servicio.files().update(fileId=file_id, body={"name": nuevo_nombre}).execute()


def obtener_parents_actuales(file_id: str) -> list[str]:
    """Fuente de verdad de la ubicacion fisica real del archivo en Drive -
    nunca se infiere de una cache local."""
    _validar_file_id(file_id)
    servicio = _cliente()
    archivo = servicio.files().get(fileId=file_id, fields="parents").execute()
    return archivo.get("parents", [])


def ubicacion_actual(file_id: str) -> str | None:
    """'procesados' / 'rechazados' / None (todavia en la carpeta de entrada,
    o en un lugar que este cliente no reconoce) segun los parents reales
    actuales del archivo."""
    servicio = _cliente()
    parents = obtener_parents_actuales(file_id)
    if _subcarpeta_id(servicio, "procesados") in parents:
        return "procesados"
    if _subcarpeta_id(servicio, "rechazados") in parents:
        return "rechazados"
    return None


def mover_a(file_id: str, nombre_carpeta_destino: str) -> None:
    """Mueve el archivo a la subcarpeta dada ('procesados' o 'rechazados'),
    quitandolo de TODOS sus padres reales actuales (soporta relocalizar
    desde 'procesados' a 'rechazados' o viceversa, no solo desde la carpeta
    de entrada)."""
    if nombre_carpeta_destino not in ("procesados", "rechazados"):
        raise ValueError(f"carpeta destino invalida: {nombre_carpeta_destino!r}")
    _validar_file_id(file_id)
    servicio = _cliente()
    carpeta_destino_id = _subcarpeta_id(servicio, nombre_carpeta_destino)
    parents_actuales = obtener_parents_actuales(file_id)

    try:
        servicio.files().update(
            fileId=file_id,
            addParents=carpeta_destino_id,
            removeParents=",".join(p for p in parents_actuales if p != carpeta_destino_id),
            fields="id, parents",
        ).execute()
    except Exception as exc:
        raise RuntimeError(sanitizar(f"fallo moviendo {file_id} a {nombre_carpeta_destino}: {exc}")) from exc


def marcar_como_procesado(file_id: str) -> None:
    mover_a(file_id, "procesados")


def marcar_como_rechazado(file_id: str) -> None:
    mover_a(file_id, "rechazados")
