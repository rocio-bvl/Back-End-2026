"""Cliente del proveedor de IA del SGR.

Se implementa SOLO con la biblioteca estándar (urllib + json): no se agregan dependencias al
proyecto y el cliente queda agnóstico del proveedor, porque habla la API "OpenAI Chat Completions"
que también exponen OpenRouter, Groq, Ollama y otros. La ApiKey vive en el `.env` y se usa únicamente
en el servidor: nunca se envía al navegador ni se escribe en un mensaje de error. Si no hay un modelo
de API configurado, se usa el modelo local (Ollama) definido también en el `.env`.
"""
import json
import urllib.error
import urllib.request

from django.conf import settings

# Identidad del asistente. Se envía como primer mensaje de la conversación.
PROMPT_SISTEMA = (
    "Eres el asistente virtual del SGR (Sistema de Gestión de Resultados) de la Ilustre "
    "Municipalidad de La Serena. Respondes siempre en español, de forma breve, clara y respetuosa. "
    "Ayudas a las personas usuarias a entender y usar el sistema: actividades y evidencias, "
    "validación, metas, delegaciones, atenciones sociales, usuarios y auditoría. Si no sabes algo, "
    "dilo con honestidad y sugiere consultar a un administrador del sistema. No inventes datos "
    "personales, credenciales ni información interna."
)

# Mensaje único y seguro: se muestra al usuario y nunca incluye la clave ni la respuesta del proveedor.
MENSAJE_ERROR = "El asistente no está disponible en este momento. Intente más tarde."


class ErrorProveedorIA(Exception):
    """Falla al comunicarse con el proveedor de IA (red, timeout, credenciales o respuesta
    malformada). Siempre se lanza con un mensaje genérico."""


def _configuracion_proveedor():
    """Devuelve (url, modelo, clave, timeout, extra) del proveedor a usar.

    Prioridad: la API remota cuando hay clave y modelo configurados; si no, el modelo local
    (Ollama u otro compatible con OpenAI Chat Completions) definido en el `.env`. Si no hay
    ninguna de las dos cosas, lanza ErrorProveedorIA sin hacer ninguna petición.
    """
    clave = getattr(settings, 'CHATBOT_API_KEY', '')
    modelo = getattr(settings, 'CHATBOT_MODEL', '')
    if clave and modelo:
        return (settings.CHATBOT_API_URL, modelo, clave, settings.CHATBOT_TIMEOUT, {})

    modelo_local = getattr(settings, 'CHATBOT_LOCAL_MODEL', '')
    if modelo_local:
        # Ollama ignora la clave: la petición local no lleva Authorization. Los modelos locales de
        # razonamiento devuelven el texto en 'reasoning' si no se les pide expresamente lo contrario.
        extra = {}
        esfuerzo = getattr(settings, 'CHATBOT_LOCAL_REASONING_EFFORT', '')
        if esfuerzo:
            extra['reasoning_effort'] = esfuerzo
        return (settings.CHATBOT_LOCAL_API_URL, modelo_local, '',
                getattr(settings, 'CHATBOT_LOCAL_TIMEOUT', 120), extra)

    raise ErrorProveedorIA(MENSAJE_ERROR)


def responder(mensajes):
    """Envía la conversación al proveedor configurado y devuelve el texto de la respuesta.

    `mensajes` es una lista de diccionarios con 'role' ('user' o 'assistant') y 'content'.
    Usa la API remota si hay clave y modelo; si no, el modelo local del `.env` (Ollama).
    Lanza ErrorProveedorIA ante cualquier problema: HTTPError, URLError, timeout, JSON inválido o
    una estructura de respuesta inesperada.
    """
    url, modelo, clave, timeout, extra = _configuracion_proveedor()

    cuerpo = {
        'model': modelo,
        'messages': [{'role': 'system', 'content': PROMPT_SISTEMA}] + list(mensajes or []),
        'temperature': 0.3,
        'max_tokens': 600,
    }
    cuerpo.update(extra)
    cabeceras = {'Content-Type': 'application/json'}
    if clave:
        cabeceras['Authorization'] = f"Bearer {clave}"
    peticion = urllib.request.Request(
        url,
        data=json.dumps(cuerpo).encode('utf-8'),
        headers=cabeceras,
        method='POST',
    )

    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            datos = json.loads(respuesta.read().decode('utf-8'))
        contenido = datos['choices'][0]['message']['content']
        if not isinstance(contenido, str) or not contenido.strip():
            raise ErrorProveedorIA(MENSAJE_ERROR)
        return contenido.strip()
    except ErrorProveedorIA:
        raise
    except urllib.error.HTTPError:
        # Credenciales inválidas, cuota, modelo inexistente...: no se propaga el detalle del proveedor
        raise ErrorProveedorIA(MENSAJE_ERROR) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        # Red caída, DNS, certificado o timeout de la conexión
        raise ErrorProveedorIA(MENSAJE_ERROR) from None
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError, IndexError, TypeError, ValueError):
        # Respuesta malformada o con otra estructura
        raise ErrorProveedorIA(MENSAJE_ERROR) from None
