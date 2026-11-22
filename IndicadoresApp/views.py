import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import Actividad
from AuditoriaApp.registro import registrar_auditoria
from IndicadoresApp.calculos import seguimiento_usuario, DatosMedicion
from IndicadoresApp.choices import TIPO_AJUSTE_FELICITACION
from IndicadoresApp.forms import MetaForm, PonderacionForm, PeriodoForm, AusenciaForm, FelicitacionForm, ReclamoForm, RespuestaReclamoForm
from IndicadoresApp.models import (MetaDesempeno, Ponderacion, Periodo, Ausencia, AjusteDesempeno, Felicitacion, Reclamo, periodo_vigente,
                                   metas_para)
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


def resumen_delegacion_tablero(delegacion, periodo, hoy, filas=None, datos=None):
    """Tarjetas del tablero: pendientes, avance esperado a la fecha, semáforo y puntaje colectivo de la delegación elegida
    (delegacion=None: toda la municipalidad). semaforo_color guarda el código (VERDE, AMBAR, ROJO o vacío)."""
    # Actividades pendientes = compromisos programados y actividades del Tubo (todavía sin evidencia)
    compromisos = Actividad.objects.filter(estado__in=['PROGRAMADA', 'EN_TUBO'])
    if delegacion is not None:
        compromisos = compromisos.filter(usuario__delegacion=delegacion)

    avance = Decimal('0')
    semaforo = 'Sin periodo vigente'
    color = ''
    meta_colectiva = Decimal('0')
    objetivo = Decimal('0')
    if periodo is not None:
        # Cada funcionario se calcula una sola vez: si el Semáforo ya trae las filas, se reutilizan
        if filas is None:
            datos = datos or DatosMedicion(periodo)
            filas = [seguimiento_usuario(usuario, periodo, hoy, datos) for usuario in usuarios_evaluados(delegacion)]
        filas = [fila for fila in filas if not fila['sin_medir']]  # sin ponderación completa no cuentan
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
        # Avance esperado a la fecha: porcentaje del trimestre transcurrido (días computables). Es la referencia del semáforo
        'avance_esperado': objetivo,
        'avance': avance,
        'semaforo_estado': semaforo,
        'semaforo_color': color,
    }


def comparacion_delegaciones(periodo, hoy):
    """Tablero del Coordinador: una fila por delegación activa con su avance, semáforo y pendientes."""
    from UsuarioApp.models import Delegacion
    filas, datos = [], (DatosMedicion(periodo) if periodo else None)  # una carga para todas las delegaciones
    for delegacion in Delegacion.objects.filter(estado='ACTIVO').order_by('nombre_visible'):
        fila = resumen_delegacion_tablero(delegacion, periodo, hoy, datos=datos)
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
    # Una sola pasada: las filas buscadas van a la tabla y todas a las tarjetas de resumen
    seguimiento, todas = filas_semaforo(delegacion, periodo, hoy, q, con_todas=True)
    dias_transcurridos = 0
    porcentaje_esperado = 0
    if periodo is not None:
        dias_transcurridos = periodo.calcular_dias_transcurridos(hoy)
        porcentaje_esperado = periodo.porcentaje_transcurrido(hoy)
    else:
        messages.warning(request, "No hay un periodo vigente para la fecha de hoy.")

    data = {
        'seguimiento': seguimiento,
        'q': q,
        'dias_transcurridos': dias_transcurridos,
        'porcentaje_esperado': porcentaje_esperado,
        'periodo': periodo,
        'resumen': resumen_delegacion_tablero(delegacion, periodo, hoy, filas=todas),
    }
    data.update(datos_ausencias(request.user, periodo))
    return render(request, 'indicadores/semaforo.html', data)


def filas_semaforo(delegacion, periodo, hoy, q='', con_todas=False):
    """Filas del Semáforo (una por responsable evaluado). La usan la pantalla y su exportación, así ambas muestran
    exactamente los mismos datos con los mismos filtros. con_todas=True devuelve además las de toda la delegación
    (sin la búsqueda), para las tarjetas de resumen, sin calcular a nadie dos veces."""
    if periodo is None:
        return ([], []) if con_todas else []
    datos = DatosMedicion(periodo)  # pocas consultas para todos, en vez de unas 40 por funcionario
    buscados = set(filtrar_por_nombre(usuarios_evaluados(delegacion), q).values_list('pk', flat=True))
    filas = []
    for usuario in usuarios_evaluados(delegacion).select_related('delegacion'):
        if con_todas or usuario.pk in buscados:
            fila = seguimiento_usuario(usuario, periodo, hoy, datos)
            fila['delegacion'] = str(usuario.delegacion) if usuario.delegacion_id else 'Sin delegación'
            filas.append(fila)
    elegidas = [fila for fila in filas if fila['id'] in buscados]
    return (elegidas, filas) if con_todas else elegidas


def numero_cl(valor):
    """Número con coma decimal, como lo lee Excel en Chile."""
    return str(valor).replace('.', ',')


@permiso_requerido('IndicadoresApp.view_metadesempeno', 'Exportar Semáforo')
def semaforo_exportar(request):
    """RF-033: exporta el Semáforo a CSV con los mismos filtros de la pantalla (delegación elegida y búsqueda por
    nombre o RUT). El archivo trae encabezado con el informe, el periodo, los filtros, quién lo generó y cuándo.
    Separador ';' y BOM UTF-8: Excel en español lo abre con tildes y columnas correctas."""
    codigo, delegacion, nombre = delegacion_seleccionada(request)
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)
    q = request.GET.get('q', '').strip()
    filas = filas_semaforo(delegacion, periodo, hoy, q)

    generado = timezone.localtime()
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="semaforo_{hoy:%Y%m%d}.csv"'
    respuesta.write('\ufeff')  # BOM: Excel reconoce el archivo como UTF-8
    escritor = csv.writer(respuesta, delimiter=';')
    escritor.writerow(['Informe', 'Semáforo: seguimiento de avance al día'])
    escritor.writerow(['Periodo', str(periodo) if periodo else 'Sin periodo vigente'])
    escritor.writerow(['Delegación', nombre])
    escritor.writerow(['Búsqueda', q or 'Sin filtro'])
    escritor.writerow(['Generado por', request.user.get_full_name() or request.user.username])
    escritor.writerow(['Fecha de generación', f"{generado:%d/%m/%Y %H:%M}"])
    escritor.writerow([])
    escritor.writerow(['Área', 'Responsable', 'Delegación', 'Objetivo hoy (%)', 'Mínimo (%)', 'Avance logrado (%)',
                       'Días ausente', 'Semáforo', 'Ítems al tope'])
    for fila in filas:
        escritor.writerow([fila['area'], fila['responsable'], fila['delegacion'], numero_cl(fila['objetivo_hoy']),
                           numero_cl(fila['minimo']), numero_cl(fila['avance_logrado']), fila['dias_ausencia'],
                           {'VERDE': 'Verde', 'AMBAR': 'Ámbar', 'ROJO': 'Rojo'}.get(fila['color'], 'Sin medir'),
                           ', '.join(fila['items_en_tope'])])
    # La exportación saca datos de funcionarios del sistema: queda en la auditoría quién la hizo y con qué filtros
    registrar_auditoria(request.user, 'CREACION', 'Exportación', 'Semáforo', '',
                        f"Delegación: {nombre} | Búsqueda: {q or '-'} | {len(filas)} filas")
    return respuesta


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


def avance_equipo(integrantes, item, periodo):
    """Actividades que suman a la meta de un equipo, con la misma regla de calcular_avance (RF-014): validadas, del
    responsable (el encargado si tiene; si no, quien la registró), sin las gestiones del Delegado (que solo quedan
    registradas) y sin las que el verificador marcó como coordinación que no suma puntaje."""
    responsable = Q(encargado__in=integrantes) | Q(encargado__isnull=True, usuario__in=integrantes)
    actividades = Actividad.objects.filter(responsable, item=item, periodo=periodo, estado='VALIDADA', es_gestion=False)
    actividades = actividades.exclude(evidencias__validacion__decision='APROBAR',
                                      evidencias__validacion__otorga_puntaje=False)
    return actividades.distinct().count()


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
                avance = avance_equipo(integrantes, meta.item, periodo)
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


# ---------------------------------------------------------------------------
# Periodos de medición (RF-005, RF-007): Coordinador y Administrador, desde Administración > Periodos
# ---------------------------------------------------------------------------
def url_periodos():
    return reverse('users:administracion') + '?pestana=periodos'


@permiso_requerido('IndicadoresApp.add_periodo', 'Crear periodo')
def periodo_crear(request):
    if request.method != 'POST':
        return redirect(url_periodos())
    if not request.user.puede_gestionar_metas():
        return acceso_denegado(request, 'Crear periodo')
    form = PeriodoForm(request.POST)
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect(url_periodos())
    periodo = form.save()
    registrar_auditoria(request.user, 'CREACION', 'Periodo', periodo.pk, '', resumen_periodo(periodo))
    messages.success(request, f"Periodo {periodo} creado.")
    return redirect(url_periodos())


def resumen_periodo(periodo):
    return (f"{periodo.nombre}: {periodo.fecha_inicio:%d/%m/%Y} a {periodo.fecha_termino:%d/%m/%Y}, "
            f"{periodo.dias_computables} días, verde {periodo.umbral_verde}%, ámbar {periodo.umbral_ambar}%, "
            f"colectivo {periodo.umbral_colectivo}%, tope {periodo.tope_cumplimiento}%, "
            f"felicitación {periodo.puntos_felicitacion} pp, {periodo.get_estado_display()}")


@permiso_requerido('IndicadoresApp.change_periodo', 'Modificar periodo')
def periodo_editar(request, pk):
    periodo = get_object_or_404(Periodo, pk=pk)
    if not request.user.puede_gestionar_metas():
        return acceso_denegado(request, 'Modificar periodo')
    antes = resumen_periodo(periodo)
    if request.method == 'POST':
        form = PeriodoForm(request.POST, instance=periodo)
        if form.is_valid():
            periodo = form.save()
            registrar_auditoria(request.user, 'MODIFICACION', 'Periodo', periodo.pk, antes, resumen_periodo(periodo))
            messages.success(request, f"Periodo {periodo} modificado.")
            return redirect(url_periodos())
    else:
        form = PeriodoForm(instance=periodo)
    return render(request, 'indicadores/periodo_form.html', {'form': form, 'periodo': periodo})


@permiso_requerido('IndicadoresApp.change_periodo', 'Cerrar o reabrir periodo')
def periodo_estado(request, pk):
    """Cerrar un periodo impide registrar actividades en él; reabrirlo lo vuelve a permitir. Queda en la auditoría."""
    periodo = get_object_or_404(Periodo, pk=pk)
    if not request.user.puede_gestionar_metas():
        return acceso_denegado(request, 'Cerrar o reabrir periodo')
    if request.method != 'POST':
        return redirect(url_periodos())
    anterior = periodo.get_estado_display()
    if periodo.periodo_cerrado():
        periodo.reabrir()
    else:
        periodo.cerrar()
    registrar_auditoria(request.user, 'MODIFICACION', 'Periodo', periodo.pk, f"estado={anterior}",
                        f"estado={periodo.get_estado_display()}")
    messages.success(request, f"Periodo {periodo}: {periodo.get_estado_display().lower()}.")
    return redirect(url_periodos())


@permiso_requerido('IndicadoresApp.add_metadesempeno', 'Parametrización de Metas')
def guardar_metas(request):
    """Crea una meta (o la actualiza si ya existe para ese cargo, ítem y alcance).
    La definen el Coordinador y el Administrador: generales o de una delegación."""
    if request.method != 'POST':
        return redirect(url_metas())
    if not request.user.puede_gestionar_metas():
        return acceso_denegado(request, 'Parametrización de Metas')

    form = MetaForm(request.POST, usuario=request.user, periodo=periodo_vigente())
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect(url_metas())
    meta, evento, antes = form.guardar()
    registrar_auditoria(request.user, evento, 'MetaDesempeno', meta.pk, antes, f"{meta} = {meta.valor_objetivo}")
    messages.success(request, "Meta guardada correctamente.")
    return redirect(url_metas(meta))


@permiso_requerido('IndicadoresApp.add_ponderacion', 'Ponderación')
def guardar_ponderacion(request):
    """RF-006: crea o actualiza el ponderador de un ítem para un cargo (Coordinador y Administrador).
    Si la suma del cargo queda bajo 100% se guarda con aviso: ese cargo no se mide hasta completarla (RN-001)."""
    if request.method != 'POST':
        return redirect(url_metas())
    if not request.user.puede_gestionar_metas():
        return acceso_denegado(request, 'Ponderación')
    form = PonderacionForm(request.POST, periodo=periodo_vigente())
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect(url_metas())
    ponderacion, evento, antes = form.guardar()
    registrar_auditoria(request.user, evento, 'Ponderacion', ponderacion.pk, antes, str(ponderacion))
    messages.success(request, "Ponderación guardada correctamente.")
    if form.total < 100:
        messages.warning(request, f"La ponderación del cargo {ponderacion.cargo} suma {form.total}%. Faltan "
                                  f"{100 - form.total}%: hasta completar 100% los funcionarios de ese cargo no se miden.")
    return redirect(url_metas())


@permiso_requerido('IndicadoresApp.change_ponderacion', 'Modificar ponderación')
def ponderacion_editar(request, pk):
    """Cambia el ponderador de un ítem ya ponderado. Cargo, ítem y periodo no cambian."""
    ponderacion = get_object_or_404(Ponderacion.objects.select_related('cargo', 'item', 'periodo'), pk=pk)
    if not request.user.puede_gestionar_metas():
        return acceso_denegado(request, 'Modificar ponderación')
    if request.method == 'POST':
        datos = {'cargo': ponderacion.cargo_id, 'item': ponderacion.item_id, 'ponderador': request.POST.get('ponderador', '')}
        form = PonderacionForm(datos, periodo=ponderacion.periodo)
        if form.is_valid():
            ponderacion, evento, antes = form.guardar()
            registrar_auditoria(request.user, evento, 'Ponderacion', ponderacion.pk, antes, str(ponderacion))
            messages.success(request, "Ponderación modificada.")
            if form.total < 100:
                messages.warning(request, f"La ponderación del cargo {ponderacion.cargo} suma {form.total}%. Faltan "
                                          f"{100 - form.total}%: hasta completar 100% los funcionarios de ese cargo no se miden.")
            return redirect(url_metas())
    else:
        form = PonderacionForm(initial={'ponderador': ponderacion.ponderador}, periodo=ponderacion.periodo)
    return render(request, 'indicadores/ponderacion_form.html', {'form': form, 'ponderacion': ponderacion})


@permiso_requerido('IndicadoresApp.delete_ponderacion', 'Eliminar ponderación')
def ponderacion_eliminar(request, pk):
    ponderacion = get_object_or_404(Ponderacion.objects.select_related('cargo', 'item', 'periodo'), pk=pk)
    if not request.user.puede_gestionar_metas():
        return acceso_denegado(request, 'Eliminar ponderación')
    if request.method != 'POST':
        return redirect(url_metas())
    if MetaDesempeno.objects.filter(cargo=ponderacion.cargo, item=ponderacion.item, periodo=ponderacion.periodo).exists():
        messages.error(request, f"{ponderacion.item} tiene metas para el cargo {ponderacion.cargo}: elimínelas antes "
                                "de quitar su ponderación.")
        return redirect(url_metas())
    registrar_auditoria(request.user, 'ELIMINACION', 'Ponderacion', ponderacion.pk, str(ponderacion), '')
    ponderacion.delete()
    messages.success(request, "Ponderación eliminada.")
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
            registrar_auditoria(request.user, evento, 'MetaDesempeno', meta.pk, antes, f"{meta} = {meta.valor_objetivo}")
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
    descripcion = f"{meta} = {meta.valor_objetivo}"
    registrar_auditoria(request.user, 'ELIMINACION', 'MetaDesempeno', meta.pk, descripcion, '')
    meta.delete()
    messages.success(request, "Meta eliminada.")
    return redirect(url_metas(meta))


# ---------------------------------------------------------------------------
# Felicitaciones y reclamos (solo Delegado y Administrador)
# Tres capas de protección: 1) @permiso_requerido exige el permiso del grupo (sin él vuelve a Mi Gestión);
# 2) puede_gestionar_felicitaciones() deja pasar solo al Delegado y al Administrador; 3) cada consulta se limita a
# funcionarios_para_felicitaciones(), así el Delegado solo ve y registra a los de su delegación.
# ---------------------------------------------------------------------------
def pagina_felicitaciones(request, form_felicitacion=None, form_reclamo=None, pestana=None):
    usuario = request.user
    periodo = periodo_vigente()
    funcionarios = usuario.funcionarios_para_felicitaciones()
    felicitaciones = Felicitacion.objects.filter(funcionario__in=funcionarios).select_related(
        'funcionario', 'funcionario__delegacion', 'registrado_por', 'ajuste', 'periodo')
    if periodo is not None:
        felicitaciones = felicitaciones.filter(periodo=periodo)
    reclamos = Reclamo.objects.filter(funcionario__in=funcionarios).select_related(
        'funcionario', 'funcionario__delegacion', 'registrado_por', 'respondido_por')
    data = {
        'periodo': periodo,
        'felicitaciones': felicitaciones,
        'reclamos': reclamos,
        'pendientes': reclamos.filter(estado='PENDIENTE').count(),
        'form_felicitacion': form_felicitacion or FelicitacionForm(registrador=usuario, periodo=periodo, prefix='felicitacion'),
        'form_reclamo': form_reclamo or ReclamoForm(registrador=usuario, prefix='reclamo'),
        'pestana': pestana or request.GET.get('pestana', 'felicitaciones'),
    }
    return render(request, 'indicadores/felicitaciones_reclamos.html', data)


@permiso_requerido('IndicadoresApp.view_felicitacion', 'Felicitaciones y Reclamos')
def felicitaciones_reclamos(request):
    if not request.user.puede_gestionar_felicitaciones():
        return acceso_denegado(request, 'Felicitaciones y Reclamos')
    return pagina_felicitaciones(request)


def tiene_metas(funcionario, periodo):
    return funcionario.cargo_id is not None and metas_para(funcionario.cargo_id, periodo, funcionario.delegacion_id).exists()


@permiso_requerido('IndicadoresApp.add_felicitacion', 'Registrar Felicitación')
def felicitacion_crear(request):
    if request.method != 'POST':
        return redirect('indicadores:felicitaciones_reclamos')
    if not request.user.puede_gestionar_felicitaciones():
        return acceso_denegado(request, 'Registrar Felicitación')
    periodo = periodo_vigente()
    # prefix: los dos formularios están en la misma página y sus campos no pueden tener el mismo id
    form = FelicitacionForm(request.POST, registrador=request.user, periodo=periodo, prefix='felicitacion')
    if not form.is_valid():
        return pagina_felicitaciones(request, form_felicitacion=form, pestana='felicitaciones')
    felicitacion = form.save(commit=False)
    felicitacion.periodo = periodo
    felicitacion.registrado_por = request.user
    # Los puntos se suman como un ajuste de desempeño: cuentan aunque el cargo no tenga meta de felicitaciones
    tipo = Catalogo.objects.get_or_create(tipo='TIPO_AJUSTE', nombre=TIPO_AJUSTE_FELICITACION)[0]
    felicitacion.ajuste = AjusteDesempeno.objects.create(
        valor=periodo.puntos_felicitacion, motivo=f"Felicitación de usuario: {felicitacion.motivo}"[:500],
        registrado_por=request.user, usuario=felicitacion.funcionario, tipo=tipo, periodo=periodo)
    felicitacion.save()
    registrar_auditoria(request.user, 'CREACION', 'Felicitacion', felicitacion.pk, '',
                        f"{felicitacion} (+{periodo.puntos_felicitacion} pp)")
    nombre = felicitacion.funcionario.get_full_name() or felicitacion.funcionario.username
    if tiene_metas(felicitacion.funcionario, periodo):
        puntos = str(periodo.puntos_felicitacion).replace('.', ',')
        messages.success(request, f"Felicitación registrada: suma {puntos} pp al cumplimiento de {nombre}.")
    else:
        messages.warning(request, f"Felicitación registrada, pero {nombre} no tiene metas en el {periodo}: "
                                  "los puntos se sumarán cuando su cargo tenga metas.")
    return redirect('indicadores:felicitaciones_reclamos')


@permiso_requerido('IndicadoresApp.delete_felicitacion', 'Eliminar Felicitación')
def felicitacion_eliminar(request, pk):
    felicitacion = get_object_or_404(Felicitacion, pk=pk)
    if request.method != 'POST':
        return redirect('indicadores:felicitaciones_reclamos')
    if not request.user.funcionarios_para_felicitaciones().filter(pk=felicitacion.funcionario_id).exists():
        return acceso_denegado(request, 'Eliminar Felicitación')
    descripcion = str(felicitacion)
    felicitacion.delete()  # borra también su ajuste: los puntos dejan de sumar
    registrar_auditoria(request.user, 'ELIMINACION', 'Felicitacion', pk, descripcion, '')
    messages.success(request, "Felicitación eliminada: sus puntos dejaron de sumar.")
    return redirect('indicadores:felicitaciones_reclamos')


@permiso_requerido('IndicadoresApp.add_reclamo', 'Registrar Reclamo')
def reclamo_crear(request):
    if request.method != 'POST':
        return redirect(reverse('indicadores:felicitaciones_reclamos') + '?pestana=reclamos')
    if not request.user.puede_gestionar_felicitaciones():
        return acceso_denegado(request, 'Registrar Reclamo')
    form = ReclamoForm(request.POST, registrador=request.user, prefix='reclamo')
    if not form.is_valid():
        return pagina_felicitaciones(request, form_reclamo=form, pestana='reclamos')
    reclamo = form.save(commit=False)
    reclamo.registrado_por = request.user
    reclamo.save()
    registrar_auditoria(request.user, 'CREACION', 'Reclamo', reclamo.pk, '', str(reclamo))
    messages.success(request, "Reclamo registrado: queda pendiente hasta que se responda.")
    return redirect(reverse('indicadores:felicitaciones_reclamos') + '?pestana=reclamos')


@permiso_requerido('IndicadoresApp.change_reclamo', 'Responder Reclamo')
def reclamo_responder(request, pk):
    reclamo = get_object_or_404(Reclamo, pk=pk)
    volver = reverse('indicadores:felicitaciones_reclamos') + '?pestana=reclamos'
    if request.method != 'POST':
        return redirect(volver)
    if not request.user.funcionarios_para_felicitaciones().filter(pk=reclamo.funcionario_id).exists():
        return acceso_denegado(request, 'Responder Reclamo')
    if reclamo.estado == 'RESUELTO':
        messages.error(request, "Ese reclamo ya fue respondido.")
        return redirect(volver)
    form = RespuestaReclamoForm(request.POST, instance=reclamo)
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect(volver)
    reclamo = form.save(commit=False)
    reclamo.estado = 'RESUELTO'
    reclamo.respondido_por = request.user
    reclamo.fecha_respuesta = timezone.now()
    reclamo.save()
    registrar_auditoria(request.user, 'MODIFICACION', 'Reclamo', reclamo.pk, 'PENDIENTE', 'RESUELTO')
    messages.success(request, "Reclamo respondido: queda resuelto.")
    return redirect(volver)
