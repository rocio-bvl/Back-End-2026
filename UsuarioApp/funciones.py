"""Funciones de apoyo que usan las views de todas las apps."""
from django.contrib import messages
from django.shortcuts import redirect

from AuditoriaApp.registro import registrar_auditoria
from UsuarioApp.models import Delegacion

from functools import wraps
from django.contrib.auth.decorators import login_required


def limpiar_rut(rut):
    rut = rut.replace('.', '').replace(' ', '').upper()
    if '-' not in rut and len(rut) > 1:
        rut = rut[:-1] + '-' + rut[-1]
    return rut


def validar_rut(rut):
    rut = limpiar_rut(rut)
    if '-' not in rut:
        return False
    numero, dv = rut.split('-')
    if not numero.isdigit() or len(dv) != 1:
        return False
    suma = 0
    multiplicador = 2
    for digito in reversed(numero):
        suma = suma + int(digito) * multiplicador
        multiplicador = multiplicador + 1
        if multiplicador > 7:
            multiplicador = 2
    resto = 11 - (suma % 11)
    if resto == 11:
        esperado = '0'
    elif resto == 10:
        esperado = 'K'
    else:
        esperado = str(resto)
    return dv == esperado


def delegacion_seleccionada(request):
    usuario = request.user
    if usuario.tiene_rol(['Admin', 'Coordinador']):
        codigo = request.GET.get('delegacion', 'GENERAL')
    elif usuario.delegacion:
        codigo = usuario.delegacion.nombre
    else:
        codigo = 'GENERAL'

    delegacion = Delegacion.objects.filter(nombre=codigo).first()
    if delegacion is None:
        return 'GENERAL', None, 'General'
    return codigo, delegacion, str(delegacion)


def acceso_denegado(request, pantalla):
    registrar_auditoria(request.user, 'ACCESO_DENEGADO', 'Vista', request.path[:50],
                        '', f"Intento de acceso a {pantalla}")
    messages.error(request, f"No tienes permisos para acceder a {pantalla}.")
    return redirect('actividades:mi_gestion')

def permiso_requerido(permiso, pantalla):
    """Pide sesión y el permiso de Django (ej. 'IndicadoresApp.view_metadesempeno').
    Sin sesión manda al login; sin permiso, lo anota en auditoría y vuelve a Mi Gestión."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.has_perm(permiso):
                return acceso_denegado(request, pantalla)
            return vista(request, *args, **kwargs)
        return login_required(envoltura)
    return decorador


def opciones_delegacion():
    """Opciones de los <select> de delegación: 'GENERAL' (toda la municipalidad) y las delegaciones activas.
    Se arma desde la base de datos porque el Administrador agrega y edita delegaciones en Gestión."""
    opciones = [('GENERAL', 'General (Toda la Municipalidad)')]
    for delegacion in Delegacion.objects.filter(estado='ACTIVO').order_by('nombre_visible'):
        opciones.append((delegacion.nombre, str(delegacion)))
    return opciones
