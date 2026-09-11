"""
Fase 6 - Demo end-to-end del ciclo generar -> QA -> reintento dirigido,
sobre la escena 09 (conocida por fallar en color en la validacion de Fase 4).
"""
from pathlib import Path

import fal_client
import requests
from dotenv import load_dotenv
from PIL import Image

from fase6_qa_reintento import generar_con_reintento
from prompts import PROMPT_V3

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SKU = "HOMIE-BLK-001"
FOTO_GORRA = ROOT / "assets" / "skus" / "HOMIE-BLK-001_3q.jpeg"
ESCENA = next((ROOT / "assets" / "escenas_base_mejoradas").glob("09_lanczos_*.png"))
OUTPUT_DIR = ROOT / "output" / "fase6" / "demo_reintento"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    url_gorra = fal_client.upload_file(str(FOTO_GORRA))
    url_escena = fal_client.upload_file(str(ESCENA))

    contador = {"n": 0}

    def funcion_generar(prompt_extra: str) -> Path:
        contador["n"] += 1
        prompt = PROMPT_V3 + ("\n\n" + prompt_extra if prompt_extra else "")
        resultado = fal_client.run(
            "fal-ai/nano-banana/edit",
            arguments={
                "prompt": prompt,
                "image_urls": [url_escena, url_gorra],
                "num_images": 1,
            },
        )
        url_img = resultado["images"][0]["url"]
        resp = requests.get(url_img, timeout=90)
        ruta = OUTPUT_DIR / f"intento_{contador['n']}.jpg"
        ruta.write_bytes(resp.content)
        return ruta

    print(f"Escena de prueba: {ESCENA.name}\n")
    # on_generada=None: este script de demo no crea un trabajo real, asi
    # que evaluar_calidad() no persiste nada (generacion_id=None).
    resultado = generar_con_reintento(funcion_generar, FOTO_GORRA, ESCENA, max_intentos=2)

    qa = resultado["qa"]
    if qa.get("qa_error"):
        print(f"\nResultado final: {resultado['intentos']} intento(s), qa_error: {qa['detalle']}")
    else:
        print(f"\nResultado final: {resultado['intentos']} intento(s), "
              f"score final={qa['score']}, aprobado={qa['aprobado']}")
    print(f"Imagen final: {resultado['ruta_final']}")


if __name__ == "__main__":
    main()
