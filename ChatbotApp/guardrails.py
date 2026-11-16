"""Guardrails del chatbot: anti prompt-injection, rate limit y saneamiento de salida.

Todo es stdlib + Django. Los patrones son conservadores: exigen frases imperativas para no
bloquear preguntas legítimas como "¿qué es prompt injection?".
"""
import re
import time

from django.conf import settings
from django.core.cache import cache

from ChatbotApp.rag import normalizar

MENSAJE_INYECCION = ("No puedo ayudar con esa solicitud. Puedo responder preguntas sobre el uso "
                     "del SGR y sus datos.")

# Frases imperativas típicas de un intento de manipular al asistente. Se evalúan sobre el texto
# normalizado (minúsculas, sin tildes), por eso no llevan acentos.
PATRONES_INYECCION = [
    r'\bignora (todas |las )?(tus |las )?(instrucciones|reglas|indicaciones)\b',
    r'\bignora (lo|todo lo) anterior\b',
    r'\bolvida (todo |lo )?(anterior|lo que te dijeron)\b',
    r'\b(revela|muestra|dime|entrega|comparte|imprime|escribe|repite)\b.{0,40}'
    r'\b(tu prompt|tus instrucciones|system prompt|la clave|la api key|tu clave|'
    r'la contrasena del sistema|tus reglas internas)\b',
    r'\bque dice (tu|el) (prompt|system prompt)\b',
    r'\bactua (sin|como si no tuvieras) (restricciones|limites|reglas)\b',
    r'\b(modo desarrollador|modo dios|jailbreak|dan mode)\b',
    r'\bpretende (que )?(no )?(hay|tienes) restricciones\b',
    r'\b(ahora|desde ahora) (eres|seras) (un|una) [a-z]+ sin restricciones\b',
]


def detectar_inyeccion(texto):
    """True si el texto parece un intento de prompt injection (imperativo claro)."""
    limpio = normalizar(texto)
    if not limpio:
        return False
    return any(re.search(patron, limpio) for patron in PATRONES_INYECCION)


def verificar_rate_limit(usuario):
    """True si el usuario puede consultar; False si excedió el límite de la ventana actual.

    Ventana fija por usuario: clave `chatbot:rate:{id}:{indice_ventana}`. LocMemCache es por
    proceso (ver docs/chatbot.md).
    """
    limite = settings.CHATBOT_RATE_LIMIT
    if not limite or limite <= 0:
        return True
    ventana = max(1, settings.CHATBOT_RATE_VENTANA)
    indice = int(time.time() // ventana)
    clave = f"chatbot:rate:{usuario.pk}:{indice}"
    if cache.add(clave, 1, timeout=ventana):
        return True
    try:
        usadas = cache.incr(clave)
    except ValueError:  # la entrada expiró entre add e incr
        cache.set(clave, 1, timeout=ventana)
        return True
    return usadas <= limite


_PATRONES_SECRETO = [
    re.compile(r'sk-[A-Za-z0-9_\-]{8,}'),
    re.compile(r'AIza[0-9A-Za-z_\-]{20,}'),
    re.compile(r'Bearer\s+[A-Za-z0-9._~+/=\-]{8,}', re.IGNORECASE),
    re.compile(r'(?:mysql|mariadb|postgres(?:ql)?|mongodb(?:\+srv)?)://[^\s"\']+', re.IGNORECASE),
    re.compile(r'(?:CHATBOT_API_KEY|DB_PASSWORD|SECRET_KEY)\s*[=:]\s*\S+', re.IGNORECASE),
]
REEMPLAZO_SENSIBLE = '[dato sensible omitido]'


def sanear_salida(texto):
    """Quita posibles secretos y trunca la respuesta al máximo configurado."""
    limpio = str(texto or '')
    clave = getattr(settings, 'CHATBOT_API_KEY', '')
    if clave:
        limpio = limpio.replace(clave, REEMPLAZO_SENSIBLE)
    for patron in _PATRONES_SECRETO:
        limpio = patron.sub(REEMPLAZO_SENSIBLE, limpio)
    maximo = settings.CHATBOT_MAX_RESPUESTA
    if maximo and len(limpio) > maximo:
        limpio = limpio[:maximo].rstrip()
    return limpio
