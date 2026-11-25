"""Cambio obligatorio de la contraseña temporal en el primer ingreso (settings.CONTRASENA_TEMPORAL).

Mientras el usuario tenga debe_cambiar_clave=True, cualquier pantalla lo lleva a "Cambiar contraseña". Solo quedan
libres esa pantalla, cerrar sesión y los archivos estáticos. Con CONTRASENA_TEMPORAL=False no hace nada.
"""
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class CambioClaveObligatorioMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, 'user', None)
        if (settings.CONTRASENA_TEMPORAL and usuario is not None and usuario.is_authenticated
                and usuario.debe_cambiar_clave):
            libres = (reverse('users:cambiar_clave'), reverse('users:logout'), '/' + settings.STATIC_URL.lstrip('/'))
            if not request.path.startswith(libres):
                return redirect('users:cambiar_clave')
        return self.get_response(request)
