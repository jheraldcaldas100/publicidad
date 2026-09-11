"""
Fase 6 - Validacion del clasificador de QA contra 10 generaciones ya conocidas
(mezcla de buenas y con fallas evidentes, juzgadas manualmente en Fase 2 y 4).
Criterio de aprobacion: el clasificador debe coincidir con el juicio humano en
al menos 8 de 10 casos.
"""
import csv
import datetime
import sys
from pathlib import Path

from fase6_qa_reintento import evaluar_calidad

ROOT = Path(__file__).resolve().parent.parent
FOTO_SKU = ROOT / "assets" / "skus" / "HOMIE-BLK-001_3q.jpeg"
REGISTRO_CSV = ROOT / "output" / "fase6" / "registro_validacion_clasificador.csv"

# (ruta, juicio_humano_aprobado, motivo del juicio humano)
LOTE = [
    (ROOT / "output/fase2/nano_banana/test1_facil/HOMIE-BLK-001_nano_banana_test1_facil_c1.jpg",
     False, "gorra completa negra (color no coincide)"),
    (ROOT / "output/fase2/nano_banana/test1_facil/HOMIE-BLK-001_nano_banana_test1_facil_c2.jpg",
     False, "gorra completa negra (color no coincide)"),
    (ROOT / "output/fase4_validacion/HOMIE-BLK-001_muestra_04.jpg",
     False, "estructura tipo malla/trucker, no coincide con SKU"),
    (ROOT / "output/fase4_validacion/HOMIE-BLK-001_muestra_09.jpg",
     False, "gorra completa gris (color no coincide)"),
    (ROOT / "output/fase2/nano_banana/test1_facil/HOMIE-BLK-001_nano_banana_test1_facil_c3.jpg",
     True, "pass limpio"),
    (ROOT / "output/fase3/frontal_0deg/HOMIE-BLK-001_frontal_0deg_c1.jpg",
     True, "pass limpio"),
    (ROOT / "output/fase3/tresq_45deg/HOMIE-BLK-001_tresq_45deg_c1.jpg",
     True, "pass limpio"),
    (ROOT / "output/fase3/perfil_90deg/HOMIE-BLK-001_perfil_90deg_c1.jpg",
     True, "pass limpio"),
    (ROOT / "output/fase4_validacion/HOMIE-BLK-001_muestra_11.jpg",
     True, "pass limpio"),
    (ROOT / "output/fase4_validacion/HOMIE-BLK-001_muestra_29.jpg",
     True, "pass limpio"),
]

CAMPOS = ["timestamp", "archivo", "juicio_humano", "juicio_clasificador", "score",
          "coincide", "problema_detectado_por_ia", "motivo_humano"]


def registrar(**kwargs):
    REGISTRO_CSV.parent.mkdir(parents=True, exist_ok=True)
    existe = REGISTRO_CSV.exists()
    with open(REGISTRO_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        if not existe:
            writer.writeheader()
        fila = {c: kwargs.get(c, "") for c in CAMPOS}
        fila["timestamp"] = datetime.datetime.now().isoformat(timespec="seconds")
        writer.writerow(fila)


def main():
    # Este script es de la Fase 6, ya cerrada. No se actualizo a la firma
    # nueva de evaluar_calidad(ruta_producto, ruta_escena, ruta_generada) a
    # proposito: 6 de las 10 muestras de LOTE vienen de fase2/fase3, cuyas
    # fotos de escena original (assets/escenas_base/escena_00{1,2,3}.jpg)
    # ya no existen en el repo (se reorganizaron a assets/escenas_base/
    # 01.png..33.png en una reorganizacion posterior no relacionada con
    # este plan) - inventar una escena de reemplazo para muestras ya
    # juzgadas historicamente seria mas riesgoso que utilidad tiene
    # recalcular este lote. El nuevo clasificador ya se valida en la
    # practica contra datos reales y actuales via el worker de Fase 8 y su
    # panel de revision humana.
    sys.exit(
        "Este script es de la Fase 6, ya cerrada. No se actualizo a la "
        "firma nueva de evaluar_calidad() (requiere una foto de escena "
        "original ademas del producto) porque varias de las muestras del "
        "lote historico referencian fotos de escena que ya no existen en "
        "el repo. Usa el worker de Fase 8 + el panel de revision para "
        "validar el clasificador contra trabajos reales."
    )
    print(f"Se van a evaluar {len(LOTE)} imagenes con el modelo de vision (~$0.01-0.02 c/u)\n")

    aciertos = 0
    for ruta, juicio_humano, motivo in LOTE:
        print(f"[QA] {ruta.name}...")
        resultado = evaluar_calidad(FOTO_SKU, ruta)
        coincide = resultado["aprobado"] == juicio_humano
        aciertos += int(coincide)

        print(f"  humano={juicio_humano} | IA={resultado['aprobado']} (score={resultado['score']}) "
              f"| {'COINCIDE' if coincide else 'NO COINCIDE'}")
        if resultado.get("problema"):
            print(f"  problema detectado por IA: {resultado['problema']}")

        registrar(
            archivo=ruta.name, juicio_humano=juicio_humano,
            juicio_clasificador=resultado["aprobado"], score=resultado["score"],
            coincide=coincide, problema_detectado_por_ia=resultado.get("problema", ""),
            motivo_humano=motivo,
        )

    print(f"\nResultado: {aciertos}/{len(LOTE)} coinciden con el juicio humano.")
    print("APROBADO" if aciertos >= 8 else "FALLA - ajustar el prompt de QA antes de conectar el reintento a produccion")


if __name__ == "__main__":
    main()
