"""
Fase 3 - Medicion de tolerancia de angulo.
3 escenas (frontal, 3/4, perfil) x 3 corridas cada una, con el modelo ganador de la
Fase 2 (Nano Banana) y su prompt corregido (PROMPT_V3). Sin QA automatico - las
imagenes se guardan para revision manual contra docs/checklist-qa-seccion-6.2.md.

Actualizado en Fase 4: PROMPT_V3 agrega una regla de forma/estructura ademas de la
regla de color de PROMPT_V3 (ver docs/checklist-qa-seccion-6.2.md item 8).
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
OUTPUT_DIR = ROOT / "output" / "fase3"
REGISTRO_CSV = OUTPUT_DIR / "registro_fase3.csv"

CORRIDAS_POR_ESCENA = 3

# angulo aproximado en grados, estimado visualmente (frontal=0, 3/4=45, perfil=90)
ESCENAS = {
    "frontal_0deg": (ROOT / "assets" / "escenas_base" / "escena_003.jpg", 0),
    "tresq_45deg": (ROOT / "assets" / "escenas_base" / "escena_001.jpg", 45),
    "perfil_90deg": (ROOT / "assets" / "escenas_base" / "escena_002.jpg", 90),
}

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
    "timestamp", "escena_id", "angulo_grados", "corrida", "sku",
    "costo_usd", "ruta_output", "error",
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
    for nombre, (ruta, _) in ESCENAS.items():
        if not ruta.exists():
            raise SystemExit(f"Falta la escena '{nombre}': {ruta}")

    total = len(ESCENAS) * CORRIDAS_POR_ESCENA
    print(f"Se van a generar {total} imagenes (~${total * 0.04:.2f})\n")

    print("[setup] Subiendo foto de gorra...")
    url_gorra = fal_client.upload_file(str(FOTO_GORRA))

    urls_escena = {}
    for nombre, (ruta, _) in ESCENAS.items():
        print(f"[setup] Subiendo escena '{nombre}'...")
        urls_escena[nombre] = fal_client.upload_file(str(ruta))

    for nombre, (ruta, angulo) in ESCENAS.items():
        for corrida in range(1, CORRIDAS_POR_ESCENA + 1):
            ruta_salida = OUTPUT_DIR / nombre / f"{SKU}_{nombre}_c{corrida}.jpg"
            print(f"[{nombre} / {angulo}deg] corrida {corrida}/{CORRIDAS_POR_ESCENA}")
            try:
                resultado = fal_client.run(
                    "fal-ai/nano-banana/edit",
                    arguments={
                        "prompt": PROMPT_V3,
                        "image_urls": [urls_escena[nombre], url_gorra],
                        "num_images": 1,
                    },
                )
                url_resultado = resultado["images"][0]["url"]
                resp = requests.get(url_resultado, timeout=90)
                resp.raise_for_status()
                ruta_salida.parent.mkdir(parents=True, exist_ok=True)
                ruta_salida.write_bytes(resp.content)
                if ruta_salida.suffix.lower() != ".jpg":
                    img = Image.open(ruta_salida).convert("RGB")
                    ruta_salida = ruta_salida.with_suffix(".jpg")
                    img.save(ruta_salida, "JPEG", quality=92)

                registrar(
                    escena_id=nombre, angulo_grados=angulo, corrida=corrida, sku=SKU,
                    costo_usd=0.04, ruta_output=str(ruta_salida), error="",
                )
            except Exception as exc:
                print(f"  ERROR: {exc}")
                registrar(
                    escena_id=nombre, angulo_grados=angulo, corrida=corrida, sku=SKU,
                    costo_usd=0.0, ruta_output="", error=str(exc),
                )

    print(f"\nFase 3 completa. Revisa {OUTPUT_DIR} y califica cada imagen contra "
          f"docs/checklist-qa-seccion-6.2.md")


if __name__ == "__main__":
    main()
