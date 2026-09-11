"""
Fase 5 - Pista A en produccion (compositing deterministico, sin IA).
Recibe cualquier foto normalizada de gorra y produce la imagen de catalogo
(recorte + fondo + sombra) en los 3 formatos de salida (4:5, 1:1, 9:16).

Criterio de aprobacion: correr el mismo input 5 veces produce exactamente el
mismo output (hash identico). No usa ninguna API externa - el recorte de fondo
corre localmente con rembg (mismo modelo ya descargado en Fase 1).
"""
import hashlib
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from rembg import new_session, remove

ROOT = Path(__file__).resolve().parent.parent

FORMATOS = {
    "4x5": (1080, 1350),   # feed principal
    "1x1": (1080, 1080),   # feed cuadrado
    "9x16": (1080, 1920),  # stories/reels
}

COLOR_TOP = (232, 228, 220)
COLOR_BOTTOM = (196, 190, 176)
ESCALA_ANCHO_GORRA = 0.55

# sesion reutilizable: crear una InferenceSession por llamada agota la memoria
# cuando se procesan varios SKU seguidos en el mismo proceso (ver Fase 7)
_SESION = None


def _obtener_sesion():
    global _SESION
    if _SESION is None:
        _SESION = new_session("bria-rmbg")
    return _SESION


def _quitar_fondo(foto_gorra: Path) -> Image.Image:
    with open(foto_gorra, "rb") as f:
        recorte_bytes = remove(f.read(), session=_obtener_sesion())
    cutout = Image.open(io.BytesIO(recorte_bytes)).convert("RGBA")
    bbox = cutout.getbbox()
    return cutout.crop(bbox)


def _fondo_degradado(ancho: int, alto: int) -> Image.Image:
    fondo = Image.new("RGB", (ancho, alto), COLOR_TOP)
    draw = ImageDraw.Draw(fondo)
    for y in range(alto):
        t = y / alto
        r = int(COLOR_TOP[0] + (COLOR_BOTTOM[0] - COLOR_TOP[0]) * t)
        g = int(COLOR_TOP[1] + (COLOR_BOTTOM[1] - COLOR_TOP[1]) * t)
        b = int(COLOR_TOP[2] + (COLOR_BOTTOM[2] - COLOR_TOP[2]) * t)
        draw.line([(0, y), (ancho, y)], fill=(r, g, b))
    return fondo


def _componer_formato(cutout: Image.Image, ancho: int, alto: int) -> Image.Image:
    fondo = _fondo_degradado(ancho, alto)

    escala = (ancho * ESCALA_ANCHO_GORRA) / cutout.width
    nuevo_ancho = int(cutout.width * escala)
    nuevo_alto = int(cutout.height * escala)
    gorra = cutout.resize((nuevo_ancho, nuevo_alto), Image.LANCZOS)

    pos_x = (ancho - nuevo_ancho) // 2
    pos_y = (alto - nuevo_alto) // 2 - int(alto * 0.04)

    sombra = Image.new("RGBA", fondo.size, (0, 0, 0, 0))
    sombra_draw = ImageDraw.Draw(sombra)
    cx = pos_x + nuevo_ancho // 2
    cy = pos_y + nuevo_alto + 20
    sombra_draw.ellipse(
        [cx - nuevo_ancho * 0.35, cy - 20, cx + nuevo_ancho * 0.35, cy + 20],
        fill=(0, 0, 0, 90),
    )
    sombra = sombra.filter(ImageFilter.GaussianBlur(18))
    fondo.paste(sombra, (0, 0), sombra)

    fondo.paste(gorra, (pos_x, pos_y), gorra)
    return fondo


def generar_imagen_producto(foto_gorra: Path, sku: str, output_dir: Path,
                             formatos: list[str] | None = None) -> dict[str, Path]:
    """Pista A: compositing deterministico, sin IA. Mismo input -> mismo output siempre.

    formatos: subconjunto de FORMATOS a producir (p.ej. ["1x1"] para
    regenerar solo un formato faltante/corrupto sin tocar los otros dos ya
    validos). None (por defecto) = los 3, comportamiento sin cambios."""
    nombres_formato = formatos if formatos is not None else list(FORMATOS)
    cutout = _quitar_fondo(foto_gorra)

    output_dir.mkdir(parents=True, exist_ok=True)
    salidas = {}
    for nombre_formato in nombres_formato:
        ancho, alto = FORMATOS[nombre_formato]
        imagen = _componer_formato(cutout, ancho, alto)
        salida = output_dir / f"{sku}_producto_{nombre_formato}.jpg"
        imagen.convert("RGB").save(salida, "JPEG", quality=90)
        salidas[nombre_formato] = salida

    return salidas


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def validar_determinismo(foto_gorra: Path, sku: str, corridas: int = 5) -> bool:
    """Corre generar_imagen_producto N veces y verifica hash identico por formato."""
    output_dir = ROOT / "output" / "fase5" / "determinismo"
    hashes: dict[str, list[str]] = {fmt: [] for fmt in FORMATOS}

    for corrida in range(1, corridas + 1):
        corrida_dir = output_dir / f"corrida_{corrida}"
        print(f"[Fase 5] Corrida {corrida}/{corridas}...")
        salidas = generar_imagen_producto(foto_gorra, sku, corrida_dir)
        for fmt, ruta in salidas.items():
            hashes[fmt].append(_sha256(ruta))

    print("\nResultado de determinismo por formato:")
    todo_ok = True
    for fmt, lista_hashes in hashes.items():
        idéntico = len(set(lista_hashes)) == 1
        todo_ok = todo_ok and idéntico
        estado = "IDENTICO" if idéntico else "DIFIERE"
        print(f"  {fmt}: {estado} ({len(set(lista_hashes))} hash(es) distinto(s) en {corridas} corridas)")
        if not idéntico:
            for i, h in enumerate(lista_hashes, 1):
                print(f"    corrida {i}: {h}")

    return todo_ok


def main():
    if len(sys.argv) < 3:
        sys.exit("Uso: python fase5_pista_a_produccion.py <foto_gorra> <sku>")

    foto_gorra = Path(sys.argv[1])
    sku = sys.argv[2]

    if not foto_gorra.exists():
        sys.exit(f"No existe: {foto_gorra}")

    ok = validar_determinismo(foto_gorra, sku)
    print(f"\n{'APROBADO' if ok else 'FALLA'}: determinismo {'confirmado' if ok else 'NO confirmado'} en 5 corridas.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
