"""Vistas JSON del chatbot.

Responden JSON (no HTML), así que no usan permiso_requerido: el control de sesión es
@login_required y el de rol un guard explícito que deja el intento en la auditoría.
"""
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from AuditoriaApp.registro import registrar_auditoria
from ChatbotApp.cliente_ia import ErrorProveedorIA, MENSAJE_ERROR, responder
from ChatbotApp.models import MensajeChat

MENSAJE_SIN_PERMISO = "No tienes permisos para usar el asistente."
MENSAJE_SIN_TEXTO = "Escriba una pregunta para el asistente."
MENSAJE_INVALIDO = "No se pudo leer el mensaje enviado."
MENSAJE_INACTIVO = "El asistente no está disponible en este momento. Intente más tarde."


def usuario_habilitado(usuario):
    """Admin, Coordinador, Delegado y superusuario. El Funcionario no usa el asistente."""
    return usuario.is_superuser or usuario.puede_usar_chatbot()


def respuesta_sin_permiso(request):
    registrar_auditoria(request.user, 'ACCESO_DENEGADO', 'Chatbot', request.path[:50],
                        '', 'Intento de uso del chatbot')
    return JsonResponse({'error': MENSAJE_SIN_PERMISO}, status=403)


def contexto_para_el_proveedor(usuario):
    """Últimos CHATBOT_MAX_HISTORIAL mensajes del usuario, en orden cronológico y con los roles
    que entiende la API (USUARIO -> user, ASISTENTE -> assistant)."""
    ultimos = list(MensajeChat.objects.filter(usuario=usuario).order_by('-fecha', '-id')[:settings.CHATBOT_MAX_HISTORIAL])
    ultimos.reverse()
    return [{'role': 'assistant' if mensaje.emisor == 'ASISTENTE' else 'user',
             'content': mensaje.contenido} for mensaje in ultimos]


def mensaje_a_json(mensaje):
    return {
        'emisor': mensaje.emisor,
        'contenido': mensaje.contenido,
        'fecha': mensaje.fecha.isoformat(),
    }


@login_required
@require_POST
def chat_mensaje(request):
    if not usuario_habilitado(request.user):
        return respuesta_sin_permiso(request)

    try:
        datos = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': MENSAJE_INVALIDO}, status=400)
    if not isinstance(datos, dict):
        return JsonResponse({'error': MENSAJE_INVALIDO}, status=400)

    mensaje = datos.get('mensaje')
    if not isinstance(mensaje, str) or not mensaje.strip():
        return JsonResponse({'error': MENSAJE_SIN_TEXTO}, status=400)
    if len(mensaje) > settings.CHATBOT_MAX_MENSAJE:
        return JsonResponse({
            'error': f"El mensaje no puede superar los {settings.CHATBOT_MAX_MENSAJE} caracteres."
        }, status=400)

    if not settings.CHATBOT_ACTIVO:
        return JsonResponse({'error': MENSAJE_INACTIVO}, status=503)

    # La pregunta queda guardada aunque el proveedor falle: es parte del historial del usuario
    MensajeChat.objects.create(usuario=request.user, emisor='USUARIO', contenido=mensaje.strip())

    try:
        respuesta = responder(contexto_para_el_proveedor(request.user))
    except ErrorProveedorIA:
        # No se guarda una respuesta del asistente cuando el proveedor falla
        return JsonResponse({'error': MENSAJE_ERROR}, status=502)

    guardado = MensajeChat.objects.create(usuario=request.user, emisor='ASISTENTE', contenido=respuesta)
    return JsonResponse({'respuesta': respuesta, 'fecha': guardado.fecha.isoformat()})


@login_required
@require_GET
def chat_historial(request):
    if not usuario_habilitado(request.user):
        return respuesta_sin_permiso(request)

    ultimos = list(MensajeChat.objects.filter(usuario=request.user).order_by('-fecha', '-id')[:50])
    ultimos.reverse()
    return JsonResponse({'mensajes': [mensaje_a_json(mensaje) for mensaje in ultimos]})


@login_required
@require_POST
def chat_limpiar(request):
    if not usuario_habilitado(request.user):
        return respuesta_sin_permiso(request)

    MensajeChat.objects.filter(usuario=request.user).delete()
    return JsonResponse({'ok': True})
