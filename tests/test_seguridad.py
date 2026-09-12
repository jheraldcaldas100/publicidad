import pytest

from seguridad import sanitizar


def test_sanitizar_none_devuelve_string_vacio():
    assert sanitizar(None) == ""


@pytest.mark.parametrize("texto", [
    "FAL_KEY=sk-abcdefghijklmnopqrstuvwxyz123456",
    "DB_PASSWORD=hunter2hunter2hunter2longenough",
    "GOOGLE_API_TOKEN=abcdefghijklmnopqrstuvwxyz0123456789",
])
def test_sanitizar_redacta_variables_de_entorno_con_guion_bajo(texto):
    """Regresion real: '_' cuenta como caracter de palabra en regex, asi
    que \\b no crea un limite entre '_' y 'KEY' en 'FAL_KEY=...' - el
    patron mas comun de nombre de variable de entorno en este proyecto
    pasaba completamente sin redactar antes de este fix."""
    resultado = sanitizar(texto)
    assert "abcdefghijklmnopqrstuvwxyz" not in resultado.lower() or "0123456789" not in resultado
    assert "[valor redactado]" in resultado


@pytest.mark.parametrize("texto", [
    "monkey business, no turkey here",
    "hockey and jockey are both words",
])
def test_sanitizar_no_falsos_positivos_en_palabras_que_contienen_key(texto):
    assert sanitizar(texto) == texto


def test_sanitizar_redacta_header_de_autorizacion():
    resultado = sanitizar("Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz")
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in resultado
    assert "[header redactado]" in resultado


def test_sanitizar_redacta_urls():
    resultado = sanitizar("fallo en https://api.example.com/v1/secret?token=abc")
    assert "https://" not in resultado
    assert "[URL redactada]" in resultado


def test_sanitizar_acepta_excepcion_como_entrada():
    try:
        raise ValueError("FAL_KEY=sk-abcdefghijklmnopqrstuvwxyz123456")
    except ValueError as exc:
        resultado = sanitizar(exc)
        assert "abcdefghijklmnopqrstuvwxyz123456" not in resultado
