"""Vistas JSON del chatbot.

Responden JSON (no HTML), así que no usan permiso_requerido: el control de sesión es
@login_required y el de rol un guard explícito que deja el intento en la auditoría.

Fase 2: cada pregunta pasa por guardrails (inyección, rate limit), contexto RAG (documentos +
datos filtrados por rol), caché estrictamente por usuario y observabilidad completa en
EventoChatbot y en el logger `chatbot`.
"""
import hashlib
import json
import logging
import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from AuditoriaApp.registro import registrar_auditoria
from ChatbotApp.cliente_ia import (
    ErrorProveedorIA, MENSAJE_ERROR, PROMPT_SISTEMA, preparar_mensajes, responder_detallado,
)
from ChatbotApp.guardrails import (
    MENSAJE_INYECCION, detectar_inyeccion, sanear_salida, verificar_rate_limit,
)
from ChatbotApp.models import EventoChatbot, MensajeChat
from ChatbotApp.rag import construir_contexto, normalizar

logger = logging.getLogger('chatbot')

# Alias compatible con la Fase 1: las pruebas y cualquier código que parchee `views.responder`
# siguen funcionando; la vista acepta tanto un texto como el dict de `responder_detallado()`.
responder = responder_detallado

MENSAJE_SIN_PERMISO = "No tienes permisos para usar el asistente."
MENSAJE_SIN_TEXTO = "Escriba una pregunta para el asistente."
MENSAJE_INVALIDO = "No se pudo leer el mensaje enviado."
MENSAJE_INACTIVO = "El asistente no está disponible en este momento. Intente más tarde."
MENSAJE_LIMITE = "Has alcanzado el límite de consultas al asistente. Intenta nuevamente más tarde."


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


def _modelo_para_cache():
    """Modelo real que usará el cliente (API si hay clave y modelo; si no, el local)."""
    if settings.CHATBOT_API_KEY and settings.CHATBOT_MODEL:
        return settings.CHATBOT_MODEL
    return settings.CHATBOT_LOCAL_MODEL


def _origen_configurado():
    """Origen esperado según la configuración, útil cuando el proveedor falla."""
    if settings.CHATBOT_API_KEY and settings.CHATBOT_MODEL:
        return 'API'
    return 'LOCAL' if settings.CHATBOT_LOCAL_MODEL else ''


def _clave_cache(usuario, pregunta, contexto):
    """Clave estrictamente por usuario: nunca se comparte entre usuarios ni entre roles."""
    base = '|'.join([
        normalizar(pregunta),
        contexto,
        settings.CHATBOT_PROMPT_VERSION,
        _modelo_para_cache(),
    ])
    return f"chatbot:respuesta:{usuario.pk}:{hashlib.sha256(base.encode('utf-8')).hexdigest()}"


def _crear_evento(request, **datos):
    evento = EventoChatbot(
        usuario=request.user,
        pregunta=datos.get('pregunta', ''),
        respuesta=datos.get('respuesta', ''),
        prompt_sistema=datos.get('prompt_sistema', ''),
        contexto=datos.get('contexto', ''),
        mensajes_enviados=datos.get('mensajes_enviados') or [],
        modelo=datos.get('modelo', ''),
        origen=datos.get('origen', ''),
        prompt_version=settings.CHATBOT_PROMPT_VERSION,
        duracion_ms=datos.get('duracion_ms'),
        tokens_prompt=datos.get('tokens_prompt'),
        tokens_respuesta=datos.get('tokens_respuesta'),
        cache_hit=datos.get('cache_hit', False),
        documentos_rag=datos.get('documentos_rag') or [],
        guardrail=datos.get('guardrail', ''),
        error=datos.get('error', '')[:2000],
    )
    evento.save()
    return evento


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

    pregunta = mensaje.strip()
    historial = contexto_para_el_proveedor(request.user)
    inicio = time.perf_counter()

    # 1) Anti prompt-injection: respuesta canónica sin llamar al proveedor.
    if detectar_inyeccion(pregunta):
        MensajeChat.objects.create(usuario=request.user, emisor='USUARIO', contenido=pregunta)
        guardado = MensajeChat.objects.create(usuario=request.user, emisor='ASISTENTE',
                                              contenido=MENSAJE_INYECCION)
        _crear_evento(
            request, pregunta=pregunta, respuesta=MENSAJE_INYECCION,
            prompt_sistema=PROMPT_SISTEMA, modelo=_modelo_para_cache(),
            duracion_ms=int((time.perf_counter() - inicio) * 1000), guardrail='INYECCION',
        )
        logger.warning("chatbot guardrail=INYECCION usuario=%s", request.user.pk)
        return JsonResponse({'respuesta': MENSAJE_INYECCION, 'fecha': guardado.fecha.isoformat()})

    # 2) Rate limit por usuario (cache.add/incr).
    if not verificar_rate_limit(request.user):
        _crear_evento(
            request, pregunta=pregunta, modelo=_modelo_para_cache(),
            duracion_ms=int((time.perf_counter() - inicio) * 1000), guardrail='RATE_LIMIT',
        )
        logger.warning("chatbot guardrail=RATE_LIMIT usuario=%s", request.user.pk)
        return JsonResponse({'error': MENSAJE_LIMITE}, status=429)

    # 3) Contexto RAG: documentos internos + datos del SGR según el alcance del rol.
    contexto, documentos, errores_rag = construir_contexto(pregunta, request.user)
    error_rag = '; '.join(errores_rag)[:500]

    # 4) Caché estrictamente por usuario.
    clave = _clave_cache(request.user, pregunta, contexto)
    cacheado = cache.get(clave)

    if cacheado:
        texto = sanear_salida(cacheado.get('respuesta', ''))
        guardrail = 'SANEO_SALIDA' if texto != cacheado.get('respuesta', '') else ''
        MensajeChat.objects.create(usuario=request.user, emisor='USUARIO', contenido=pregunta)
        guardado = MensajeChat.objects.create(usuario=request.user, emisor='ASISTENTE', contenido=texto)
        _crear_evento(
            request, pregunta=pregunta, respuesta=texto, prompt_sistema=PROMPT_SISTEMA,
            contexto=contexto, mensajes_enviados=[],
            modelo=cacheado.get('modelo', _modelo_para_cache()), origen='CACHE',
            duracion_ms=int((time.perf_counter() - inicio) * 1000),
            cache_hit=True, documentos_rag=documentos, guardrail=guardrail, error=error_rag,
        )
        logger.info(
            "chatbot usuario=%s origen=CACHE cache_hit=True duracion_ms=%s docs=%s guardrail=%s",
            request.user.pk, int((time.perf_counter() - inicio) * 1000), len(documentos), guardrail or '-',
        )
        return JsonResponse({'respuesta': texto, 'fecha': guardado.fecha.isoformat()})

    # 5) Miss: preguntar al proveedor con prompt endurecido + contexto RAG.
    mensajes = (
        [{'role': 'system', 'content': 'CONTEXTO DEL SGR (úsalo como única fuente de datos):\n' + contexto}]
        + historial
        + [{'role': 'user', 'content': pregunta}]
    )
    # Los mensajes que realmente recibe el proveedor: system único (prompt + contexto) + historial.
    mensajes_completos = preparar_mensajes(mensajes)

    # La pregunta queda guardada aunque el proveedor falle: es parte del historial del usuario.
    MensajeChat.objects.create(usuario=request.user, emisor='USUARIO', contenido=pregunta)

    try:
        resultado = responder(mensajes)
    except ErrorProveedorIA:
        _crear_evento(
            request, pregunta=pregunta, prompt_sistema=PROMPT_SISTEMA, contexto=contexto,
            mensajes_enviados=mensajes_completos, modelo=_modelo_para_cache(),
            origen=_origen_configurado(),
            duracion_ms=int((time.perf_counter() - inicio) * 1000),
            documentos_rag=documentos, error=('ErrorProveedorIA' + (f'; RAG: {error_rag}' if error_rag else '')),
        )
        logger.warning("chatbot usuario=%s error=ErrorProveedorIA origen=%s", request.user.pk,
                       _origen_configurado() or 'desconocido')
        return JsonResponse({'error': MENSAJE_ERROR}, status=502)

    if isinstance(resultado, dict):
        detalle = resultado
    else:  # compatibilidad con pruebas/parches que devuelven solo el texto
        detalle = {
            'texto': str(resultado),
            'modelo': _modelo_para_cache(),
            'origen': _origen_configurado(),
            'tokens_prompt': None,
            'tokens_respuesta': None,
            'duracion_ms': int((time.perf_counter() - inicio) * 1000),
        }
    texto = sanear_salida(detalle.get('texto', ''))
    guardrail = 'SANEO_SALIDA' if texto != detalle.get('texto', '') else ''

    cache.set(clave, {'respuesta': texto, 'modelo': detalle.get('modelo', _modelo_para_cache())},
              timeout=settings.CHATBOT_CACHE_TTL)
    guardado = MensajeChat.objects.create(usuario=request.user, emisor='ASISTENTE', contenido=texto)
    _crear_evento(
        request, pregunta=pregunta, respuesta=texto, prompt_sistema=PROMPT_SISTEMA,
        contexto=contexto, mensajes_enviados=mensajes_completos, modelo=detalle.get('modelo', _modelo_para_cache()),
        origen=detalle.get('origen', _origen_configurado()), duracion_ms=detalle.get('duracion_ms'),
        tokens_prompt=detalle.get('tokens_prompt'), tokens_respuesta=detalle.get('tokens_respuesta'),
        cache_hit=False, documentos_rag=documentos, guardrail=guardrail, error=error_rag,
    )
    logger.info(
        "chatbot usuario=%s origen=%s modelo=%s cache_hit=False duracion_ms=%s tokens=%s/%s "
        "docs=%s guardrail=%s",
        request.user.pk, detalle.get('origen', _origen_configurado()), detalle.get('modelo', _modelo_para_cache()),
        detalle.get('duracion_ms'), detalle.get('tokens_prompt'), detalle.get('tokens_respuesta'),
        len(documentos), guardrail or '-',
    )
    return JsonResponse({'respuesta': texto, 'fecha': guardado.fecha.isoformat()})


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
