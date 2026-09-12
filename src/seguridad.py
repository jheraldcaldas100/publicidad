"""
Redaccion de secretos, compartida entre persistencia en base de datos,
panel, y consola/logs del worker - un solo lugar, para que agregar un patron
nuevo de secreto lo cubra en los tres a la vez.
"""
import re

_RE_URL = re.compile(r"https?://\S+")
# corrige bug real (encontrado escribiendo la prueba de regresion de esta
# misma sesion): la version anterior solo consumia UNA palabra despues de
# "Authorization:" - en "Authorization: Bearer sk-..." (el formato estandar
# de header HTTP, el mas realista de encontrar en un log real), la version
# vieja se comia solo "Bearer" y dejaba el token real completamente
# visible justo despues del "[header redactado]".
_RE_AUTH_HEADER = re.compile(
    r"Authorization\s*:?\s*(?:Bearer\s+)?\S+|Bearer\s+\S+", re.IGNORECASE
)
# (?<![A-Za-z]) en vez de \b antes de la palabra clave - corrige bug real:
# "_" cuenta como caracter de palabra en regex, asi que \b NO crea un limite
# entre "_" y "K" en "FAL_KEY=..." (el patron mas comun en mensajes de error
# reales de este proyecto: FAL_KEY, GOOGLE_..., etc.) - con \b, ese caso
# pasaba completamente sin redactar. El lookbehind es de ancho cero, asi que
# el guion bajo antes de la palabra clave nunca se consume ni se borra.
_RE_VALOR_SECRETO = re.compile(
    r"(?<![A-Za-z])(key|token|secret|password|api[_-]?key)\b\s*[:=]?\s*[A-Za-z0-9_\-]{20,}",
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
