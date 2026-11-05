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
from IndicadoresApp.forms import MetaForm, AusenciaForm
from IndicadoresApp.models import MetaDesempeno, Ausencia, periodo_vigente, metas_para
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
    # Actividades pendientes = compromisos programados y actividades del Tubo (todavía sin evidencia)
    compromisos = Actividad.objects.filter(estado__in=['PROGRAMADA', 'EN_TUBO'])
    if delegacion is not None:
        compromisos = compromisos.filter(usuario__delegacion=delegacion)

    avance = Decimal('0')
    semaforo = 'Sin periodo vigente'
    color = ''
    meta_colectiva = Decimal('0')
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
        # Puntaje colectivo: el avance promedio del equipo. Se da por cumplido cuando alcanza el umbral colectivo
        # (80%) de lo esperado a la fecha
        meta_colectiva = round(objetivo * periodo.umbral_colectivo / 100, 1)
    return {
        'puntaje_colectivo': avance,
        'meta_colectiva': meta_colectiva,
        'cumple_colectivo': periodo is not None and avance >= meta_colectiva,
        'umbral_colectivo': periodo.umbral_colectivo if periodo else None,
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
        fila['por_validar'] = Actividad.objects.filter(estado='EVIDENCIA_INGRESADA', es_gestion=False, usuario__delegacion=delegacion).count()
        filas.append(fila)
    return filas


@login_required
def dashboard(request):
    """El tablero quedó dentro de Mi Gestión (pestaña Resumen): esta dirección se conserva y lleva allá."""
    destino = reverse('actividades:mi_gestion')
    if request.GET:
        destino += '?' + request.GET.urlencode()
    return redirect(destino)


def datos_tablero(request):
    """Datos del tablero de cada perfil (J5) para Mi Gestión: el grupo del usuario decide qué se calcula y qué
    plantilla parcial se muestra en la pestaña Resumen (indicadores/dashboard_<perfil>.html)."""
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
            'por_validar': Actividad.objects.filter(estado='EVIDENCIA_INGRESADA', es_gestion=False).count(),
            'total_metas': MetaDesempeno.objects.filter(periodo=periodo).count() if periodo else 0,
        })
        data['plantilla_tablero'] = 'indicadores/dashboard_admin.html'
        return data

    if tipo == 'coordinador':
        # Las tarjetas siguen al selector de la barra (GENERAL = toda la comuna); la tabla compara todas las
        # delegaciones y marca la elegida
        data.update(resumen_delegacion_tablero(delegacion, periodo, hoy))
        if delegacion is None:
            data['delegacion_actual'] = 'Toda la municipalidad'
        data['delegacion_elegida'] = delegacion
        data['delegaciones'] = comparacion_delegaciones(periodo, hoy)
        data['por_validar'] = Actividad.objects.filter(estado='EVIDENCIA_INGRESADA', es_gestion=False).count()
        data['plantilla_tablero'] = 'indicadores/dashboard_coordinador.html'
        return data

    if tipo == 'delegado':
        data.update(resumen_delegacion_tablero(delegacion, periodo, hoy))
        por_validar = Actividad.objects.filter(estado='EVIDENCIA_INGRESADA', es_gestion=False)
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
        data['plantilla_tablero'] = 'indicadores/dashboard_delegado.html'
        return data

    # Administrativo: su propio avance y lo que tiene pendiente, y el puntaje colectivo de su equipo
    mias = Actividad.objects.filter(usuario=usuario) | Actividad.objects.filter(encargado=usuario)
    colectivo = resumen_delegacion_tablero(usuario.delegacion, periodo, hoy) if usuario.delegacion_id else {}
    data.update({
        'puntaje_colectivo': colectivo.get('puntaje_colectivo'),
        'meta_colectiva': colectivo.get('meta_colectiva'),
        'cumple_colectivo': colectivo.get('cumple_colectivo'),
        'umbral_colectivo': colectivo.get('umbral_colectivo'),
        'mi_avance': seguimiento_usuario(usuario, periodo, hoy) if periodo and usuario.cargo_id else None,
        'mis_pendientes': mias.filter(estado__in=['PROGRAMADA', 'EN_TUBO']).distinct().order_by('fecha_realizacion')[:5],
        'mis_pendientes_count': mias.filter(estado__in=['PROGRAMADA', 'EN_TUBO']).distinct().count(),
        'en_revision_count': mias.filter(estado='EVIDENCIA_INGRESADA').distinct().count(),
        'rechazadas_count': mias.filter(estado='RECHAZADA').distinct().count(),
        'validadas_count': mias.filter(estado='VALIDADA', periodo=periodo).distinct().count() if periodo else 0,
    })
    data['plantilla_tablero'] = 'indicadores/dashboard_administrativo.html'
    return data


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
        'resumen': resumen_delegacion_tablero(delegacion, periodo, hoy),
    }
    data.update(datos_ausencias(request.user, periodo))
    return render(request, 'indicadores/semaforo.html', data)


# ---------------------------------------------------------------------------
# Ausencias: vacaciones, días administrativos y licencias (ajustan las metas)
# ---------------------------------------------------------------------------
def datos_ausencias(usuario, periodo, form=None):
    """Ausencias del periodo que puede ver y gestionar el usuario, y el formulario para registrar una nueva."""
    if not usuario.puede_registrar_ausencias() or periodo is None:
        return {'puede_ausencias': False}
    ausencias = Ausencia.objects.filter(usuario__in=usuario.usuarios_para_ausencias(), desde__lte=periodo.fecha_termino,
                                        hasta__gte=periodo.fecha_inicio).select_related('usuario', 'registrado_por')
    return {
        'puede_ausencias': True,
        'ausencias': ausencias,
        'form_ausencia': form or AusenciaForm(registrador=usuario),
    }


@permiso_requerido('IndicadoresApp.add_ausencia', 'Registrar Ausencia')
def ausencia_crear(request):
    if request.method != 'POST':
        return redirect(reverse('indicadores:semaforo') + '#ausencias')
    if not request.user.puede_registrar_ausencias():
        return acceso_denegado(request, 'Registrar Ausencia')
    form = AusenciaForm(request.POST, registrador=request.user)
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect(reverse('indicadores:semaforo') + '#ausencias')
    ausencia = form.save(commit=False)
    ausencia.registrado_por = request.user
    ausencia.save()
    registrar_auditoria(request.user, 'CREACION', 'Ausencia', ausencia.pk, '', f"{ausencia} ({ausencia.dias()} días)")
    messages.success(request, f"Ausencia registrada: las metas de {ausencia.usuario} se ajustaron a los días trabajados.")
    return redirect(reverse('indicadores:semaforo') + '#ausencias')


@permiso_requerido('IndicadoresApp.delete_ausencia', 'Eliminar Ausencia')
def ausencia_eliminar(request, pk):
    ausencia = get_object_or_404(Ausencia, pk=pk)
    if request.method != 'POST':
        return redirect(reverse('indicadores:semaforo') + '#ausencias')
    if not request.user.usuarios_para_ausencias().filter(pk=ausencia.usuario_id).exists():
        return acceso_denegado(request, 'Eliminar Ausencia')
    descripcion = str(ausencia)
    ausencia.delete()
    registrar_auditoria(request.user, 'ELIMINACION', 'Ausencia', pk, descripcion, '')
    messages.success(request, "Ausencia eliminada: las metas se recalcularon.")
    return redirect(reverse('indicadores:semaforo') + '#ausencias')


# ---------------------------------------------------------------------------
# Reporte de atrasos de validación por delegado
# ---------------------------------------------------------------------------
DIAS_ALERTA_VALIDACION = 3  # desde este atraso la alerta y el reporte la marcan en rojo


@permiso_requerido('IndicadoresApp.view_metadesempeno', 'Atrasos de validación')
def atrasos_validacion(request):
    """Para el Administrador y el Coordinador: por delegación, cuántas evidencias esperan validación, cuántas
    llevan más de 3 días, la más antigua y cuánto se demora el delegado en validar."""
    from ActividadesApp.models import Evidencia, Validacion
    from UsuarioApp.models import Delegacion
    if not request.user.puede_administrar():
        return acceso_denegado(request, 'Atrasos de validación')
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)
    filas = []
    for delegacion in Delegacion.objects.filter(estado='ACTIVO').order_by('nombre_visible'):
        pendientes = Evidencia.objects.filter(estado_revision='PENDIENTE', actividad__es_gestion=False,
                                              actividad__usuario__delegacion=delegacion)
        edades = [(hoy - timezone.localtime(e.fecha).date()).days for e in pendientes]
        validaciones = Validacion.objects.filter(evidencia__actividad__usuario__delegacion=delegacion,
                                                 evidencia__actividad__es_gestion=False).select_related('evidencia')
        if periodo is not None:
            validaciones = validaciones.filter(evidencia__actividad__periodo=periodo)
        demoras = [(v.fecha - v.evidencia.fecha).total_seconds() / 86400 for v in validaciones]
        filas.append({
            'delegacion': delegacion,
            'delegados': ', '.join(str(d) for d in delegacion.delegados()) or 'Sin delegado',
            'pendientes': len(edades),
            'atrasadas': sum(1 for edad in edades if edad >= DIAS_ALERTA_VALIDACION),
            'mas_antigua': max(edades) if edades else 0,
            'validadas': len(demoras),
            'promedio_dias': round(sum(demoras) / len(demoras), 1) if demoras else None,
        })
    filas.sort(key=lambda fila: (-fila['atrasadas'], -fila['mas_antigua']))
    return render(request, 'indicadores/atrasos_validacion.html', {
        'filas': filas, 'periodo': periodo, 'dias_alerta': DIAS_ALERTA_VALIDACION})


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


def url_metas(meta=None):
    """Vuelve al panel de administración con la pestaña de metas abierta.
    Con una meta, el selector queda en su delegación (o en GENERAL), para que se vea lo que se acaba de guardar."""
    if meta is None:
        return reverse('users:administracion') + '#goals'
    codigo = meta.delegacion.nombre if meta.delegacion else 'GENERAL'
    return reverse('users:administracion') + f"?pestana=metas&delegacion={codigo}#goals"


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
    return redirect(url_metas(meta))


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
            return redirect(url_metas(meta))
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
    return redirect(url_metas(meta))
