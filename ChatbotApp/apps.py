from django.apps import AppConfig
from django.conf import settings
from django.core.checks import Warning, register


@register()
def check_chatbot_rate_backend(app_configs, **kwargs):
    """Advierte si el rate limit vuelve a la caché por proceso en un despliegue real.

    Con ``CHATBOT_RATE_BACKEND='cache'`` el contador vive en ``LocMemCache`` y se multiplica por
    cada worker. Es aceptable en desarrollo (``DEBUG=True``), pero en producción el contador debe
    ser compartido (``'db'``).
    """
    if app_configs is not None and not any(
            config.name == 'ChatbotApp' for config in app_configs):
        return []
    backend = getattr(settings, 'CHATBOT_RATE_BACKEND', 'db')
    if backend == 'cache' and not getattr(settings, 'DEBUG', False):
        return [Warning(
            "CHATBOT_RATE_BACKEND='cache' usa LocMemCache por proceso: con varios workers el "
            "límite efectivo se multiplica por el número de procesos.",
            hint="Configure CHATBOT_RATE_BACKEND='db' en producción.",
            id='ChatbotApp.W001',
        )]
    return []


class ChatbotappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ChatbotApp"
    verbose_name = "Chatbot"
