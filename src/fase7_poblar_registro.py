"""
Fase 7 - Corre Fase 5 (Pista A) y Fase 6 (Pista B + QA + reintento) sobre 5 SKU
de prueba, registrando cada llamada en la base de datos (db.py).

Los 5 SKU-id son simulados (misma foto real de HOMIE-BLK-001, distinto sku_id)
para poder probar que las consultas agregadas de la base de datos funcionan -
no representan productos reales distintos. Ver conversacion / decision del
usuario en el momento de esta fase.
"""
import sys
from pathlib import Path

import fal_client
import requests
from dotenv import load_dotenv
from PIL import Image

from db import registrar_generacion
from fase5_pista_a_produccion import generar_imagen_producto
from fase6_qa_reintento import evaluar_calidad, construir_prompt_reintento

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

FOTO_GORRA_REAL = ROOT / "assets" / "skus" / "HOMIE-BLK-001_3q.jpeg"
ESCENAS_DIR = ROOT / "assets" / "escenas_base_mejoradas"
OUTPUT_DIR = ROOT / "output" / "fase7"

SKUS_PRUEBA = [f"TEST-SKU-{i:03d}" for i in range(1, 6)]  # 5 SKU simulados
ESCENAS_PRUEBA = ["04", "09", "29"]  # 2 con historial de falla + 1 limpia
MAX_INTENTOS = 2

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


def ruta_escena(numero: str) -> Path:
    return next(ESCENAS_DIR.glob(f"{numero}_lanczos_*.png"))


def correr_pista_a(sku: str):
    salidas = generar_imagen_producto(FOTO_GORRA_REAL, sku, OUTPUT_DIR / "pista_a" / sku)
    for formato, ruta in salidas.items():
        registrar_generacion(
            sku=sku, escena_id="n/a", modelo_ia="compositing_local",
            prompt="n/a", seed="n/a", intento=1, score_qa=None, problema="",
            costo_usd=0.0, ruta_output=str(ruta),
        )
    print(f"  [Pista A] {sku}: {len(salidas)} formatos generados (costo $0.00)")


def correr_pista_b(sku: str, escena_num: str, url_gorra: str, url_escena_cache: dict):
    if escena_num not in url_escena_cache:
        url_escena_cache[escena_num] = fal_client.upload_file(str(ruta_escena(escena_num)))
    url_escena = url_escena_cache[escena_num]

    salida_dir = OUTPUT_DIR / "pista_b" / sku
    salida_dir.mkdir(parents=True, exist_ok=True)

    for intento in range(1, MAX_INTENTOS + 1):
        prompt_intento = PROMPT_V3
        if intento > 1:
            prompt_intento = construir_prompt_reintento(PROMPT_V3, qa_anterior)

        resultado = fal_client.run(
            "fal-ai/nano-banana/edit",
            arguments={
                "prompt": prompt_intento,
                "image_urls": [url_escena, url_gorra],
                "num_images": 1,
            },
        )
        url_img = resultado["images"][0]["url"]
        resp = requests.get(url_img, timeout=90)
        ruta_salida = salida_dir / f"escena{escena_num}_intento{intento}.jpg"
        ruta_salida.write_bytes(resp.content)

        qa = evaluar_calidad(FOTO_GORRA_REAL, ruta_salida)

        registrar_generacion(
            sku=sku, escena_id=escena_num, modelo_ia="nano_banana",
            prompt=prompt_intento, seed="n/a", intento=intento,
            score_qa=qa["score"], problema=qa.get("problema", ""),
            costo_usd=0.06, ruta_output=str(ruta_salida),
        )
        print(f"  [Pista B] {sku} / escena {escena_num} / intento {intento}: "
              f"score={qa['score']} aprobado={qa['aprobado']}")

        if qa["aprobado"]:
            break
        qa_anterior = qa


def main():
    # Este script es de la Fase 7, ya cerrada y documentada en
    # resultados-fase7.md. No se actualizo a la firma nueva de 3 imagenes de
    # evaluar_calidad() a proposito - no hay razon de negocio para volver a
    # correrlo (usa PROMPT_V3 hardcodeado localmente y escribe
    # generaciones.score_qa directamente, ambos reemplazados por
    # src/prompts.py y evaluaciones_qa en el worker de Fase 8). Salida
    # incondicional, sin bandera de escape: una ruta de escape que ya no
    # funciona (la llamada de mas abajo a evaluar_calidad() con 2
    # argumentos lanzaria TypeError igual) seria peor que no tener ninguna.
    sys.exit(
        "Este script es de la Fase 7, ya cerrada y documentada en "
        "resultados-fase7.md. No se actualizo a la firma nueva de "
        "evaluar_calidad() a proposito - no hay razon de negocio para "
        "volver a correrlo. Usa el worker de Fase 8 en su lugar."
    )
    total_llamadas = len(SKUS_PRUEBA) * len(ESCENAS_PRUEBA)
    print(f"Se van a correr hasta {total_llamadas} generaciones de Pista B "
          f"(+ reintentos posibles) sobre {len(SKUS_PRUEBA)} SKU de prueba x "
          f"{len(ESCENAS_PRUEBA)} escenas. Costo estimado: ~$1.00-1.50\n")

    print("[setup] Subiendo foto de gorra real...")
    url_gorra = fal_client.upload_file(str(FOTO_GORRA_REAL))
    url_escena_cache = {}

    for sku in SKUS_PRUEBA:
        print(f"\n=== {sku} ===")
        correr_pista_a(sku)
        for escena_num in ESCENAS_PRUEBA:
            correr_pista_b(sku, escena_num, url_gorra, url_escena_cache)

    print("\nListo. Corre fase7_consultas.py para ver el reporte agregado desde la base de datos.")


if __name__ == "__main__":
    main()
