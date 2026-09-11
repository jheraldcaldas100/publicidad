"""
Fixture compartida: cada prueba corre contra un archivo SQLite temporal
propio, nunca contra output/gorrolandia.db real - ninguna prueba
automatizada de este proyecto debe poder tocar la base de produccion ni
gastar dinero real en llamadas a fal.ai/Drive.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


@pytest.fixture
def db_path_temporal(tmp_path, monkeypatch):
    """Como db_temporal, pero SIN llamar inicializar_db() - para pruebas
    que necesitan construir su propio esquema de partida (p.ej. simular la
    base real preexistente antes de la migracion)."""
    ruta = tmp_path / "test_gorrolandia.db"
    monkeypatch.setenv("GORROLANDIA_DB_PATH", str(ruta))

    import db
    monkeypatch.setattr(db, "DB_PATH", ruta)
    return ruta


@pytest.fixture
def db_temporal(tmp_path, monkeypatch):
    """Crea una base SQLite temporal e inicializa su esquema, redirigiendo
    db.DB_PATH (y GORROLANDIA_DB_PATH, para que un subproceso lanzado desde
    dentro de la prueba tambien la use)."""
    ruta = tmp_path / "test_gorrolandia.db"
    monkeypatch.setenv("GORROLANDIA_DB_PATH", str(ruta))

    import db
    monkeypatch.setattr(db, "DB_PATH", ruta)
    db.inicializar_db()
    return ruta


@pytest.fixture
def imagen_valida(tmp_path):
    """Crea y devuelve la ruta a un JPEG minimo pero real (decodifica con
    PIL) - para pruebas que necesitan un archivo de imagen valido sin
    depender de assets del proyecto."""
    from PIL import Image

    def _crear(nombre: str = "img.jpg", tamano=(10, 10)) -> Path:
        ruta = tmp_path / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", tamano).save(ruta)
        return ruta

    return _crear
