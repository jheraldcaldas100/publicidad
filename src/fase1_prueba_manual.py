"""
Fase 1 - Prueba manual end-to-end.
Toma 1 gorra + 1 escena base y produce las dos imagenes de una publicacion.
Sin cola, sin Drive, sin panel de revision - solo valida que el flujo corre.
"""
import csv
import datetime
import os
import sys
from pathlib import Path

import fal_client
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFilter
from rembg import remove

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SKU = "HOMIE-BLK-001"
FOTO_GORRA = ROOT / "assets" / "skus" / "HOMIE-BLK-001_3q.jpeg"
ESCENA_BASE = ROOT / "assets" / "escenas_base" / "escena_001.jpg"
OUTPUT_DIR = ROOT / "output"
REGISTRO_CSV = OUTPUT_DIR / "registro.csv"

FORMATO_ANCHO, FORMATO_ALTO = 1080, 1350  # 4:5, feed principal

CAMPOS_REGISTRO = [
    "timestamp", "sku", "escena_id", "modelo_ia", "prompt",
    "seed", "intento", "score_qa", "problema", "costo_usd", "ruta_output",
]


def registrar_generacion(**kwargs):
    OUTPUT_DIR.mkdir(exist_ok=True)
    existe = REGISTRO_CSV.exists()
    with open(REGISTRO_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_REGISTRO)
        if not existe:
            writer.writeheader()
        fila = {campo: kwargs.get(campo, "") for campo in CAMPOS_REGISTRO}
        fila["timestamp"] = datetime.datetime.now().isoformat(timespec="seconds")
        writer.writerow(fila)


def generar_imagen_producto(foto_gorra: Path) -> Path:
    """Pista A: compositing deterministico, sin IA. Mismo input -> mismo output siempre."""
    print("[Pista A] Quitando fondo de la foto de producto...")
    with open(foto_gorra, "rb") as f:
        recorte = remove(f.read())  # PNG con canal alfa

    recorte_path = OUTPUT_DIR / f"{SKU}_recorte.png"
    OUTPUT_DIR.mkdir(exist_ok=True)
    recorte_path.write_bytes(recorte)

    cutout = Image.open(recorte_path).convert("RGBA")
    bbox = cutout.getbbox()
    cutout = cutout.crop(bbox)

    # Fondo: degradado plano placeholder (pendiente paleta de marca real)
    fondo = Image.new("RGB", (FORMATO_ANCHO, FORMATO_ALTO), "#e8e4dc")
    draw = ImageDraw.Draw(fondo)
    color_top = (232, 228, 220)
    color_bottom = (196, 190, 176)
    for y in range(FORMATO_ALTO):
        t = y / FORMATO_ALTO
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * t)
        draw.line([(0, y), (FORMATO_ANCHO, y)], fill=(r, g, b))

    # Escalar gorra a ~55% del ancho del canvas
    escala = (FORMATO_ANCHO * 0.55) / cutout.width
    nuevo_ancho = int(cutout.width * escala)
    nuevo_alto = int(cutout.height * escala)
    cutout = cutout.resize((nuevo_ancho, nuevo_alto), Image.LANCZOS)

    pos_x = (FORMATO_ANCHO - nuevo_ancho) // 2
    pos_y = (FORMATO_ALTO - nuevo_alto) // 2 - 60

    # Sombra proyectada: elipse difuminada bajo la gorra
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

    fondo.paste(cutout, (pos_x, pos_y), cutout)

    salida = OUTPUT_DIR / f"{SKU}_producto_4x5_v1.jpg"
    fondo.convert("RGB").save(salida, "JPEG", quality=90)
    print(f"[Pista A] Guardado: {salida}")

    registrar_generacion(
        sku=SKU, escena_id="n/a", modelo_ia="compositing_local",
        prompt="n/a", seed="n/a", intento=1, score_qa="n/a",
        problema="", costo_usd=0.0, ruta_output=str(salida),
    )
    return salida


def generar_imagen_contexto(foto_gorra: Path, escena_base: Path) -> Path:
    """Pista B: edicion por IA. Reemplaza la gorra de la escena base por la del SKU."""
    print("[Pista B] Subiendo imagenes a fal.ai...")
    url_escena = fal_client.upload_file(str(escena_base))
    url_gorra = fal_client.upload_file(str(foto_gorra))

    prompt = (
        "Image 1 is a person wearing a plain cap. Image 2 is a product photo of a cap "
        "on a white background. Replace the cap the person is wearing in image 1 with "
        "the exact cap shown in image 2, matching its color, embroidered logo text, and "
        "side patch precisely. Keep the person's face, skin tone, hair, pose, clothing, "
        "and background completely unchanged. Match the head angle and lighting of image 1."
    )

    print("[Pista B] Llamando a fal-ai/flux-pro/kontext/multi (costo real ~$0.03-0.04)...")
    modelo = "fal-ai/flux-pro/kontext/multi"
    resultado = fal_client.run(
        modelo,
        arguments={
            "prompt": prompt,
            "image_urls": [url_escena, url_gorra],
            "num_images": 1,
        },
    )

    imagen_url = resultado["images"][0]["url"]
    seed = resultado.get("seed", "n/a")

    import requests
    resp = requests.get(imagen_url, timeout=60)
    resp.raise_for_status()

    salida_raw = OUTPUT_DIR / f"{SKU}_modelo_4x5_v1_raw.jpg"
    salida_raw.write_bytes(resp.content)

    img = Image.open(salida_raw).convert("RGB")
    if img.size != (FORMATO_ANCHO, FORMATO_ALTO):
        img = img.resize((FORMATO_ANCHO, FORMATO_ALTO), Image.LANCZOS)
    salida = OUTPUT_DIR / f"{SKU}_modelo_4x5_v1.jpg"
    img.save(salida, "JPEG", quality=90)
    print(f"[Pista B] Guardado: {salida}")

    registrar_generacion(
        sku=SKU, escena_id=escena_base.stem, modelo_ia=modelo,
        prompt=prompt, seed=seed, intento=1, score_qa="pendiente_revision_manual",
        problema="", costo_usd=0.03, ruta_output=str(salida),
    )
    return salida


def main():
    if not FOTO_GORRA.exists():
        sys.exit(f"Falta la foto de la gorra: {FOTO_GORRA}")
    if not ESCENA_BASE.exists():
        sys.exit(f"Falta la escena base: {ESCENA_BASE}")
    if not os.environ.get("FAL_KEY"):
        sys.exit("Falta FAL_KEY en .env")

    generar_imagen_producto(FOTO_GORRA)
    generar_imagen_contexto(FOTO_GORRA, ESCENA_BASE)

    print("\nFase 1 completa. Revisa las imagenes en output/ y el registro en output/registro.csv")


if __name__ == "__main__":
    main()
