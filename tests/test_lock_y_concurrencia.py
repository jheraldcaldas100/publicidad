"""
Pruebas con subprocesos reales - nunca lanzan el worker completo (que
cargaria credenciales reales de Drive/fal.ai), siempre uno de los ayudantes
minimos en este mismo directorio. GORROLANDIA_DB_PATH/GORROLANDIA_LOCK_PATH
se pasan explicitamente via env= a cada subprocess.Popen, nunca se asume que
un monkeypatch del proceso de pytest los alcanza (no lo hace: un subproceso
en Windows reimporta los modulos desde cero).
"""
import subprocess
import sys
import time
from pathlib import Path

from filelock import FileLock, Timeout

AYUDANTE_LOCK = Path(__file__).resolve().parent / "_ayudante_lock.py"
AYUDANTE_DB = Path(__file__).resolve().parent / "_ayudante_inicializar_db.py"


def _terminar(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def test_instancia_unica_del_lock(tmp_path, monkeypatch):
    ruta_lock = tmp_path / "worker.lock"
    assert ruta_lock.resolve().is_relative_to(tmp_path.resolve())  # nunca la ruta real de produccion
    env = {**__import__("os").environ, "GORROLANDIA_LOCK_PATH": str(ruta_lock)}

    proc = subprocess.Popen(
        [sys.executable, str(AYUDANTE_LOCK)],
        cwd=str(AYUDANTE_LOCK.parent), env=env,
        stdout=subprocess.PIPE, text=True,
    )
    try:
        primera_linea = proc.stdout.readline().strip()
        assert primera_linea == "LOCK_ADQUIRIDO"

        # una segunda adquisicion del mismo lock, desde el proceso de
        # pytest, debe fallar mientras el ayudante lo tiene.
        segundo_lock = FileLock(str(ruta_lock), timeout=0)
        with __import__("pytest").raises(Timeout):
            segundo_lock.acquire()
    finally:
        _terminar(proc)

    # liberado (terminate = cierre ordenado) -> ahora si se puede adquirir
    tercer_lock = FileLock(str(ruta_lock), timeout=2)
    tercer_lock.acquire()
    tercer_lock.release()


def test_lock_se_libera_tras_un_crash_no_un_cierre_ordenado(tmp_path):
    """kill (no terminate) simula un crash real - el sistema operativo debe
    liberar el lock igual, sin importar la causa de la muerte del proceso."""
    ruta_lock = tmp_path / "worker.lock"
    env = {**__import__("os").environ, "GORROLANDIA_LOCK_PATH": str(ruta_lock)}

    proc = subprocess.Popen(
        [sys.executable, str(AYUDANTE_LOCK)],
        cwd=str(AYUDANTE_LOCK.parent), env=env,
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert proc.stdout.readline().strip() == "LOCK_ADQUIRIDO"
        proc.kill()
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            _terminar(proc)

    lock = FileLock(str(ruta_lock), timeout=2)
    lock.acquire()  # no debe lanzar Timeout
    lock.release()


def test_inicializar_db_concurrente_no_lanza_excepcion(tmp_path):
    ruta_db = tmp_path / "concurrente.db"
    assert ruta_db.resolve().is_relative_to(tmp_path.resolve())
    env = {**__import__("os").environ, "GORROLANDIA_DB_PATH": str(ruta_db)}

    procesos = [
        subprocess.Popen([sys.executable, str(AYUDANTE_DB)], cwd=str(AYUDANTE_DB.parent), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    resultados = [p.communicate(timeout=15) for p in procesos]
    for i, (proc, (stdout, stderr)) in enumerate(zip(procesos, resultados)):
        assert proc.returncode == 0, f"proceso {i} fallo: {stderr}"
        assert "INICIALIZADO" in stdout

    import sqlite3
    con = sqlite3.connect(ruta_db)
    columnas = {f[1] for f in con.execute("PRAGMA table_info(generaciones)")}
    con.close()
    assert "trabajo_id" in columnas
