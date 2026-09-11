"""
Redaccion de secretos, compartida entre persistencia en base de datos,
panel, y consola/logs del worker - un solo lugar, para que agregar un patron
nuevo de secreto lo cubra en los tres a la vez.
"""
import re

_RE_URL = re.compile(r"https?://\S+")
_RE_AUTH_HEADER = re.compile(r"(Authorization|Bearer)\s*:?\s*\S+", re.IGNORECASE)
_RE_VALOR_SECRETO = re.compile(
    r"\b(key|token|secret|password|api[_-]?key)\b\s*[:=]?\s*[A-Za-z0-9_\-]{20,}",
    re.IGNORECASE,
)


def sanitizar(texto) -> str:
    """Redacta URLs, headers de autorizacion, y valores largos que aparecen
    junto a palabras como key/token/secret/password. Acepta cualquier valor
    (None, una excepcion, etc.) y siempre devuelve un string."""
    if texto is None:
        return ""
    texto = str(texto)
    texto = _RE_AUTH_HEADER.sub("[header redactado]", texto)
    texto = _RE_VALOR_SECRETO.sub("[valor redactado]", texto)
    texto = _RE_URL.sub("[URL redactada]", texto)
    return texto
