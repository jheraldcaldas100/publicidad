"""
Fase 2 - Reintento dirigido de Nano Banana en Test 1 (facil).
Nano Banana fallo 2/5 por un patron especifico: pinto la gorra completa del color
de la gorra de la escena en vez de blanco+negro del SKU real. Se ajusta el prompt
para forzar explicitamente la fidelidad de color y se corre 5 veces mas.

Actualizado en Fase 4: se agrego tambien una regla de forma/estructura (ver
PROMPT_V3) despues de detectar que sin ella la visera sale casi plana en vez de
con la curvatura moderada del SKU real. Ver docs/checklist-qa-seccion-6.2.md item 8.
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
ESCENA = ROOT / "assets" / "escenas_base" / "escena_001.jpg"
OUTPUT_DIR = ROOT / "output" / "fase2" / "nano_banana" / "test1_facil_v2_prompt"
REGISTRO_CSV = ROOT / "output" / "fase2" / "registro_fase2.csv"

CORRIDAS = 5

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
    "timestamp", "modelo_ia", "test", "corrida", "sku", "escena_id",
    "seed", "costo_usd", "ruta_output", "error",
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
    print("[setup] Subiendo imagenes...")
    url_gorra = fal_client.upload_file(str(FOTO_GORRA))
    url_escena = fal_client.upload_file(str(ESCENA))

    for corrida in range(1, CORRIDAS + 1):
        print(f"[nano_banana_v2] test1_facil - corrida {corrida}/{CORRIDAS}")
        ruta_salida = OUTPUT_DIR / f"{SKU}_nano_banana_v2_test1_facil_c{corrida}.jpg"
        try:
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
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            ruta_salida.write_bytes(resp.content)
            if ruta_salida.suffix.lower() != ".jpg":
                img = Image.open(ruta_salida).convert("RGB")
                ruta_salida = ruta_salida.with_suffix(".jpg")
                img.save(ruta_salida, "JPEG", quality=92)

            registrar(
                modelo_ia="nano_banana_v2_prompt", test="test1_facil", corrida=corrida,
                sku=SKU, escena_id=ESCENA.stem, seed="n/a",
                costo_usd=0.04, ruta_output=str(ruta_salida), error="",
            )
        except Exception as exc:
            print(f"  ERROR: {exc}")
            registrar(
                modelo_ia="nano_banana_v2_prompt", test="test1_facil", corrida=corrida,
                sku=SKU, escena_id=ESCENA.stem, seed="n/a",
                costo_usd=0.0, ruta_output="", error=str(exc),
            )

    print(f"\nListo. Revisa {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
