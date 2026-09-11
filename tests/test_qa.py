import pytest

from fase6_qa_reintento import (
    ErrorEsquemaQA,
    _es_verdadero,
    _parsear_json_estricto,
    _texto_correcciones,
    _validar_esquema,
    calcular_score,
    construir_prompt_reintento,
)

RESPUESTA_OK = {
    "item_1_color": True, "item_2_logo": True, "item_3_parche": True,
    "item_4_rostro": True, "item_5_escena": True, "item_6_angulo": True,
    "item_7_luz": True, "item_8_estructura": True, "problema": "",
}


def test_parseo_json_directo():
    assert _parsear_json_estricto('{"a": 1}') == {"a": 1}


def test_parseo_json_con_texto_extra_alrededor_falla_si_hay_basura_despues():
    with pytest.raises(ErrorEsquemaQA):
        _parsear_json_estricto('{"a": 1} esto no deberia estar aqui')


def test_parseo_json_tolera_cerca_de_markdown_con_json():
    """Regresion real: el modelo de vision casi siempre envuelve el JSON en
    una cerca de codigo markdown pese a que el prompt pide explicitamente
    'sin markdown' - encontrado en la corrida real del backfill (38% de
    falsos qa_error antes de este fix)."""
    texto = '```json\n{"a": 1}\n```'
    assert _parsear_json_estricto(texto) == {"a": 1}


def test_parseo_json_tolera_cerca_de_markdown_sin_json():
    texto = '```\n{"a": 1}\n```'
    assert _parsear_json_estricto(texto) == {"a": 1}


def test_parseo_json_con_cerca_pero_basura_real_dentro_sigue_fallando():
    with pytest.raises(ErrorEsquemaQA):
        _parsear_json_estricto('```json\n{"a": 1} basura real\n```')


def test_parseo_json_tolera_prefijo_antes_de_la_llave():
    # el modelo a veces antepone texto tipo "Here's the JSON:" antes del objeto
    objeto = _parsear_json_estricto('Here is the result:\n{"a": 1}')
    assert objeto == {"a": 1}


def test_parseo_json_sin_objeto_falla():
    with pytest.raises(ErrorEsquemaQA):
        _parsear_json_estricto("no hay json aqui")


def test_validar_esquema_ok():
    _validar_esquema(dict(RESPUESTA_OK))  # no debe lanzar


def test_validar_esquema_falta_clave():
    incompleta = {k: v for k, v in RESPUESTA_OK.items() if k != "item_1_color"}
    with pytest.raises(ErrorEsquemaQA):
        _validar_esquema(incompleta)


@pytest.mark.parametrize("valor", [1, 0, None, [], "si", "verdadero"])
def test_validar_esquema_rechaza_valores_no_booleanos(valor):
    malo = {**RESPUESTA_OK, "item_1_color": valor}
    with pytest.raises(ErrorEsquemaQA):
        _validar_esquema(malo)


@pytest.mark.parametrize("valor", ["true", "TRUE", " True ", "false", "FALSE"])
def test_validar_esquema_acepta_strings_true_false(valor):
    _validar_esquema({**RESPUESTA_OK, "item_1_color": valor})  # no debe lanzar


def test_validar_esquema_problema_muy_largo_es_sospechoso():
    with pytest.raises(ErrorEsquemaQA):
        _validar_esquema({**RESPUESTA_OK, "problema": "x" * 2001})


def test_bug_truthiness_string_false_no_es_true():
    """Regresion del bug real: bool('false') == True en Python puro. Una
    vez que _validar_esquema deja pasar el string 'false' como valor
    valido, _es_verdadero (no bool()) debe normalizarlo a False."""
    assert _es_verdadero("false") is False
    assert _es_verdadero("False") is False
    assert _es_verdadero(" FALSE ") is False
    assert _es_verdadero("true") is True
    assert _es_verdadero(True) is True
    assert _es_verdadero(False) is False


def test_calcular_score_perfecto():
    score, aprobado = calcular_score(RESPUESTA_OK)
    assert score == 100
    assert aprobado is True


def test_calcular_score_string_false_cuenta_como_fallo():
    resultado = {**RESPUESTA_OK, "item_1_color": "false"}
    score, aprobado = calcular_score(resultado)
    assert aprobado is False
    assert score < 100


def test_calcular_score_fallo_critico_limita_a_menos_de_80():
    resultado = dict(RESPUESTA_OK)
    resultado["item_1_color"] = False  # critico
    score, aprobado = calcular_score(resultado)
    assert score <= 79
    assert aprobado is False


def test_calcular_score_fallo_no_critico_puede_seguir_aprobado():
    resultado = dict(RESPUESTA_OK)
    resultado["item_7_luz"] = False  # no critico
    score, aprobado = calcular_score(resultado)
    assert aprobado is True


def test_construir_prompt_reintento_agrega_solo_correcciones_de_items_fallidos():
    resultado = {**RESPUESTA_OK, "item_1_color": False}
    prompt = construir_prompt_reintento("BASE", resultado)
    assert prompt.startswith("BASE")
    assert "COLOR" in prompt
    assert "LOGO" not in prompt  # item_2_logo si paso, no debe agregar su correccion


def test_construir_prompt_reintento_sin_fallos_no_cambia_el_prompt():
    assert construir_prompt_reintento("BASE", RESPUESTA_OK) == "BASE"


def test_construir_prompt_reintento_con_qa_error_no_explota():
    assert construir_prompt_reintento("BASE", {"qa_error": True, "detalle": "x"}) == "BASE"


def test_texto_correcciones_qa_error_vacio():
    assert _texto_correcciones({"qa_error": True, "detalle": "x"}) == ""
