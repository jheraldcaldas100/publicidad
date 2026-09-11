"""
Fase 4 - Validacion de una muestra del banco de escenas mejoradas con PROMPT_V3.
Corre Pista B (Nano Banana) sobre 8 escenas representativas (variando entorno,
postura y visibilidad de rostro) usando el prompt de produccion vigente
(color + forma). Sin QA automatico - las imagenes se guardan para revision
manual contra docs/checklist-qa-seccion-6.2.md (los 8 items).
"""
import csv
import datetime
from pathlib import Path

import fal_client
import requests
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SKU = "HOMIE-BLK-001"
FOTO_GORRA = ROOT / "assets" / "skus" / "HOMIE-BLK-001_3q.jpeg"
ESCENAS_DIR = ROOT / "assets" / "escenas_base_mejoradas"
OUTPUT_DIR = ROOT / "output" / "fase4_validacion"
REGISTRO_CSV = OUTPUT_DIR / "registro_fase4_validacion.csv"

# muestra representativa: distintos entornos/posturas/visibilidad de rostro
MUESTRA = ["04", "05", "09", "11", "16", "22", "29", "33"]

PROMPT_V3 = (
    "Image 1 is a person wearing a plain cap. Image 2 is a product photo of a cap "
    "on a white background. Replace the cap the person is wearing in image 1 with "
    "the exact cap shown in image 2, matching its color, embroidered logo text, and "
    "side patch precisely. "
    "CRITICAL COLOR RULE: the cap's front crown panels must end up WHITE, exactly as "
    "in image 2 - do NOT use the color of the cap currently worn in image 1 for the "
    "crown. Do not blend, average, or tint the two cap colors together. The visor/bill "
    "must be BLACK, exactly as in image 2. "
    "CRITICAL SHAPE RULE: the cap in image 2 is a structured 6-panel cap with a stiff "
    "crown and a MODERATELY CURVED brim (not flat, not floppy). Replicate that exact "
    "crown structure and brim curvature - do NOT use the crown shape, brim curve, or "
    "softness of the cap currently worn in image 1. "
    "Keep the person's face, skin tone, hair, pose, clothing, and background completely "
    "unchanged. Match the head angle and lighting of image 1."
)

CAMPOS_REGISTRO = [
    "timestamp", "escena_id", "sku", "costo_usd", "ruta_output", "error",
]


def registrar(**kwargs):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existe = REGISTRO_CSV.exists()
    with open(REGISTRO_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS_REGISTRO)
        if not existe:
            writer.writeheader()
        fila = {campo: kwargs.get(campo, "") for campo in CAMPOS_REGISTRO}
        fila["timestamp"] = datetime.datetime.now().isoformat(timespec="seconds")
        writer.writerow(fila)


def main():
    escenas = {}
    for numero in MUESTRA:
        candidatos = list(ESCENAS_DIR.glob(f"{numero}_lanczos_*.png"))
        if not candidatos:
            raise SystemExit(f"Falta la escena mejorada numero {numero}")
        escenas[numero] = candidatos[0]

    print(f"Se van a generar {len(escenas)} imagenes (~${len(escenas) * 0.04:.2f})\n")

    print("[setup] Subiendo foto de gorra...")
    url_gorra = fal_client.upload_file(str(FOTO_GORRA))

    for numero, ruta_escena in escenas.items():
        print(f"[muestra {numero}] subiendo escena y generando...")
        try:
            url_escena = fal_client.upload_file(str(ruta_escena))
            resultado = fal_client.run(
                "fal-ai/nano-banana/edit",
                arguments={
                    "prompt": PROMPT_V3,
                    "image_urls": [url_escena, url_gorra],
                    "num_images": 1,
                },
            )
            url_resultado = resultado["images"][0]["url"]
            resp = requests.get(url_resultado, timeout=90)
            resp.raise_for_status()
            ruta_salida = OUTPUT_DIR / f"{SKU}_muestra_{numero}.jpg"
            ruta_salida.parent.mkdir(parents=True, exist_ok=True)
            ruta_salida.write_bytes(resp.content)
            if ruta_salida.suffix.lower() != ".jpg":
                img = Image.open(ruta_salida).convert("RGB")
                ruta_salida = ruta_salida.with_suffix(".jpg")
                img.save(ruta_salida, "JPEG", quality=92)

            registrar(
                escena_id=numero, sku=SKU, costo_usd=0.04,
                ruta_output=str(ruta_salida), error="",
            )
        except Exception as exc:
            print(f"  ERROR: {exc}")
            registrar(
                escena_id=numero, sku=SKU, costo_usd=0.0,
                ruta_output="", error=str(exc),
            )

    print(f"\nListo. Revisa {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
