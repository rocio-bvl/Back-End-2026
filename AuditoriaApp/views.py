from django.core.paginator import Paginator
from django.shortcuts import render, redirect

from AuditoriaApp.models import Auditoria
from UsuarioApp.funciones import acceso_denegado


def logs(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin']):
        return acceso_denegado(request, 'Auditoría')

    registros = Auditoria.objects.select_related('usuario').all()
    paginador = Paginator(registros, 25)
    page_obj = paginador.get_page(request.GET.get('page'))

    data = {
        'logs_auditoria': page_obj,
        'page_obj': page_obj,
        'is_paginated': paginador.num_pages > 1,
    }
    return render(request, 'auditoria/logs.html', data)
