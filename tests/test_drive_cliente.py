import pytest

from fase8_drive_cliente import ArchivoRechazado, _sanear_nombre_archivo, derivar_sku, derivar_sku_o_generar


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


def test_derivar_sku_o_generar_usa_el_nombre_si_ya_es_valido():
    sku, generado = derivar_sku_o_generar("HOMIE-BLK-001.jpg", "1yICmSwdIvo1Tzupl9PtE")
    assert sku == "HOMIE-BLK-001"
    assert generado is False


def test_derivar_sku_o_generar_nunca_rechaza_nombres_de_whatsapp():
    """Regresion real: las fotos reales llegan reenviadas por WhatsApp con
    nombres tipo 'Copia de WhatsApp Image ... (3).jpeg', sin ningun codigo
    de producto - antes esto rechazaba TODAS las fotos reales del negocio."""
    nombre = "Copia de WhatsApp Image 2026-09-03 at 12.35.08 PM (3).jpeg"
    sku, generado = derivar_sku_o_generar(nombre, "1yICmSwdIvo1Tzupl9PtE-nriAEZ7oQB9")
    assert generado is True
    assert sku == "FOTO-1yICmSwdIvo1"  # primeros 12 caracteres del drive_file_id
    # el sku generado debe ser seguro para usarse como componente de ruta
    assert "/" not in sku and "\\" not in sku and " " not in sku


def test_derivar_sku_o_generar_es_deterministico_para_el_mismo_archivo():
    """El mismo drive_file_id siempre produce el mismo sku generado -
    importante para que reintentar un ciclo no cree un sku distinto."""
    nombre = "IMG 1234 (copia).HEIC"  # espacios -> no matchea RE_SKU_VALIDO, fuerza la rama generada
    sku1, generado1 = derivar_sku_o_generar(nombre, "abc123")
    sku2, generado2 = derivar_sku_o_generar(nombre, "abc123")
    assert generado1 is True and generado2 is True
    assert sku1 == sku2
