"""
Ayudante minimo para probar el lock de instancia unica del worker sin
arrancar el worker completo (que intentaria cargar credenciales reales de
Drive/fal.ai). Solo adquiere el lock (via GORROLANDIA_LOCK_PATH) y espera -
nunca toca Drive, fal.ai, ni hace polling de nada.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fase8_worker_ingesta import adquirir_lock_worker  # noqa: E402

if __name__ == "__main__":
    lock = adquirir_lock_worker()
    print("LOCK_ADQUIRIDO", flush=True)
    try:
        time.sleep(30)
    finally:
        lock.release()
