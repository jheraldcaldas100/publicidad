"""
Backup de output/gorrolandia.db - API de backup de sqlite3 (segura sobre una
base viva, a diferencia de una copia cruda de archivo que puede capturar un
WAL/journal a medias), con verificacion de integridad y poda de backups
viejos.

Fuente unica de esta logica - fase8_backfill_historico.py la importa en vez
de duplicarla. Pensado para correrse solo (manual) o programado (ver
scripts/backup_diario.ps1, Tarea Programada diaria).
"""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import db

RETENCION_DIAS = 30


def hacer_backup() -> Path:
    origen_path = db.DB_PATH.resolve()
    carpeta_backups = origen_path.parent / "backups"
    destino_path = carpeta_backups / f"{origen_path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}"

    if not origen_path.is_file():
        sys.exit(f"[backup] no existe la base de datos en {origen_path} - nada que respaldar")
    carpeta_backups.mkdir(parents=True, exist_ok=True)
    if destino_path.exists():
        sys.exit("[backup] ya existe un backup con ese nombre - resolver antes de continuar")

    origen = None
    destino = None
    exito = False
    try:
        origen = sqlite3.connect(origen_path)
        destino = sqlite3.connect(destino_path)
        origen.backup(destino)
        resultado = destino.execute("PRAGMA integrity_check").fetchone()[0]
        if resultado != "ok":
            raise RuntimeError(f"backup corrupto: {resultado}")
        exito = True
    finally:
        if origen is not None:
            origen.close()
        if destino is not None:
            destino.close()
        if not exito:
            destino_path.unlink(missing_ok=True)

    print(f"[backup] Backup creado en: {destino_path}")
    return destino_path


def podar_backups_viejos(retencion_dias: int = RETENCION_DIAS) -> None:
    """Elimina backups (de este mismo script o del backfill, mismo patron de
    nombre) con mas de retencion_dias - nunca toca nada que no matchee
    exactamente el patron esperado."""
    carpeta_backups = db.DB_PATH.resolve().parent / "backups"
    if not carpeta_backups.is_dir():
        return

    limite = datetime.now() - timedelta(days=retencion_dias)
    prefijo = f"{db.DB_PATH.name}.bak-"
    for archivo in carpeta_backups.glob(f"{prefijo}*"):
        timestamp_str = archivo.name[len(prefijo):]
        try:
            fecha = datetime.strptime(timestamp_str, "%Y%m%d-%H%M%S")
        except ValueError:
            continue  # nombre inesperado - no se toca, mejor un backup de mas que borrar algo por error
        if fecha < limite:
            archivo.unlink()
            print(f"[backup] Eliminado backup viejo (> {retencion_dias} dias): {archivo.name}")


def main():
    hacer_backup()
    podar_backups_viejos()


if __name__ == "__main__":
    main()
