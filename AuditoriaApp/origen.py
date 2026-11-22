"""Origen de cada evento de auditoría (RNF-008): la IP desde donde se hizo y el canal del sistema.

El middleware guarda la petición en curso para que registrar_auditoria() la encuentre sin tener que recibirla
como parámetro en cada vista. Sin petición (un comando de manage.py, la consola o un script) el evento es
EXTERNO: se hizo fuera de las pantallas del sistema.
"""
import ipaddress
from contextvars import ContextVar

from django.conf import settings

_peticion = ContextVar('peticion_auditoria', default=None)


class OrigenAuditoriaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        marca = _peticion.set(request)
        try:
            return self.get_response(request)
        finally:
            _peticion.reset(marca)


def peticion_actual():
    return _peticion.get()


def ip_de(request):
    """IP del equipo que hizo la petición, o None si no se detecta.
    Detrás de un proxy (Nginx, balanceador de AWS) REMOTE_ADDR es el del proxy: con AUDITORIA_CONFIAR_PROXY=True se
    toma la última IP de X-Forwarded-For, que es la que agregó el proxy propio. No se activa sin proxy, porque
    cualquiera puede escribir ese encabezado y falsear su IP."""
    if request is None:
        return None
    ip = request.META.get('REMOTE_ADDR', '')
    if settings.AUDITORIA_CONFIAR_PROXY:
        reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if reenviada:
            ip = reenviada.split(',')[-1].strip()
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


def canal_de(request):
    if request is None:
        return 'EXTERNO'
    if request.path.startswith('/admin/'):
        return 'ADMIN'
    return 'SGR'
