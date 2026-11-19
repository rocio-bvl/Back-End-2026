"""Entrega protegida de los archivos subidos (OWASP A01).

Antes /media/ se servía a cualquiera que tuviera la dirección. Ahora:
- sin sesión, se redirige al login;
- una fotografía de evidencia solo la ve quien puede ver esa actividad (puede_ver_actividad);
- las fotos de perfil, cualquier usuario con sesión (aparecen en la barra y en Mi Gestión).
En producción, Nginx no debe servir /media/ directamente: debe pasar la petición a Django.
"""
import mimetypes
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.utils._os import safe_join

from ActividadesApp.models import Evidencia
from UsuarioApp.funciones import acceso_denegado


@login_required
def archivo_protegido(request, ruta):
    try:
        completa = safe_join(settings.MEDIA_ROOT, ruta)  # impide salir de MEDIA_ROOT con ../
    except Exception:
        raise Http404
    if not os.path.isfile(completa):
        raise Http404

    if ruta.startswith('evidencias/'):
        from ActividadesApp.views import puede_ver_actividad
        evidencia = Evidencia.objects.filter(imagen=ruta).select_related('actividad', 'actividad__usuario').first()
        if evidencia is None:
            raise Http404
        if not puede_ver_actividad(request.user, evidencia.actividad):
            return acceso_denegado(request, 'Fotografía de evidencia')
    elif not ruta.startswith('perfiles/'):
        raise Http404

    tipo = mimetypes.guess_type(completa)[0] or 'application/octet-stream'
    respuesta = FileResponse(open(completa, 'rb'), content_type=tipo)
    respuesta['X-Content-Type-Options'] = 'nosniff'
    respuesta['Cache-Control'] = 'private, max-age=300'
    return respuesta
