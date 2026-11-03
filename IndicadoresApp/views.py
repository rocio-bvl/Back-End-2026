from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import Actividad
from AuditoriaApp.registro import registrar_auditoria
from IndicadoresApp.calculos import seguimiento_usuario
from IndicadoresApp.forms import MetaForm
from IndicadoresApp.models import MetaDesempeno, periodo_vigente, metas_para
from UsuarioApp.funciones import delegacion_seleccionada, acceso_denegado, permiso_requerido
from UsuarioApp.models import Usuario, Cargo, Catalogo


def filtrar_por_nombre(usuarios, q):
    """Buscador propio de Semáforo y Resumen: nombre, apellido o RUT."""
    if not q:
        return usuarios
    return usuarios.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q))


def usuarios_evaluados(delegacion):
    usuarios = Usuario.objects.filter(is_active=True, cargo__isnull=False).select_related('cargo', 'cargo__area')
    if delegacion is not None:
        usuarios = usuarios.filter(delegacion=delegacion)
    return usuarios


def tipo_tablero(usuario):
    """Qué tablero ve cada perfil, según su grupo de Django (J1). Cada uno de los 4 perfiles tiene el suyo:
    Administrador: totales del sistema. Supervisor (Coordinador): comparación entre delegaciones.
    Delegado: su delegación. Administrativo (Funcionario): lo suyo."""
    grupos = set(usuario.groups.values_list('name', flat=True))
    if usuario.is_superuser or 'Administrador' in grupos:
        return 'admin'
    if 'Supervisor' in grupos:
        return 'coordinador'
    if 'Delegado' in grupos:
        return 'delegado'
    return 'administrativo'


def resumen_delegacion_tablero(delegacion, periodo, hoy):
    """Las tres tarjetas de siempre: pendientes, avance promedio y semáforo de la delegación elegida
    (delegacion=None: toda la municipalidad). semaforo_color guarda el código (VERDE, AMBAR, ROJO o vacío)."""
    # Actividades pendientes = compromisos programados y actividades del Tubo (todavía sin ejecutar)
    compromisos = Actividad.objects.filter(estado__in=['PROGRAMADA', 'EN_TUBO'])
    if delegacion is not None:
        compromisos = compromisos.filter(usuario__delegacion=delegacion)

    avance = Decimal('0')
    semaforo = 'Sin periodo vigente'
    color = ''
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
    return {
        'compromisos_pendientes_count': compromisos.count(),
        'avance_periodo_porcentaje': f"{avance}%",
        'avance': avance,
        'semaforo_estado': semaforo,
        'semaforo_color': color,
    }


def comparacion_delegaciones(periodo, hoy):
    """Tablero del Coordinador: una fila por delegación activa con su avance, semáforo y pendientes."""
    from UsuarioApp.models import Delegacion
    filas = []
    for delegacion in Delegacion.objects.filter(estado='ACTIVO').order_by('nombre_visible'):
        fila = resumen_delegacion_tablero(delegacion, periodo, hoy)
        fila['delegacion'] = delegacion
        fila['responsables'] = usuarios_evaluados(delegacion).count()
        fila['por_validar'] = Actividad.objects.filter(estado='REGISTRADA', usuario__delegacion=delegacion).count()
        filas.append(fila)
    return filas


@login_required
def dashboard(request):
    """Tablero distinto por perfil (J5): elige la plantilla según el grupo del usuario."""
    from ActividadesApp.models import AtencionSocial
    from UsuarioApp.models import Delegacion

    usuario = request.user
    codigo, delegacion, nombre = delegacion_seleccionada(request)
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)
    tipo = tipo_tablero(usuario)

    data = {'delegacion_actual': f"Delegación {nombre}", 'periodo': periodo, 'tipo_tablero': tipo}

    if tipo == 'admin':
        data.update(resumen_delegacion_tablero(delegacion, periodo, hoy))
        data.update({
            'total_usuarios': Usuario.objects.filter(is_active=True).count(),
            'total_delegaciones': Delegacion.objects.filter(estado='ACTIVO').count(),
            'total_actividades': Actividad.objects.filter(periodo=periodo).count() if periodo else 0,
            'total_atenciones': AtencionSocial.objects.count(),
            'por_validar': Actividad.objects.filter(estado='REGISTRADA').count(),
            'total_metas': MetaDesempeno.objects.filter(periodo=periodo).count() if periodo else 0,
        })
        return render(request, 'indicadores/dashboard_admin.html', data)

    if tipo == 'coordinador':
        # Las tarjetas siguen al selector de la barra (GENERAL = toda la comuna); la tabla compara todas las
        # delegaciones y marca la elegida
        data.update(resumen_delegacion_tablero(delegacion, periodo, hoy))
        if delegacion is None:
            data['delegacion_actual'] = 'Toda la municipalidad'
        data['delegacion_elegida'] = delegacion
        data['delegaciones'] = comparacion_delegaciones(periodo, hoy)
        data['por_validar'] = Actividad.objects.filter(estado='REGISTRADA').count()
        return render(request, 'indicadores/dashboard_coordinador.html', data)

    if tipo == 'delegado':
        data.update(resumen_delegacion_tablero(delegacion, periodo, hoy))
        por_validar = Actividad.objects.filter(estado='REGISTRADA')
        if delegacion is not None:
            por_validar = por_validar.filter(usuario__delegacion=delegacion)
        data['por_validar'] = por_validar.count()
        # Los 5 responsables más atrasados de la delegación (para saber a quién apoyar primero)
        atrasados = []
        if periodo is not None:
            for evaluado in usuarios_evaluados(delegacion):
                atrasados.append(seguimiento_usuario(evaluado, periodo, hoy))
            atrasados.sort(key=lambda fila: fila['avance_logrado'])
        data['atrasados'] = atrasados[:5]
        return render(request, 'indicadores/dashboard_delegado.html', data)

    # Administrativo: su propio avance y lo que tiene pendiente
    mias = Actividad.objects.filter(usuario=usuario) | Actividad.objects.filter(encargado=usuario)
    data.update({
        'mi_avance': seguimiento_usuario(usuario, periodo, hoy) if periodo and usuario.cargo_id else None,
        'mis_pendientes': mias.filter(estado__in=['PROGRAMADA', 'EN_TUBO']).distinct().order_by('fecha_realizacion')[:5],
        'mis_pendientes_count': mias.filter(estado__in=['PROGRAMADA', 'EN_TUBO']).distinct().count(),
        'en_revision_count': mias.filter(estado='REGISTRADA').distinct().count(),
        'rechazadas_count': mias.filter(estado='RECHAZADA').distinct().count(),
        'validadas_count': mias.filter(estado='VALIDADA', periodo=periodo).distinct().count() if periodo else 0,
    })
    return render(request, 'indicadores/dashboard_administrativo.html', data)


@permiso_requerido('IndicadoresApp.view_metadesempeno', 'Semáforo')
def semaforo(request):

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)

    q = request.GET.get('q', '').strip()
    seguimiento = []
    dias_transcurridos = 0
    porcentaje_esperado = 0
    if periodo is not None:
        dias_transcurridos = periodo.calcular_dias_transcurridos(hoy)
        porcentaje_esperado = periodo.porcentaje_transcurrido(hoy)
        for usuario in filtrar_por_nombre(usuarios_evaluados(delegacion), q):
            seguimiento.append(seguimiento_usuario(usuario, periodo, hoy))
    else:
        messages.warning(request, "No hay un periodo vigente para la fecha de hoy.")

    data = {
        'seguimiento': seguimiento,
        'q': q,
        'dias_transcurridos': dias_transcurridos,
        'porcentaje_esperado': porcentaje_esperado,
        'periodo': periodo,
    }
    return render(request, 'indicadores/semaforo.html', data)


@permiso_requerido('IndicadoresApp.view_metadesempeno', 'Resumen de Delegación')
def resumen_delegacion(request):

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
                    # Botones Modificar / Eliminar: solo si quien mira puede editar esta meta
                    'editable': request.user.puede_editar_meta(meta),
                })

    # Equipo: cada integrante sabe si quien mira puede modificarlo o eliminarlo (pantallas propias, no Django Admin).
    # El buscador filtra solo la tabla del equipo; las comisiones siguen calculadas con toda la delegación.
    q = request.GET.get('q', '').strip()
    integrantes = list(filtrar_por_nombre(equipo, q))
    for integrante in integrantes:
        integrante.editable = request.user.puede_editar_usuario(integrante)
        integrante.eliminable = request.user.puede_eliminar_usuario(integrante)

    data = {
        'delegacion_nombre': f"Delegación {nombre}",
        'comisiones': comisiones,
        'equipo': integrantes,
        'q': q,
    }
    return render(request, 'indicadores/resumen_delegacion.html', data)


def url_metas():
    """Vuelve al panel de administración con la pestaña de metas abierta."""
    return reverse('users:administracion') + '#goals'


def mostrar_errores(request, form):
    for errores in form.errors.values():
        for error in errores:
            messages.error(request, error)


@permiso_requerido('IndicadoresApp.add_metadesempeno', 'Parametrización de Metas')
def guardar_metas(request):
    """Crea una meta (o la actualiza si ya existe para ese cargo, ítem y alcance).
    El Administrador define metas generales o de cualquier delegación; el Delegado, solo de la suya."""
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


@permiso_requerido('IndicadoresApp.change_metadesempeno', 'Modificar meta')
def meta_editar(request, pk):
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


@permiso_requerido('IndicadoresApp.delete_metadesempeno', 'Eliminar meta')
def meta_eliminar(request, pk):
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
