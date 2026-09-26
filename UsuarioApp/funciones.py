"""Funciones de apoyo que usan las views de todas las apps."""
from django.contrib import messages
from django.shortcuts import redirect

from AuditoriaApp.registro import registrar_auditoria
from UsuarioApp.models import Delegacion


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
