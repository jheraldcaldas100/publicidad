"""
Ayudante minimo para probar inicializar_db() concurrente entre 2 procesos
reales, sin arrancar nada mas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db  # noqa: E402

if __name__ == "__main__":
    db.inicializar_db()
    print("INICIALIZADO", flush=True)
