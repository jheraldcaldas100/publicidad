import pytest

from fase8_drive_cliente import ArchivoRechazado, _sanear_nombre_archivo, derivar_sku


@pytest.mark.parametrize("nombre,esperado", [
    ("HOMIE-BLK-001.jpg", "HOMIE-BLK-001"),
    ("sku_con_guion_bajo.png", "sku_con_guion_bajo"),
])
def test_derivar_sku_valido(nombre, esperado):
    assert derivar_sku(nombre) == esperado


@pytest.mark.parametrize("nombre", [
    "CON.jpg", "con.jpg", "NUL.png", "LPT1.jpg",  # reservados de Windows
    "...jpg", "foo..jpg", ".jpg", "",              # puntos/vacio
    "a b.jpg", "sku con espacio.png",              # espacios
])
def test_derivar_sku_rechaza_nombres_invalidos(nombre):
    with pytest.raises(ArchivoRechazado):
        derivar_sku(nombre)


@pytest.mark.parametrize("nombre", [
    "sku/../otro.jpg", "../../../etc/passwd.jpg", "a/../../b.jpg",
])
def test_derivar_sku_es_seguro_ante_separadores_de_ruta(nombre):
    """Path(...).stem ya colapsa cualquier '..'/'/' al ultimo componente -
    el sku resultante nunca puede escapar del directorio esperado, aunque
    el nombre de archivo de Drive contenga separadores de ruta."""
    sku = derivar_sku(nombre)
    assert "/" not in sku and "\\" not in sku and ".." not in sku


def test_sanear_nombre_archivo_reemplaza_caracteres_no_seguros():
    assert _sanear_nombre_archivo("a b*c.jpg") == "a_b_c.jpg"
    assert _sanear_nombre_archivo("HOMIE-BLK-001.jpg") == "HOMIE-BLK-001.jpg"
