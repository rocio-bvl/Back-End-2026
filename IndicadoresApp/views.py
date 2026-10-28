from decimal import Decimal

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import Actividad
from AuditoriaApp.registro import registrar_auditoria
from IndicadoresApp.calculos import seguimiento_usuario
from IndicadoresApp.forms import MetaForm
from IndicadoresApp.models import MetaDesempeno, periodo_vigente, metas_para
from UsuarioApp.funciones import delegacion_seleccionada, acceso_denegado
from UsuarioApp.models import Usuario, Cargo, Catalogo


def usuarios_evaluados(delegacion):
    usuarios = Usuario.objects.filter(is_active=True, cargo__isnull=False).select_related('cargo', 'cargo__area')
    if delegacion is not None:
        usuarios = usuarios.filter(delegacion=delegacion)
    return usuarios


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('users:login')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)

    # Actividades pendientes = compromisos programados y actividades del Tubo (todavía sin ejecutar)
    compromisos = Actividad.objects.filter(estado__in=['PROGRAMADA', 'EN_TUBO'])
    if delegacion is not None:
        compromisos = compromisos.filter(usuario__delegacion=delegacion)

    avance = Decimal('0')
    semaforo = 'Sin periodo vigente'
    if periodo is not None:
        filas = []
        for usuario in usuarios_evaluados(delegacion):
            filas.append(seguimiento_usuario(usuario, periodo, hoy))
        if filas:
            suma = Decimal('0')
            for fila in filas:
                suma = suma + fila['avance_logrado']
            avance = round(suma / len(filas), 1)
        objetivo = periodo.porcentaje_transcurrido(hoy)
        if objetivo > 0:
            color = periodo.calcular_semaforo(avance * 100 / objetivo)
        else:
            color = 'VERDE'
        semaforo = {'VERDE': 'Verde', 'AMBAR': 'Ámbar', 'ROJO': 'Rojo'}[color]

    data = {
        'delegacion_actual': f"Delegación {nombre}",
        'compromisos_pendientes_count': compromisos.count(),
        'avance_periodo_porcentaje': f"{avance}%",
        'semaforo_estado': semaforo,
    }
    return render(request, 'indicadores/dashboard.html', data)


def semaforo(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado']):
        return acceso_denegado(request, 'Semáforo')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)

    seguimiento = []
    dias_transcurridos = 0
    porcentaje_esperado = 0
    if periodo is not None:
        dias_transcurridos = periodo.calcular_dias_transcurridos(hoy)
        porcentaje_esperado = periodo.porcentaje_transcurrido(hoy)
        for usuario in usuarios_evaluados(delegacion):
            seguimiento.append(seguimiento_usuario(usuario, periodo, hoy))
    else:
        messages.warning(request, "No hay un periodo vigente para la fecha de hoy.")

    data = {
        'seguimiento': seguimiento,
        'dias_transcurridos': dias_transcurridos,
        'porcentaje_esperado': porcentaje_esperado,
        'periodo': periodo,
    }
    return render(request, 'indicadores/semaforo.html', data)


def resumen_delegacion(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado']):
        return acceso_denegado(request, 'Resumen de Delegación')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    periodo = periodo_vigente()
    equipo = usuarios_evaluados(delegacion)

    comisiones = []
    if periodo is not None:
        # Una fila por cada meta de cada cargo presente en el equipo
        cargos = Cargo.objects.filter(usuarios__in=equipo).distinct()
        for cargo in cargos:
            integrantes = equipo.filter(cargo=cargo)
            cantidad = integrantes.count()
            for meta in metas_para(cargo.pk, periodo, delegacion.pk if delegacion else None):
                meta_total = meta.valor_objetivo * cantidad
                avance = Actividad.objects.filter(usuario__in=integrantes, item=meta.item, periodo=periodo, estado='VALIDADA').count()
                if meta_total > 0:
                    porcentaje = round(Decimal(avance) * 100 / meta_total, 1)
                else:
                    porcentaje = Decimal('0')
                if porcentaje > periodo.tope_cumplimiento:
                    porcentaje = periodo.tope_cumplimiento
                comisiones.append({
                    'id': meta.pk,
                    'cargo': cargo.nombre,
                    'nombre': meta.item.nombre,
                    'ponderacion': meta.ponderador,
                    'meta': meta_total,
                    'avance': avance,
                    'porcentaje_cumplimiento': porcentaje,
                    'total_ponderado': round(porcentaje * meta.ponderador / 100, 1),
                })

    data = {
        'delegacion_nombre': f"Delegación {nombre}",
        'comisiones': comisiones,
        'equipo': equipo,
    }
    return render(request, 'indicadores/resumen_delegacion.html', data)


def url_metas():
    """Vuelve al panel de administración con la pestaña de metas abierta."""
    return reverse('users:administracion') + '#goals'


def mostrar_errores(request, form):
    for errores in form.errors.values():
        for error in errores:
            messages.error(request, error)


def guardar_metas(request):
    """Crea una meta (o la actualiza si ya existe para ese cargo, ítem y alcance).
    El Administrador define metas generales o de cualquier delegación; el Delegado, solo de la suya."""
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_gestionar_metas():
        return acceso_denegado(request, 'Parametrización de Metas')
    if request.method != 'POST':
        return redirect(url_metas())

    form = MetaForm(request.POST, usuario=request.user, periodo=periodo_vigente())
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect(url_metas())
    meta, evento, antes = form.guardar()
    registrar_auditoria(request.user, evento, 'MetaDesempeno', meta.pk, antes, f"{meta} = {meta.valor_objetivo} ({meta.ponderador}%)")
    messages.success(request, "Meta guardada correctamente.")
    if form.total < 100:
        messages.warning(request, f"Los ponderadores del cargo {meta.cargo} suman {form.total}%. "
                                  f"Faltan {100 - form.total}% para completar 100%.")
    return redirect(url_metas())


def meta_editar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    meta = get_object_or_404(MetaDesempeno.objects.select_related('cargo', 'item', 'periodo', 'delegacion'), pk=pk)
    if not request.user.puede_editar_meta(meta):
        return acceso_denegado(request, 'Modificar meta')

    if request.method == 'POST':
        form = MetaForm(request.POST, usuario=request.user, periodo=meta.periodo, meta=meta)
        if form.is_valid():
            meta, evento, antes = form.guardar()
            registrar_auditoria(request.user, evento, 'MetaDesempeno', meta.pk, antes,
                                f"{meta} = {meta.valor_objetivo} ({meta.ponderador}%)")
            messages.success(request, "Meta modificada.")
            return redirect(url_metas())
    else:
        form = MetaForm(usuario=request.user, periodo=meta.periodo, meta=meta)
    return render(request, 'indicadores/meta_form.html', {'form': form, 'meta': meta})


def meta_eliminar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    meta = get_object_or_404(MetaDesempeno, pk=pk)
    if not request.user.puede_editar_meta(meta):
        return acceso_denegado(request, 'Eliminar meta')
    if request.method != 'POST':
        return redirect(url_metas())
    descripcion = f"{meta} = {meta.valor_objetivo} ({meta.ponderador}%)"
    registrar_auditoria(request.user, 'ELIMINACION', 'MetaDesempeno', meta.pk, descripcion, '')
    meta.delete()
    messages.success(request, "Meta eliminada.")
    return redirect(url_metas())
