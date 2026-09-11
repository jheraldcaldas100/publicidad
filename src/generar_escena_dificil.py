"""
Genera la escena base 'dificil' (angulo divergente/perfil) para la Fase 2.
Placeholder generado con IA, igual que escena_001 - no necesita ser del banco final.
"""
import os
from pathlib import Path

import fal_client
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SALIDA = ROOT / "assets" / "escenas_base" / "escena_002.jpg"

PROMPT = (
    "Professional studio portrait photo of a young man wearing a plain solid navy blue "
    "baseball cap, viewed in profile from the side, head turned significantly away from "
    "the camera showing a pronounced divergent angle (close to full side profile), soft "
    "studio lighting, dark blue background, wearing a dark casual t-shirt, photorealistic, "
    "high detail, shoulders and part of torso visible."
)


def main():
    if not os.environ.get("FAL_KEY"):
        raise SystemExit("Falta FAL_KEY en .env")

    print("Generando escena dificil (perfil / angulo divergente)...")
    resultado = fal_client.run(
        "fal-ai/flux/dev",
        arguments={
            "prompt": PROMPT,
            "image_size": "portrait_4_3",
            "num_images": 1,
        },
    )

    imagen_url = resultado["images"][0]["url"]
    resp = requests.get(imagen_url, timeout=60)
    resp.raise_for_status()

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_bytes(resp.content)
    print(f"Guardado: {SALIDA}")


if __name__ == "__main__":
    main()
