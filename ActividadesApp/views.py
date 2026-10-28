from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Q, F
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.choices import ESTADOS_PENDIENTES
# validar_imagen se importa aquí porque las pruebas la usan como ActividadesApp.views.validar_imagen
from ActividadesApp.forms import (ActividadForm, EjecucionForm, FechaRealizacionForm, ComentarioForm, EncargadoForm,
                                  AtencionForm, solicitudes_para, validar_imagen)
from ActividadesApp.models import (Actividad, Evidencia, Validacion, AtencionSocial, ComentarioActividad,
                                   DIAS_POR_VENCER)
from AuditoriaApp.registro import registrar_auditoria
from IndicadoresApp.calculos import indicadores_usuario, total_ponderado
from IndicadoresApp.models import periodo_vigente
from UsuarioApp.funciones import opciones_delegacion
from UsuarioApp.funciones import delegacion_seleccionada, acceso_denegado
from UsuarioApp.models import Usuario


# ---------------------------------------------------------------------------
# Reglas de acceso a una actividad (las usan las vistas y las plantillas)
# ---------------------------------------------------------------------------
def misma_delegacion(usuario, actividad):
    return usuario.delegacion_id is not None and usuario.delegacion_id == actividad.usuario.delegacion_id


def puede_ver_actividad(usuario, actividad):
    """La ven quien la registró, su encargado, el Admin, el Coordinador y los de su misma delegación."""
    if actividad.es_responsable(usuario) or usuario.tiene_rol(['Admin', 'Coordinador']):
        return True
    return misma_delegacion(usuario, actividad)


def puede_comentar(usuario, actividad):
    """Escriben en la bitácora: quien la registró, su encargado, el Delegado de la delegación y el Admin.
    El Coordinador solo visualiza."""
    if actividad.es_responsable(usuario) or usuario.es_administrador():
        return True
    return usuario.es_delegado() and misma_delegacion(usuario, actividad)


def puede_programar(usuario, actividad):
    """Asignan o cambian la fecha de una actividad pendiente: sus responsables, su Delegado y el Admin."""
    if not actividad.pendiente():
        return False
    return puede_comentar(usuario, actividad)


def puede_asignar_encargado(usuario, actividad):
    """Delegado (en su delegación), Coordinador y Admin asignan encargado a una actividad sin ejecutar."""
    if not usuario.puede_asignar_encargado() or actividad.estado not in ESTADOS_PENDIENTES + ['RECHAZADA']:
        return False
    if usuario.es_delegado():
        return misma_delegacion(usuario, actividad)
    return True


def candidatos_encargado(usuario, actividad):
    """Funcionarios activos que se pueden asignar: el Delegado elige entre los de su delegación;
    el Coordinador y el Admin, entre todos los de las delegaciones registradas."""
    funcionarios = Usuario.objects.filter(is_active=True, roles_asignados__rol__codigo='Funcionario').select_related('delegacion')
    if usuario.es_delegado():
        funcionarios = funcionarios.filter(delegacion_id=usuario.delegacion_id)
    return funcionarios.distinct().order_by('delegacion__nombre', 'first_name', 'last_name')


def fila_actividad(actividad, usuario):
    """Adapta una actividad a los nombres que usan las tablas de las plantillas."""
    ejecucion = actividad.ejecucion_vigente()
    return {
        'id': actividad.pk,
        'folio': actividad.folio(),
        'fecha': actividad.fecha,
        'fecha_realizacion': actividad.fecha_realizacion,
        'solicitud_problema': actividad.solicitud_problema,
        'accion': actividad.accion,
        'item': actividad.item.nombre,
        'territorio': actividad.territorio or '-',
        'funcionario': actividad.usuario,
        'encargado': actividad.encargado,
        'delegacion': actividad.usuario.delegacion or 'General',
        'depende_externos': actividad.depende_externos,
        'estado_codigo': actividad.estado,
        'estado': actividad.get_estado_display(),
        'vencido': actividad.vencido(),
        'proximo_a_vencer': actividad.proximo_a_vencer(),
        'tiene_foto': bool(ejecucion and ejecucion.imagen),
        'solicitud': actividad.solicitud,
        'puede_ejecutar': actividad.puede_ejecutar(usuario),
    }


# ---------------------------------------------------------------------------
# Mi Gestión: el perfil del usuario conectado
# ---------------------------------------------------------------------------
def mi_gestion(request):
    """Una sola vista para los cuatro roles. Lo que cambia entre roles no son plantillas distintas:
    son las consultas (qué actividades se traen) y los {% if %} de la plantilla (qué se muestra)."""
    if not request.user.is_authenticated:
        return redirect('users:login')

    usuario = request.user
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)
    base = Actividad.objects.select_related('item', 'usuario', 'usuario__delegacion', 'encargado', 'territorio', 'solicitud')

    # 1. Mis actividades: las que registré y las que me asignaron como encargado
    mias = base.filter(Q(usuario=usuario) | Q(encargado=usuario))
    mis_actividades = [fila_actividad(a, usuario) for a in mias]
    pendientes = [a for a in mis_actividades if a['estado_codigo'] in ESTADOS_PENDIENTES + ['RECHAZADA']]
    pendientes.sort(key=lambda a: (a['fecha_realizacion'] is None, a['fecha_realizacion'] or hoy))

    # 2. Indicadores del perfil
    indicadores = indicadores_usuario(usuario, periodo, hoy)
    completadas = mias.filter(estado='VALIDADA')
    if periodo is not None:
        completadas = completadas.filter(periodo=periodo)
    cumplimiento = total_ponderado(indicadores)
    resumen = {
        'cumplimiento': cumplimiento,
        'barra': int(min(cumplimiento, 100)),  # ancho de la barra de progreso (máximo 100%)
        'tiene_metas': bool(indicadores),
        'completadas': completadas.count(),
        'pendientes': len(pendientes),
        'en_revision': mias.filter(estado='REGISTRADA').count(),
    }
    metas = [{
        'item_nombre': ind.meta.item.nombre,
        'ponderador': ind.meta.ponderador,
        'meta_trimestre': ind.meta.valor_objetivo,
        'avance_actual': ind.avance_actual,
        'porcentaje_cumplimiento': ind.cumplimiento,
        'cumplimiento_ponderado': ind.cumplimiento_ponderado,
    } for ind in indicadores]

    # 3. Supervisión: Admin y Coordinador ven todas las delegaciones (o la que filtren); el Delegado, solo la suya
    vista_global = usuario.tiene_rol(['Admin', 'Coordinador'])
    ve_delegacion = vista_global or usuario.es_delegado()
    codigo, delegacion, nombre = delegacion_seleccionada(request)
    actividades_delegacion = []
    funcionarios_delegacion = []
    filtro_funcionario = request.GET.get('funcionario', '')
    if ve_delegacion:
        de_la_delegacion = base
        if delegacion is not None:
            de_la_delegacion = de_la_delegacion.filter(usuario__delegacion=delegacion)
        elif usuario.es_delegado():
            de_la_delegacion = de_la_delegacion.none()
        funcionarios_delegacion = Usuario.objects.filter(pk__in=de_la_delegacion.values('usuario')).order_by('first_name')
        if filtro_funcionario.isdigit():
            de_la_delegacion = de_la_delegacion.filter(Q(usuario_id=filtro_funcionario) | Q(encargado_id=filtro_funcionario))
        actividades_delegacion = [fila_actividad(a, usuario) for a in de_la_delegacion]

        if vista_global:
            # Admin y Coordinador no tienen actividades propias que medir: las tarjetas resumen lo que muestra la tabla
            completadas = de_la_delegacion.filter(estado='VALIDADA')
            if periodo is not None:
                completadas = completadas.filter(periodo=periodo)
            resumen = {
                'total': de_la_delegacion.count(),
                'completadas': completadas.count(),
                'pendientes': de_la_delegacion.filter(estado__in=ESTADOS_PENDIENTES + ['RECHAZADA']).count(),
                'en_revision': de_la_delegacion.filter(estado='REGISTRADA').count(),
            }

    data = {
        'resumen': resumen,
        'periodo': periodo,
        'metas': metas,
        'mis_actividades': mis_actividades,
        'pendientes': pendientes,
        # Admin y Coordinador no tienen pestañas propias: solo ven las actividades de todas las delegaciones
        'vista_global': vista_global,
        'muestra_mis_actividades': not vista_global and (usuario.puede_registrar() or bool(mis_actividades)),
        've_delegacion': ve_delegacion,
        'actividades_delegacion': actividades_delegacion,
        'funcionarios_delegacion': funcionarios_delegacion,
        'filtro_funcionario': filtro_funcionario,
        'opciones_delegacion': opciones_delegacion(),
        'delegacion_activa': codigo,
        'delegacion_nombre': nombre,
        'pestana': request.GET.get('pestana', ''),
    }
    return render(request, 'actividades/mi_gestion.html', data)


# ---------------------------------------------------------------------------
# Registrar actividad
# ---------------------------------------------------------------------------
def fecha_de_texto(texto):
    """Convierte 'AAAA-MM-DD' en fecha. Devuelve None si viene vacío o mal escrito."""
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def guardar_ejecucion(actividad, usuario, comentario, imagen):
    """Crea el registro de ejecución (nueva versión si ya había uno) y deja la actividad en revisión."""
    anterior = actividad.ejecucion_vigente()
    ejecucion = Evidencia.objects.create(
        actividad=actividad, comentario=comentario, imagen=imagen or '',
        version=(anterior.version + 1) if anterior else 1, reemplaza_a=anterior)
    registrar_auditoria(usuario, 'CREACION', 'Evidencia', ejecucion.pk, '', ejecucion)
    return ejecucion


def actividad_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    # Registran actividades el Funcionario y el Admin. El Coordinador solo visualiza; el Delegado valida.
    if not request.user.puede_registrar():
        return acceso_denegado(request, 'Registrar Actividad')

    periodo = periodo_vigente()
    if request.method == 'POST':
        form = ActividadForm(request.POST, request.FILES, usuario=request.user)
        if form.is_valid():
            datos = form.cleaned_data
            if periodo is None or periodo.periodo_cerrado():
                form.add_error(None, "No hay un periodo vigente abierto: no se pueden registrar actividades.")
            elif datos['fecha_realizacion'] is not None and datos['fecha_realizacion'] < periodo.fecha_inicio:
                form.add_error('fecha_realizacion', "La fecha es anterior al periodo vigente.")
        # add_error() deja el formulario inválido: el segundo is_valid() ya considera estas dos reglas
        if form.is_valid():
            datos = form.cleaned_data
            estado = form.estado_inicial()
            actividad = Actividad.objects.create(
                solicitud_problema=datos['solicitud_problema'].strip(),
                accion=datos['accion'].strip(),
                territorio=datos['territorio'],
                depende_externos=datos['depende_externos'],
                fecha_realizacion=datos['fecha_realizacion'],
                estado=estado,
                item=datos['item'],
                periodo=periodo,
                usuario=request.user,
                encargado=datos['encargado'],
                solicitud=datos['solicitud'],
            )
            registrar_auditoria(request.user, 'CREACION', 'Actividad', actividad.pk, '', f"{actividad} [{actividad.estado}]")

            if estado == 'REGISTRADA':
                guardar_ejecucion(actividad, request.user, datos['comentario'].strip(), datos['imagen'])
                actividad.sincronizar_estado()
                messages.success(request, f"Actividad {actividad.folio()} registrada como ejecutada. "
                                          "Queda a la espera de la validación del Delegado.")
                return redirect('actividades:mi_gestion')
            if actividad.depende_externos:
                if actividad.fecha_realizacion:
                    messages.success(request, f"Actividad {actividad.folio()} ingresada al Tubo de Trabajo con fecha de "
                                              f"ejecución {actividad.fecha_realizacion:%d/%m/%Y}.")
                else:
                    messages.success(request, f"Actividad {actividad.folio()} ingresada al Tubo de Trabajo. "
                                              "La fecha de ejecución se puede agregar después.")
                return redirect('actividades:tubo_trabajo')
            messages.success(request, f"Actividad {actividad.folio()} programada para el "
                                      f"{actividad.fecha_realizacion:%d/%m/%Y}. Queda pendiente hasta que se ejecute.")
            return redirect('actividades:mi_gestion')
    else:
        inicial = {'depende_externos': request.GET.get('tubo') == '1'}
        if inicial['depende_externos']:
            inicial['fecha_realizacion'] = None  # en el Tubo la fecha de ejecución parte vacía
        if request.GET.get('solicitud', '').isdigit():
            inicial['solicitud'] = request.GET['solicitud']  # "Crear actividad" desde el Registro de Atenciones
        form = ActividadForm(usuario=request.user, initial=inicial)

    return render(request, 'actividades/actividad_form.html', {'form': form, 'hoy': timezone.localdate()})


# ---------------------------------------------------------------------------
# Detalle de la actividad: ejecución, fecha, encargado y bitácora
# ---------------------------------------------------------------------------
def actividad_detalle(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    actividad = get_object_or_404(Actividad.objects.select_related('usuario', 'item', 'periodo', 'encargado', 'territorio'), pk=pk)
    if not puede_ver_actividad(request.user, actividad):
        return acceso_denegado(request, f"la actividad {actividad.folio()}")

    ejecuciones = []
    for ejecucion in actividad.evidencias.order_by('-version'):
        validacion = getattr(ejecucion, 'validacion', None)
        ejecuciones.append({
            'codigo': ejecucion.codigo(),
            'version': ejecucion.version,
            'fecha': ejecucion.fecha,
            'comentario': ejecucion.comentario,
            'imagen': ejecucion.imagen,
            'estado': ejecucion.get_estado_revision_display(),
            'estado_codigo': ejecucion.estado_revision,
            'observacion': validacion.observacion if validacion else '',
            'verificador': validacion.verificador if validacion else None,
        })

    usuario = request.user
    data = {
        'actividad': actividad,
        'ejecuciones': ejecuciones,
        'comentarios': actividad.comentarios.select_related('usuario'),
        'puede_ejecutar': actividad.puede_ejecutar(usuario),
        'puede_comentar': puede_comentar(usuario, actividad),
        'puede_programar': puede_programar(usuario, actividad),
        'puede_asignar': puede_asignar_encargado(usuario, actividad),
        'form_ejecucion': EjecucionForm(),
        'form_fecha': FechaRealizacionForm(initial={'fecha_realizacion': actividad.fecha_realizacion}),
        'form_comentario': ComentarioForm(),
        'form_encargado': EncargadoForm(candidatos=candidatos_encargado(usuario, actividad),
                                        initial={'encargado': actividad.encargado_id}),
        'hoy': timezone.localdate(),
    }
    return render(request, 'actividades/actividad_detalle.html', data)


def mostrar_errores(request, form):
    for errores in form.errors.values():
        for error in errores:
            messages.error(request, error)


def registrar_ejecucion(request, pk):
    """Quien registró la actividad o su encargado deja constancia de que se hizo (comentario + foto opcional).
    Sirve para un compromiso, una actividad del Tubo o una ejecución rechazada."""
    if not request.user.is_authenticated:
        return redirect('users:login')
    actividad = get_object_or_404(Actividad, pk=pk)
    if request.method != 'POST':
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    if not actividad.puede_ejecutar(request.user):
        messages.error(request, "Solo quien registró la actividad o su encargado registran la ejecución, "
                                "y solo si está pendiente o fue rechazada.")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    form = EjecucionForm(request.POST, request.FILES)
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    estado_anterior = actividad.estado
    guardar_ejecucion(actividad, request.user, form.cleaned_data['comentario'], form.cleaned_data['imagen'])
    if estado_anterior in ESTADOS_PENDIENTES:
        # Un compromiso cuenta en el periodo en que se ejecuta, y su fecha de realización es hoy
        periodo = periodo_vigente()
        if periodo is not None and not periodo.periodo_cerrado():
            actividad.periodo = periodo
        actividad.fecha_realizacion = timezone.localdate()
    actividad.sincronizar_estado()
    registrar_auditoria(request.user, 'MODIFICACION', 'Actividad', actividad.pk, estado_anterior, actividad.estado)

    if estado_anterior == 'RECHAZADA':
        messages.success(request, f"Nueva ejecución de {actividad.folio()} enviada a validación.")
    else:
        messages.success(request, f"Actividad {actividad.folio()} ejecutada: espera la validación del Delegado.")
    return redirect('actividades:actividad_detalle', pk=actividad.pk)


def asignar_fecha(request, pk):
    """Asigna la fecha a una actividad del Tubo (pasa a PROGRAMADA) o cambia la de un compromiso."""
    if not request.user.is_authenticated:
        return redirect('users:login')
    actividad = get_object_or_404(Actividad, pk=pk)
    if request.method != 'POST':
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    if not puede_programar(request.user, actividad):
        messages.error(request, "No puede asignar la fecha de esta actividad.")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    form = FechaRealizacionForm(request.POST)
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    antes = f"{actividad.estado} {actividad.fecha_realizacion or 'sin fecha'}"
    actividad.fecha_realizacion = form.cleaned_data['fecha_realizacion']
    actividad.estado = 'PROGRAMADA'
    actividad.save()
    registrar_auditoria(request.user, 'MODIFICACION', 'Actividad', actividad.pk, antes,
                        f"{actividad.estado} {actividad.fecha_realizacion}")
    messages.success(request, f"Actividad {actividad.folio()} programada para el {actividad.fecha_realizacion:%d/%m/%Y}.")
    return redirect('actividades:actividad_detalle', pk=actividad.pk)


def asignar_encargado(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    actividad = get_object_or_404(Actividad.objects.select_related('usuario'), pk=pk)
    if request.method != 'POST':
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    if not puede_asignar_encargado(request.user, actividad):
        messages.error(request, "No puede asignar encargado a esta actividad.")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    form = EncargadoForm(request.POST, candidatos=candidatos_encargado(request.user, actividad))
    if not form.is_valid():
        messages.error(request, "Elija un Funcionario de la lista.")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    antes = str(actividad.encargado or 'sin encargado')
    actividad.encargado = form.cleaned_data['encargado']
    actividad.save(update_fields=['encargado'])
    registrar_auditoria(request.user, 'MODIFICACION', 'Actividad', actividad.pk, f"encargado={antes}",
                        f"encargado={actividad.encargado}")
    messages.success(request, f"{actividad.encargado} queda a cargo de {actividad.folio()}.")
    return redirect('actividades:actividad_detalle', pk=actividad.pk)


def comentar_actividad(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    actividad = get_object_or_404(Actividad.objects.select_related('usuario'), pk=pk)
    if request.method != 'POST':
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    if not puede_comentar(request.user, actividad):
        messages.error(request, "No puede agregar actualizaciones a esta actividad.")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    form = ComentarioForm(request.POST)
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    comentario = ComentarioActividad.objects.create(actividad=actividad, usuario=request.user,
                                                    texto=form.cleaned_data['texto'])
    registrar_auditoria(request.user, 'CREACION', 'ComentarioActividad', comentario.pk, '', comentario.texto[:200])
    messages.success(request, "Actualización agregada a la bitácora.")
    return redirect(reverse('actividades:actividad_detalle', args=[actividad.pk]) + '#bitacora')


# ---------------------------------------------------------------------------
# Tubo de Trabajo: actividades que dependen de factores externos
# ---------------------------------------------------------------------------
ESTADOS_FILTRO_TUBO = [
    ('', 'Pendientes (con y sin fecha)'),
    ('SIN_FECHA', 'Sin fecha de ejecución'),
    ('CON_FECHA', 'Con fecha de ejecución'),
    ('VENCIDOS', 'Con fecha vencida'),
    ('EJECUTADAS', 'Ejecutadas, en revisión'),
    ('COMPLETADAS', 'Completadas (validadas)'),
    ('TODOS', 'Todas'),
]


def tubo_trabajo(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Funcionario']):
        return acceso_denegado(request, 'Tubo de Trabajo')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    # El Tubo son las actividades que dependen de factores externos: se registran sin fecha
    actividades = Actividad.objects.filter(depende_externos=True).select_related('usuario', 'encargado', 'territorio', 'item')
    if delegacion is not None:
        # Todos los de la delegación ven la agenda colectiva
        actividades = actividades.filter(usuario__delegacion=delegacion)
    elif not request.user.tiene_rol(['Admin', 'Coordinador']):
        # Sin delegación asignada: solo lo propio
        actividades = actividades.filter(Q(usuario=request.user) | Q(encargado=request.user))

    filtros = {
        'responsable': request.GET.get('responsable', ''),
        'estado': request.GET.get('estado', ''),
        'territorio': request.GET.get('territorio', ''),
        'mios': request.GET.get('mios', ''),
    }
    responsables = Usuario.objects.filter(Q(pk__in=actividades.values('usuario')) | Q(pk__in=actividades.values('encargado'))).order_by('first_name', 'last_name')
    territorios = sorted({a.territorio for a in actividades if a.territorio}, key=lambda t: t.nombre)

    hoy = timezone.localdate()
    if filtros['responsable'].isdigit():
        actividades = actividades.filter(Q(usuario_id=filtros['responsable']) | Q(encargado_id=filtros['responsable']))
    if filtros['estado'] == 'SIN_FECHA':
        actividades = actividades.filter(estado='EN_TUBO')
    elif filtros['estado'] == 'CON_FECHA':
        actividades = actividades.filter(estado='PROGRAMADA')
    elif filtros['estado'] == 'VENCIDOS':
        actividades = actividades.filter(estado='PROGRAMADA', fecha_realizacion__lt=hoy)
    elif filtros['estado'] == 'EJECUTADAS':
        actividades = actividades.filter(estado__in=['REGISTRADA', 'RECHAZADA'])
    elif filtros['estado'] == 'COMPLETADAS':
        actividades = actividades.filter(estado='VALIDADA')
    elif filtros['estado'] != 'TODOS':
        actividades = actividades.filter(estado__in=ESTADOS_PENDIENTES)
    if filtros['territorio'].isdigit():
        actividades = actividades.filter(territorio_id=filtros['territorio'])
    if filtros['mios'] == '1':
        actividades = actividades.filter(Q(usuario=request.user) | Q(encargado=request.user))

    # Primero las que tienen fecha (la más próxima arriba); al final, las que aún no tienen fecha de ejecución
    actividades = actividades.select_related('solicitud').order_by(F('fecha_realizacion').asc(nulls_last=True), 'fecha')
    lista = [fila_actividad(a, request.user) for a in actividades]
    data = {
        'actividades': lista,
        'delegacion_actual': f"Delegación {nombre}",
        'codigo_delegacion': codigo,
        'filtros': filtros,
        'responsables': responsables,
        'territorios': territorios,
        'estados_filtro': ESTADOS_FILTRO_TUBO,
    }
    return render(request, 'actividades/tubo_trabajo.html', data)


# ---------------------------------------------------------------------------
# Registro de Atenciones (Gestión Social)
# ---------------------------------------------------------------------------
def atenciones_visibles(usuario, delegacion):
    """Admin y Coordinador: todas (o la delegación elegida arriba). Delegado y Funcionario: las de su delegación."""
    atenciones = AtencionSocial.objects.select_related('usuario', 'usuario__delegacion', 'tipo_atencion', 'subtipo_atencion')
    if usuario.tiene_rol(['Admin', 'Coordinador']):
        if delegacion is not None:
            atenciones = atenciones.filter(usuario__delegacion=delegacion)
    else:
        atenciones = atenciones.filter(usuario__delegacion_id=usuario.delegacion_id)
    return atenciones


def puede_editar_atencion(usuario, atencion):
    """La modifica quien la registró o el Administrador."""
    return usuario.es_administrador() or (usuario.puede_registrar() and atencion.usuario_id == usuario.pk)


def gestion_social(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Funcionario']):
        return acceso_denegado(request, 'Registro de Atenciones')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    atenciones = atenciones_visibles(request.user, delegacion).prefetch_related('actividades')
    # "Ver solicitud" desde una actividad: muestra solo esa
    solicitud_id = request.GET.get('solicitud', '')
    if solicitud_id.isdigit():
        atenciones = atenciones.filter(pk=solicitud_id)
    texto = request.GET.get('q', '').strip()
    if texto:
        atenciones = atenciones.filter(Q(nombre_solicitante__icontains=texto) | Q(rut_solicitante__icontains=texto))

    lista = []
    for atencion in atenciones:
        fila = {
            'id': atencion.pk,
            'fecha_atencion': atencion.fecha,
            'registrada_por': atencion.usuario,
            'tipo_atencion': atencion.tipo_atencion.nombre,
            'sub_atencion': atencion.subtipo_atencion or '-',
            'nombre_usuario': atencion.nombre_solicitante,
            'rut_usuario': atencion.rut_solicitante,
            'fono': atencion.telefono_solicitante,
            'requiere_visita': atencion.requiere_visita,
            'codigo': atencion.codigo(),
            'estado': atencion.estado(),
            'estado_texto': atencion.get_estado_display(),
            'actividades': list(atencion.actividades.all()),
            'editable': puede_editar_atencion(request.user, atencion),
            'eliminable': request.user.es_administrador(),
        }
        lista.append(fila)

    data = {
        'atenciones': lista,
        'filtro_solicitud': solicitud_id if solicitud_id.isdigit() else '',
        'q': texto,
        'delegacion_actual': nombre,
    }
    return render(request, 'actividades/gestion_social.html', data)


def atencion_form(request, atencion=None):
    nueva = atencion is None
    if request.method == 'POST':
        form = AtencionForm(request.POST, instance=atencion)
        if form.is_valid():
            antes = '' if nueva else f"{atencion}"
            atencion = form.save(commit=False)
            if nueva:
                atencion.usuario = request.user  # queda registrada a nombre de quien inició sesión
            atencion.save()
            registrar_auditoria(request.user, 'CREACION' if nueva else 'MODIFICACION', 'AtencionSocial', atencion.pk,
                                antes, f"{atencion}")
            messages.success(request, f"Atención {atencion.codigo()} {'registrada' if nueva else 'actualizada'}.")
            return redirect('actividades:gestion_social')
    else:
        form = AtencionForm(instance=atencion)
    return render(request, 'actividades/atencion_form.html', {'form': form, 'object': atencion})


def atencion_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    # Agregan atenciones el Funcionario y el Administrador; el Delegado y el Coordinador solo las visualizan
    if not request.user.puede_registrar():
        return acceso_denegado(request, 'Agregar Atención')
    return atencion_form(request)


def atencion_editar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    atencion = get_object_or_404(AtencionSocial, pk=pk)
    if not puede_editar_atencion(request.user, atencion):
        return acceso_denegado(request, f"la atención {atencion.codigo()}")
    return atencion_form(request, atencion)


def atencion_eliminar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.es_administrador():
        return acceso_denegado(request, 'Eliminar Atención')
    atencion = get_object_or_404(AtencionSocial, pk=pk)
    if request.method == 'POST':
        descripcion = f"{atencion}"
        atencion.delete()  # las actividades vinculadas quedan, sin solicitud
        registrar_auditoria(request.user, 'ELIMINACION', 'AtencionSocial', pk, descripcion, '')
        messages.success(request, "Atención eliminada.")
    return redirect('actividades:gestion_social')


# ---------------------------------------------------------------------------
# Verificación de evidencias
# ---------------------------------------------------------------------------
def verificacion(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_verificar():
        return acceso_denegado(request, 'Verificación')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    pendientes = Evidencia.objects.filter(estado_revision='PENDIENTE').select_related(
        'actividad', 'actividad__usuario', 'actividad__item').order_by('fecha')
    if not request.user.es_administrador():
        # El Delegado verifica solo las actividades de su delegación
        if request.user.delegacion is None:
            messages.warning(request, "No tiene delegación asignada: no hay evidencias que pueda verificar.")
            pendientes = pendientes.none()
        else:
            pendientes = pendientes.filter(actividad__usuario__delegacion=request.user.delegacion)
    elif delegacion is not None:
        pendientes = pendientes.filter(actividad__usuario__delegacion=delegacion)

    lista = []
    seleccionada = None
    id_seleccionada = request.GET.get('evidencia_id', '')
    for evidencia in pendientes:
        fila = {
            'id': evidencia.pk,
            'codigo': evidencia.codigo(),
            'fecha_registro': evidencia.fecha,
            'funcionario': evidencia.actividad.usuario,
            'item': evidencia.actividad.item.nombre,
            'descripcion': evidencia.actividad.solicitud_problema,
            'accion': evidencia.actividad.accion,
            'actividad_id': evidencia.actividad_id,
            'folio': evidencia.actividad.folio(),
            'version': evidencia.version,
            'comentario': evidencia.comentario,
            'depende_externos': evidencia.actividad.depende_externos,
            'fecha_realizacion': evidencia.actividad.fecha_realizacion,
            'encargado': evidencia.actividad.encargado,
            'imagen': evidencia.imagen,
        }
        lista.append(fila)
        if str(evidencia.pk) == id_seleccionada:
            seleccionada = fila

    data = {
        'evidencias_pendientes': lista,
        'evidencia_seleccionada': seleccionada,
    }
    return render(request, 'actividades/verificacion.html', data)


def validar_evidencia(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_verificar():
        return acceso_denegado(request, 'Verificación')
    if request.method != 'POST':
        return redirect('actividades:verificacion')

    evidencia = get_object_or_404(Evidencia, pk=pk)
    if not request.user.es_administrador():
        delegacion_actividad = evidencia.actividad.usuario.delegacion_id
        if request.user.delegacion_id is None or request.user.delegacion_id != delegacion_actividad:
            messages.error(request, "Solo puede verificar evidencias de funcionarios de su delegación.")
            return redirect('actividades:verificacion')
    decision = request.POST.get('decision', '')
    observacion = request.POST.get('observacion', '').strip()

    if evidencia.estado_revision != 'PENDIENTE' or Validacion.objects.filter(evidencia=evidencia).exists():
        messages.error(request, "Esta evidencia ya fue revisada.")
        return redirect('actividades:verificacion')
    if evidencia.actividad.es_responsable(request.user):
        messages.error(request, "No puede validar una actividad que usted registró o tiene a su cargo.")
        return redirect('actividades:verificacion')
    # Rechazar invalida la evidencia, no la actividad: se debe cumplir igual y el funcionario la resube
    if decision not in ['APROBAR', 'RECHAZAR']:
        messages.error(request, "Decisión no válida.")
        return redirect('actividades:verificacion')
    if decision == 'RECHAZAR' and not observacion:
        messages.error(request, "Para rechazar la ejecución debe escribir una observación que explique el motivo.")
        return redirect(reverse('actividades:verificacion') + f"?evidencia_id={evidencia.pk}")

    Validacion.objects.create(evidencia=evidencia, decision=decision, observacion=observacion, verificador=request.user)
    nuevos_estados = {'APROBAR': 'APROBADA', 'RECHAZAR': 'RECHAZADA'}
    anterior = evidencia.estado_revision
    evidencia.estado_revision = nuevos_estados[decision]
    evidencia.save()
    evidencia.actividad.sincronizar_estado()
    registrar_auditoria(request.user, 'MODIFICACION', 'Evidencia', evidencia.pk, anterior, evidencia.estado_revision)

    if decision == 'APROBAR':
        messages.success(request, f"Actividad {evidencia.actividad.folio()} validada: queda completada.")
    else:
        messages.success(request, f"Ejecución {evidencia.codigo()} rechazada: el funcionario debe registrarla de nuevo.")
    return redirect('actividades:verificacion')
