"""
Fase 2 - Comparativa de modelos de IA (Pista B) para elegir el modelo de produccion.
Usa el SKU Homie (caso mas dificil) contra 2-3 modelos candidatos, 2 escenas x 5 corridas.
Sin QA automatico (eso es Fase 6) - las imagenes se guardan para revision manual contra
el checklist de docs/checklist-qa-seccion-6.2.md.
"""
import csv
import datetime
import os
import sys
from pathlib import Path

import fal_client
import requests
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SKU = "HOMIE-BLK-001"
FOTO_GORRA = ROOT / "assets" / "skus" / "HOMIE-BLK-001_3q.jpeg"
OUTPUT_DIR = ROOT / "output" / "fase2"
REGISTRO_CSV = OUTPUT_DIR / "registro_fase2.csv"

CORRIDAS_POR_TEST = 5

ESCENAS = {
    "test1_facil": ROOT / "assets" / "escenas_base" / "escena_001.jpg",
    "test2_dificil": ROOT / "assets" / "escenas_base" / "escena_002.jpg",
}

PROMPT_EDICION = (
    "Image 1 is a person wearing a plain cap. Image 2 is a product photo of a cap "
    "on a white background. Replace the cap the person is wearing in image 1 with "
    "the exact cap shown in image 2, matching its color, embroidered logo text, and "
    "side patch precisely. Keep the person's face, skin tone, hair, pose, clothing, "
    "and background completely unchanged. Match the head angle and lighting of image 1."
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


def guardar_resultado(url_imagen: str, ruta_salida: Path):
    resp = requests.get(url_imagen, timeout=90)
    resp.raise_for_status()
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ruta_salida.write_bytes(resp.content)
    # normaliza a JPEG por si el modelo devuelve PNG/WEBP
    if ruta_salida.suffix.lower() != ".jpg":
        img = Image.open(ruta_salida).convert("RGB")
        ruta_salida = ruta_salida.with_suffix(".jpg")
        img.save(ruta_salida, "JPEG", quality=92)
    return ruta_salida


def correr_flux_kontext(url_escena: str, url_gorra: str):
    """FLUX.1 Kontext [pro] - edicion multi-imagen. ~$0.04/img"""
    resultado = fal_client.run(
        "fal-ai/flux-pro/kontext/multi",
        arguments={
            "prompt": PROMPT_EDICION,
            "image_urls": [url_escena, url_gorra],
            "num_images": 1,
        },
    )
    return resultado["images"][0]["url"], resultado.get("seed", "n/a"), 0.04


def correr_nano_banana(url_escena: str, url_gorra: str):
    """Nano Banana (Gemini 2.5 Flash Image) - edicion multi-imagen. ~$0.04/img"""
    resultado = fal_client.run(
        "fal-ai/nano-banana/edit",
        arguments={
            "prompt": PROMPT_EDICION,
            "image_urls": [url_escena, url_gorra],
            "num_images": 1,
        },
    )
    return resultado["images"][0]["url"], "n/a", 0.04


def correr_fashn(url_escena: str, url_gorra: str):
    """FASHN v1.6 - virtual try-on, no disenado para headwear (categoria auto). ~$0.075/img"""
    resultado = fal_client.run(
        "fal-ai/fashn/tryon/v1.6",
        arguments={
            "model_image": url_escena,
            "garment_image": url_gorra,
            "category": "auto",
        },
    )
    return resultado["images"][0]["url"], "n/a", 0.075


MODELOS = {
    "flux_kontext_pro": correr_flux_kontext,
    "nano_banana": correr_nano_banana,
    "fashn_v1.6": correr_fashn,
}


def main():
    smoke = "--smoke" in sys.argv

    if not FOTO_GORRA.exists():
        sys.exit(f"Falta la foto de la gorra: {FOTO_GORRA}")
    for nombre, ruta in ESCENAS.items():
        if not ruta.exists():
            sys.exit(f"Falta la escena '{nombre}': {ruta}")
    if not os.environ.get("FAL_KEY"):
        sys.exit("Falta FAL_KEY en .env")

    escenas = {"test1_facil": ESCENAS["test1_facil"]} if smoke else ESCENAS
    corridas = 1 if smoke else CORRIDAS_POR_TEST

    total_generaciones = len(MODELOS) * len(escenas) * corridas
    costo_estimado = sum(
        {"flux_kontext_pro": 0.04, "nano_banana": 0.04, "fashn_v1.6": 0.075}[m]
        for m in MODELOS
    ) * len(escenas) * corridas
    print(f"Se van a generar {total_generaciones} imagenes (~${costo_estimado:.2f})\n")

    print("[setup] Subiendo foto de gorra a fal.ai...")
    url_gorra = fal_client.upload_file(str(FOTO_GORRA))

    urls_escena = {}
    for nombre, ruta in escenas.items():
        print(f"[setup] Subiendo escena '{nombre}'...")
        urls_escena[nombre] = fal_client.upload_file(str(ruta))

    for modelo_nombre, funcion in MODELOS.items():
        for test_nombre, ruta_escena in escenas.items():
            url_escena = urls_escena[test_nombre]
            for corrida in range(1, corridas + 1):
                ruta_salida = (
                    OUTPUT_DIR / modelo_nombre / test_nombre
                    / f"{SKU}_{modelo_nombre}_{test_nombre}_c{corrida}.jpg"
                )
                if ruta_salida.exists():
                    print(f"[{modelo_nombre}] {test_nombre} - corrida {corrida}/{corridas} (ya existe, omitiendo)")
                    continue
                print(f"[{modelo_nombre}] {test_nombre} - corrida {corrida}/{corridas}")
                try:
                    url_resultado, seed, costo = funcion(url_escena, url_gorra)
                    ruta_final = guardar_resultado(url_resultado, ruta_salida)
                    registrar(
                        modelo_ia=modelo_nombre, test=test_nombre, corrida=corrida,
                        sku=SKU, escena_id=ruta_escena.stem, seed=seed,
                        costo_usd=costo, ruta_output=str(ruta_final), error="",
                    )
                except Exception as exc:
                    print(f"  ERROR: {exc}")
                    registrar(
                        modelo_ia=modelo_nombre, test=test_nombre, corrida=corrida,
                        sku=SKU, escena_id=ruta_escena.stem, seed="n/a",
                        costo_usd=0.0, ruta_output="", error=str(exc),
                    )

    print(f"\nFase 2 completa. Revisa {OUTPUT_DIR} y califica cada imagen contra "
          f"docs/checklist-qa-seccion-6.2.md")


if __name__ == "__main__":
    main()
