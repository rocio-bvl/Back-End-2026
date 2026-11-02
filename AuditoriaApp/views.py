from django.core.paginator import Paginator
from django.shortcuts import render, redirect

from AuditoriaApp.models import Auditoria
from UsuarioApp.funciones import acceso_denegado, permiso_requerido
from UsuarioApp.models import Usuario


@permiso_requerido('AuditoriaApp.view_auditoria', 'Auditoría')
def logs(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_administrar():
        return acceso_denegado(request, 'Auditoría')

    usuario = request.GET.get('usuario', '')
    evento = request.GET.get('evento', '')
    desde = request.GET.get('desde', '')
    hasta = request.GET.get('hasta', '')

    registros = Auditoria.objects.select_related('usuario').all()

    if usuario:
        registros = registros.filter(usuario_id=usuario)
    if evento:
        registros = registros.filter(evento=evento)
    if desde:
        registros = registros.filter(fecha__date__gte=desde)
    if hasta:
        registros = registros.filter(fecha__date__lte=hasta)

    paginador = Paginator(registros, 25)
    page_obj = paginador.get_page(request.GET.get('page'))

    data = {
        'logs_auditoria': page_obj,
        'page_obj': page_obj,
        'is_paginated': paginador.num_pages > 1,

        'usuarios': Usuario.objects.order_by(
            'first_name',
            'last_name'
        ),

        'usuario_actual': usuario,
        'evento_actual': evento,
        'desde': desde,
        'hasta': hasta,
    }
    return render(request, 'auditoria/logs.html', data)
