"""
Fase 4 - Sube la resolucion de las escenas base a >=2000px en el lado corto.
Metodo: interpolacion Lanczos local (sin costo, sin llamadas a ninguna API).
No agrega detalle nuevo (no es un upscaler de IA) - solo da margen de pixeles
para poder recortar a 4:5/1:1/9:16 sin quedarse corto en la imagen fuente.
Factor de escala calculado por imagen para que TODAS lleguen al mismo lado
corto objetivo, sin importar su resolucion original.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ORIGEN = ROOT / "assets" / "escenas_base"
DESTINO = ROOT / "assets" / "escenas_base_mejoradas"

LADO_CORTO_OBJETIVO = 2048


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    archivos = sorted(ORIGEN.glob("*.png"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0)

    for archivo in archivos:
        numero = archivo.stem
        ya_existe = list(DESTINO.glob(f"{numero}_lanczos_*.png"))
        if ya_existe:
            print(f"{numero}: ya existe ({ya_existe[0].name}), omitiendo")
            continue

        img = Image.open(archivo)
        lado_corto_actual = min(img.size)
        factor = LADO_CORTO_OBJETIVO / lado_corto_actual
        nuevo_size = (round(img.width * factor), round(img.height * factor))

        img_mejorada = img.resize(nuevo_size, Image.LANCZOS)
        salida = DESTINO / f"{numero}_lanczos_{factor:.2f}x.png"
        img_mejorada.save(salida)
        print(f"{numero}: {img.size} -> {nuevo_size} (factor {factor:.2f}x) -> {salida.name}")

    print("\nListo.")


if __name__ == "__main__":
    main()
