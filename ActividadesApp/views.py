from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Q, F
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.choices import ESTADOS_PENDIENTES
# validar_imagen se importa aquí porque las pruebas la usan como ActividadesApp.views.validar_imagen
from ActividadesApp.forms import (ActividadForm, EvidenciaForm, FechaRealizacionForm, ComentarioForm, EncargadoForm,
                                AtencionForm, solicitudes_para, validar_imagen)
from ActividadesApp.models import (Actividad, Evidencia, Validacion, AtencionSocial, ComentarioActividad,
                                Territorio, DIAS_POR_VENCER)
from AuditoriaApp.registro import registrar_auditoria
from IndicadoresApp.calculos import indicadores_usuario, total_ponderado
from IndicadoresApp.models import periodo_vigente
from UsuarioApp.funciones import opciones_delegacion
from UsuarioApp.funciones import delegacion_seleccionada, acceso_denegado, permiso_requerido
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
    """Delegado (en su delegación), Coordinador y Admin asignan encargado a una actividad sin evidencia."""
    if not usuario.puede_asignar_encargado() or actividad.estado not in ESTADOS_PENDIENTES + ['RECHAZADA']:
        return False
    if usuario.es_delegado():
        return misma_delegacion(usuario, actividad)
    return True


def puede_cambiar_puntaje(usuario, actividad):
    """Cambian si una actividad validada suma puntaje: el Administrador y el Delegado de su delegación, nunca su
    propio responsable. Las gestiones del Delegado no suman nunca."""
    if not actividad.completada() or actividad.es_gestion or actividad.validacion_vigente() is None:
        return False
    if not usuario.puede_verificar() or actividad.es_responsable(usuario):
        return False
    return usuario.es_administrador() or misma_delegacion(usuario, actividad)


def candidatos_encargado(usuario, actividad):
    """Funcionarios activos que se pueden asignar: el Delegado elige entre los de su delegación;
    el Coordinador y el Admin, entre todos los de las delegaciones registradas."""
    funcionarios = Usuario.objects.filter(is_active=True, roles_asignados__rol__codigo='Funcionario').select_related('delegacion')
    if usuario.es_delegado():
        funcionarios = funcionarios.filter(delegacion_id=usuario.delegacion_id)
    return funcionarios.distinct().order_by('delegacion__nombre', 'first_name', 'last_name')


def fila_actividad(actividad, usuario):
    """Adapta una actividad a los nombres que usan las tablas de las plantillas."""
    evidencia = actividad.evidencia_vigente()
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
        'tiene_foto': bool(evidencia and evidencia.imagen),
        'solicitud': actividad.solicitud,
        'puede_registrar_evidencia': actividad.puede_registrar_evidencia(usuario),
        'es_gestion': actividad.es_gestion,
        # Validada, pero quien validó marcó que no lleva punto (por ejemplo, la coordinación previa a un taller)
        'sin_puntaje': actividad.completada() and not actividad.es_gestion and not actividad.otorga_puntaje(),
    }


# ---------------------------------------------------------------------------
# Mi Gestión: todo lo del usuario conectado en una sola pantalla (avance, actividades, metas y mantenedores)
# ---------------------------------------------------------------------------
@permiso_requerido('ActividadesApp.view_actividad', 'Mi Gestión')
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
        'en_revision': mias.filter(estado='EVIDENCIA_INGRESADA').count(),
    }
    metas = [{
        'item_nombre': ind.meta.item.nombre,
        'ponderador': ind.meta.ponderador,
        'meta_trimestre': ind.meta.valor_objetivo,
        # Meta ajustada a los días trabajados (vacaciones, días administrativos y licencias la reducen)
        'meta_ajustada': ind.objetivo_ajustado(),
        'avance_actual': ind.avance_actual,
        'porcentaje_cumplimiento': ind.cumplimiento,
        'cumplimiento_ponderado': ind.cumplimiento_ponderado,
        'en_tope': ind.en_tope(),
    } for ind in indicadores]
    dias_ausente = indicadores[0].dias_ausencia() if indicadores else 0

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
                'en_revision': de_la_delegacion.filter(estado='EVIDENCIA_INGRESADA').count(),
            }

    data = {
        'resumen': resumen,
        'periodo': periodo,
        'metas': metas,
        'mis_actividades': mis_actividades,
        'pendientes': pendientes,
        # Admin y Coordinador no tienen pestañas propias: solo ven las actividades de todas las delegaciones
        'vista_global': vista_global,
        'muestra_mis_actividades': not vista_global and (usuario.puede_agregar_actividad() or bool(mis_actividades)),
        'metas_en_tope': [meta['item_nombre'] for meta in metas if meta['en_tope']],
        'dias_ausente': dias_ausente,
        'tope': periodo.tope_cumplimiento if periodo else None,
        've_delegacion': ve_delegacion,
        'actividades_delegacion': actividades_delegacion,
        'funcionarios_delegacion': funcionarios_delegacion,
        'filtro_funcionario': filtro_funcionario,
        'opciones_delegacion': opciones_delegacion(),
        'delegacion_activa': codigo,
        'delegacion_nombre': nombre,
    }
    # Pestaña abierta (?pestana=): solo una de las que tiene el perfil; si no, Resumen
    disponibles = ['resumen']
    if data['muestra_mis_actividades']:
        disponibles += ['mias', 'pendientes']
    if not vista_global:
        disponibles.append('metas')
    if ve_delegacion:
        disponibles.append('delegacion')
    pedida = request.GET.get('pestana', '')
    data['pestana'] = pedida if pedida in disponibles else 'resumen'
    # Tablero del perfil (lo que antes era Indicadores): tarjetas de avance y pestaña Resumen
    from IndicadoresApp.views import datos_tablero
    data.update(datos_tablero(request))
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


def guardar_evidencia(actividad, usuario, comentario, imagen):
    """Crea la evidencia (nueva versión si ya había uno) y deja la actividad en revisión."""
    anterior = actividad.evidencia_vigente()
    evidencia = Evidencia.objects.create(
        actividad=actividad, comentario=comentario, imagen=imagen or '',
        version=(anterior.version + 1) if anterior else 1, reemplaza_a=anterior)
    registrar_auditoria(usuario, 'CREACION', 'Evidencia', evidencia.pk, '', evidencia)
    return evidencia


@permiso_requerido('ActividadesApp.add_actividad', 'Registrar Actividad')
def actividad_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    # Registran actividades el Funcionario y el Admin; el Delegado ingresa sus gestiones (sin puntaje) y las
    # felicitaciones de usuarios. El Coordinador solo supervisa.
    if not request.user.puede_agregar_actividad():
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
                nombre_usuario=datos['nombre_usuario'],
                telefono_usuario=datos['telefono_usuario'],
                es_gestion=form.es_gestion(),
            )
            registrar_auditoria(request.user, 'CREACION', 'Actividad', actividad.pk, '', f"{actividad} [{actividad.estado}]")
            if form.solicitud_encontrada is not None:
                messages.info(request, f"La persona atendida ya estaba en el Registro de Atenciones: la actividad quedó "
                                       f"vinculada a la solicitud {form.solicitud_encontrada.codigo()}.")
            avisar_tope(request, actividad)

            if form.es_felicitacion():
                # El Delegado informa la felicitación con respaldo formal: queda validada y suma al funcionario felicitado
                evidencia = guardar_evidencia(actividad, request.user, datos['comentario'].strip(), datos['imagen'])
                Validacion.objects.create(evidencia=evidencia, decision='APROBAR', otorga_puntaje=True,
                                          observacion="Felicitación informada por el Delegado.", verificador=request.user)
                evidencia.estado_revision = 'APROBADA'
                evidencia.save()
                actividad.sincronizar_estado()
                registrar_auditoria(request.user, 'MODIFICACION', 'Evidencia', evidencia.pk, 'PENDIENTE', 'APROBADA (felicitación)')
                messages.success(request, f"Felicitación {actividad.folio()} registrada para {actividad.encargado}.")
                return redirect('actividades:mi_gestion')

            if estado == 'EVIDENCIA_INGRESADA':
                guardar_evidencia(actividad, request.user, datos['comentario'].strip(), datos['imagen'])
                actividad.sincronizar_estado()
                if actividad.es_gestion:
                    messages.success(request, f"Gestión {actividad.folio()} registrada. Las gestiones del Delegado no "
                                              "suman puntaje.")
                else:
                    messages.success(request, f"Actividad {actividad.folio()} registrada con su evidencia. "
                                              "Queda a la espera de la validación del Delegado.")
                return redirect('actividades:mi_gestion')
            if actividad.depende_externos:
                if actividad.fecha_realizacion:
                    messages.success(request, f"Actividad {actividad.folio()} ingresada al Tubo de Trabajo con fecha de "
                                            f"realización {actividad.fecha_realizacion:%d/%m/%Y}.")
                else:
                    messages.success(request, f"Actividad {actividad.folio()} ingresada al Tubo de Trabajo. "
                                            "La fecha de realización se puede agregar después.")
                return redirect('actividades:tubo_trabajo')
            messages.success(request, f"Actividad {actividad.folio()} programada para el "
                                    f"{actividad.fecha_realizacion:%d/%m/%Y}. Queda pendiente hasta que se realice.")
            return redirect('actividades:mi_gestion')
    else:
        inicial = {'depende_externos': request.GET.get('tubo') == '1'}
        if inicial['depende_externos']:
            inicial['fecha_realizacion'] = None  # en el Tubo la fecha de realización parte vacía
        if request.GET.get('solicitud', '').isdigit():
            inicial['solicitud'] = request.GET['solicitud']  # "Crear actividad" desde el Registro de Atenciones
        form = ActividadForm(usuario=request.user, initial=inicial)

    return render(request, 'actividades/actividad_form.html', {
        'form': form, 'hoy': timezone.localdate(), 'es_delegado': request.user.es_delegado()})


def avisar_tope(request, actividad):
    """Si el ítem de la actividad ya llegó al tope (120%) para su responsable, se avisa: más actividades de ese
    ítem ya no suben el puntaje."""
    if actividad.es_gestion or actividad.periodo is None:
        return
    responsable = actividad.responsable()
    for indicador in indicadores_usuario(responsable, actividad.periodo, timezone.localdate()):
        if indicador.meta.item_id == actividad.item_id and indicador.en_tope():
            messages.warning(request, f"El ítem '{actividad.item.nombre}' ya llegó al tope de "
                                      f"{actividad.periodo.tope_cumplimiento:.0f}% para {responsable}: nuevas "
                                      "actividades de este ítem no suben el puntaje. Conviene enfocarse en los ítems "
                                      "con menor avance.")


# ---------------------------------------------------------------------------
# Editar actividad
# ---------------------------------------------------------------------------
@permiso_requerido('ActividadesApp.change_actividad', 'Editar Actividad')
def actividad_editar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')

    if not request.user.tiene_rol(['Admin']):
        return acceso_denegado(
            request, 'Editar Actividad'
        )
    actividad = get_object_or_404(Actividad, pk=pk)

    if actividad.completada():
        messages.error(
            request, 'Las actividades validadas no pueden modificarse.'
        )
        return redirect('actividades:mi_gestion')

    if request.method == 'POST':
        form = ActividadForm(
            request.POST,
            request.FILES,
            usuario=request.user,
            actividad=actividad
        )

        if form.is_valid():
            datos = form.cleaned_data
            antes = str(actividad)

            actividad.solicitud_problema = datos['solicitud_problema'].strip()
            actividad.accion = datos['accion'].strip()
            actividad.item = datos['item']
            actividad.territorio = datos['territorio']
            actividad.depende_externos = datos['depende_externos']
            actividad.fecha_realizacion = datos['fecha_realizacion']
            actividad.encargado = datos['encargado']
            actividad.solicitud = datos['solicitud']
            actividad.nombre_usuario = datos['nombre_usuario']
            actividad.telefono_usuario = datos['telefono_usuario']
            actividad.save()
            # Si queda con fecha de hoy o anterior y aún no tenía evidencia, se agrega como en actividad_crear            
            if datos['comentario'] and actividad.evidencia_vigente() is None:                
                guardar_evidencia(actividad, request.user, datos['comentario'].strip(), datos['imagen'])            
            # El estado se recalcula según la fecha, el Tubo y la evidencia (EN_TUBO, PROGRAMADA, EVIDENCIA_INGRESADA...)            
            actividad.sincronizar_estado()

            registrar_auditoria(
                request.user,
                'MODIFICACION',
                'Actividad',
                actividad.pk,
                antes,
                str(actividad)
            )
            messages.success(
                request, 'Actividad actualizada correctamente.'
            )
            return redirect('actividades:mi_gestion')
    else:
        form = ActividadForm(
            usuario=request.user,
            initial={
                'solicitud_problema': actividad.solicitud_problema,
                'accion': actividad.accion,
                'item': actividad.item,
                'territorio': actividad.territorio,
                'depende_externos': actividad.depende_externos,
                'fecha_realizacion': actividad.fecha_realizacion,
                'encargado': actividad.encargado,
                'solicitud': actividad.solicitud,
                'nombre_usuario': actividad.nombre_usuario,
                'telefono_usuario': actividad.telefono_usuario,
                'comentario': actividad.evidencia_vigente().comentario if actividad.evidencia_vigente() else '',
            })

    return render(request,
        'actividades/actividad_form.html',
        {
            'form': form,
            'actividad': actividad,
            'modo_edicion': True,
            'hoy': timezone.localdate(),
        }
    )


# ---------------------------------------------------------------------------
# Eliminar actividad
# ---------------------------------------------------------------------------
@permiso_requerido('ActividadesApp.delete_actividad', 'Eliminar Actividad')
def actividad_eliminar(request, pk):
    if not request.user.tiene_rol(["Admin"]):
        return acceso_denegado(
            request, "No tiene permisos para eliminar actividades."
        )

    actividad = get_object_or_404(
        Actividad, pk=pk
    )

    if actividad.completada():
        messages.error(
            request, "Una actividad validada no puede eliminarse."
        )
        return redirect(
            "actividades:mi_gestion"
        )
    # Solo se elimina con POST (formulario con confirmación); un link o una recarga no borran nada    
    if request.method != 'POST':        
        return redirect('actividades:actividad_detalle', pk=actividad.pk)    
    
    descripcion = str(actividad)    
    actividad.delete()    
    registrar_auditoria(request.user, 'ELIMINACION', 'Actividad', pk, descripcion, '')

    messages.success(
        request, "Actividad eliminada correctamente."
    )

    return redirect(
        "actividades:mi_gestion"
    )


# ---------------------------------------------------------------------------
# Detalle de la actividad: evidencias, fecha, encargado y bitácora
# ---------------------------------------------------------------------------
@permiso_requerido('ActividadesApp.view_actividad', 'Detalle Actividad')
def actividad_detalle(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    actividad = get_object_or_404(Actividad.objects.select_related('usuario', 'item', 'periodo', 'encargado', 'territorio'), pk=pk)
    if not puede_ver_actividad(request.user, actividad):
        return acceso_denegado(request, f"la actividad {actividad.folio()}")

    evidencias = []
    for evidencia in actividad.evidencias.order_by('-version'):
        validacion = getattr(evidencia, 'validacion', None)
        evidencias.append({
            'codigo': evidencia.codigo(),
            'version': evidencia.version,
            'fecha': evidencia.fecha,
            'comentario': evidencia.comentario,
            'imagen': evidencia.imagen,
            'estado': evidencia.get_estado_revision_display(),
            'estado_codigo': evidencia.estado_revision,
            'observacion': validacion.observacion if validacion else '',
            'verificador': validacion.verificador if validacion else None,
        })

    usuario = request.user
    data = {
        'actividad': actividad,
        'evidencias': evidencias,
        'comentarios': actividad.comentarios.select_related('usuario'),
        'puede_registrar_evidencia': actividad.puede_registrar_evidencia(usuario),
        'puede_comentar': puede_comentar(usuario, actividad),
        'puede_programar': puede_programar(usuario, actividad),
        'puede_asignar': puede_asignar_encargado(usuario, actividad),
        'puede_cambiar_puntaje': puede_cambiar_puntaje(usuario, actividad),
        'otorga_puntaje': actividad.otorga_puntaje(),
        'form_evidencia': EvidenciaForm(),
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


@permiso_requerido('ActividadesApp.add_actividad', 'Agregar Evidencia')
def registrar_evidencia(request, pk):
    """Quien registró la actividad o su encargado deja constancia de que se hizo (comentario + foto opcional).
    Sirve para un compromiso, una actividad del Tubo o una evidencia rechazada."""
    if not request.user.is_authenticated:
        return redirect('users:login')
    actividad = get_object_or_404(Actividad, pk=pk)
    if request.method != 'POST':
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    if not actividad.puede_registrar_evidencia(request.user):
        messages.error(request, "Solo quien registró la actividad o su encargado agregan la evidencia, "
                                "y solo si está pendiente o fue rechazada.")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    form = EvidenciaForm(request.POST, request.FILES)
    if not form.is_valid():
        mostrar_errores(request, form)
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    estado_anterior = actividad.estado
    guardar_evidencia(actividad, request.user, form.cleaned_data['comentario'], form.cleaned_data['imagen'])
    if estado_anterior in ESTADOS_PENDIENTES:
        # Un compromiso cuenta en el periodo en que se realiza, y su fecha de realización es hoy
        periodo = periodo_vigente()
        if periodo is not None and not periodo.periodo_cerrado():
            actividad.periodo = periodo
        actividad.fecha_realizacion = timezone.localdate()
    actividad.sincronizar_estado()
    registrar_auditoria(request.user, 'MODIFICACION', 'Actividad', actividad.pk, estado_anterior, actividad.estado)

    if estado_anterior == 'RECHAZADA':
        messages.success(request, f"Nueva evidencia de {actividad.folio()} enviada a validación.")
    else:
        messages.success(request, f"Evidencia de {actividad.folio()} agregada: espera la validación del Delegado.")
    return redirect('actividades:actividad_detalle', pk=actividad.pk)


@permiso_requerido('ActividadesApp.view_actividad', 'Asignar Fecha')
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


@permiso_requerido('ActividadesApp.asignar_encargado', 'Asignar Encargado')
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


@permiso_requerido('ActividadesApp.add_comentarioactividad', 'Comentar Actividad')
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
    ('SIN_FECHA', 'Sin fecha de realización'),
    ('CON_FECHA', 'Con fecha de realización'),
    ('VENCIDOS', 'Con fecha vencida'),
    ('CON_EVIDENCIA', 'Evidencia ingresada'),
    ('COMPLETADAS', 'Completadas (validadas)'),
    ('TODOS', 'Todas'),
]


@permiso_requerido('ActividadesApp.view_actividad', 'Tubo de Trabajo')
def tubo_trabajo(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Funcionario']):
        return acceso_denegado(request, 'Tubo de Trabajo')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    usuario = request.user
    # El Funcionario solo ve lo suyo (lo que registró o donde es encargado), igual que en Mi Gestión,
    # y solo filtra por estado. Admin y Coordinador ven todo o la delegación elegida; el Delegado, la suya.
    solo_lo_suyo = not usuario.tiene_rol(['Admin', 'Coordinador', 'Delegado'])
    # El Tubo son las actividades que dependen de factores externos
    actividades = Actividad.objects.filter(depende_externos=True).select_related('usuario', 'encargado', 'territorio', 'item')
    if solo_lo_suyo:
        actividades = actividades.filter(Q(usuario=usuario) | Q(encargado=usuario))
    elif delegacion is not None:
        actividades = actividades.filter(usuario__delegacion=delegacion)
    elif not usuario.tiene_rol(['Admin', 'Coordinador']):
        # Delegado sin delegación asignada: solo lo propio
        actividades = actividades.filter(Q(usuario=usuario) | Q(encargado=usuario))

    filtros = {
        'responsable': request.GET.get('responsable', '').strip(),
        'estado': request.GET.get('estado', ''),
        'territorio': request.GET.get('territorio', ''),
        'mios': request.GET.get('mios', '')
    }
    if solo_lo_suyo:
        # Aunque lleguen en la dirección, el Funcionario no usa estos filtros
        filtros.update({'responsable': '', 'territorio': '', 'mios': ''})

    # Territorios del filtro: los de la delegación elegida, o los de todas si está en GENERAL
    territorios = Territorio.objects.filter(estado='ACTIVO').select_related('delegacion')
    if delegacion is not None:
        territorios = territorios.filter(delegacion=delegacion)
    territorios = territorios.order_by('delegacion__nombre_visible', 'nombre')

    hoy = timezone.localdate()
    if filtros['responsable']:
        # Buscador: nombre, apellido o RUT de quien la registró o de su encargado
        texto = filtros['responsable']
        actividades = actividades.filter(
            Q(usuario__first_name__icontains=texto) | Q(usuario__last_name__icontains=texto) |
            Q(usuario__username__icontains=texto) | Q(encargado__first_name__icontains=texto) |
            Q(encargado__last_name__icontains=texto) | Q(encargado__username__icontains=texto)).distinct()
    if filtros['estado'] == 'SIN_FECHA':
        actividades = actividades.filter(estado='EN_TUBO')
    elif filtros['estado'] == 'CON_FECHA':
        actividades = actividades.filter(estado='PROGRAMADA')
    elif filtros['estado'] == 'VENCIDOS':
        actividades = actividades.filter(estado='PROGRAMADA', fecha_realizacion__lt=hoy)
    elif filtros['estado'] == 'CON_EVIDENCIA':
        actividades = actividades.filter(estado__in=['EVIDENCIA_INGRESADA', 'RECHAZADA'])
    elif filtros['estado'] == 'COMPLETADAS':
        actividades = actividades.filter(estado='VALIDADA')
    elif filtros['estado'] != 'TODOS':
        actividades = actividades.filter(estado__in=ESTADOS_PENDIENTES)
    if filtros['territorio'].isdigit():
        actividades = actividades.filter(territorio_id=filtros['territorio'])
    if filtros['mios'] == '1':
        actividades = actividades.filter(Q(usuario=request.user) | Q(encargado=request.user))

    # Primero las que tienen fecha (la más próxima arriba); al final, las que aún no tienen fecha de realización
    actividades = actividades.select_related('solicitud').order_by(F('fecha_realizacion').asc(nulls_last=True), 'fecha')
    lista = [fila_actividad(a, request.user) for a in actividades]
    data = {
        'actividades': lista,
        'delegacion_actual': f"Delegación {nombre}",
        'codigo_delegacion': codigo,
        'filtros': filtros,
        'territorios': territorios,
        'estados_filtro': ESTADOS_FILTRO_TUBO,
        'solo_lo_suyo': solo_lo_suyo,
        'por_delegacion': delegacion is None,  # en GENERAL los territorios se agrupan por delegación
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


def puede_ver_atencion(usuario, atencion):
    """Ver el detalle: Admin y Coordinador, todas; Delegado, las de su delegación; Funcionario, las que registró."""
    if usuario.tiene_rol(['Admin', 'Coordinador']):
        return True
    if usuario.es_delegado():
        return atencion.usuario is not None and atencion.usuario.delegacion_id == usuario.delegacion_id
    return atencion.usuario_id == usuario.pk


def puede_editar_atencion(usuario, atencion):
    """La modifica quien la registró o el Administrador."""
    return usuario.es_administrador() or (usuario.puede_registrar() and atencion.usuario_id == usuario.pk)


@permiso_requerido('ActividadesApp.view_atencionsocial', 'Gestión Social')
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
            'visible': puede_ver_atencion(request.user, atencion),
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


def actividades_vinculables(usuario, atencion):
    """Actividades que se pueden vincular a la atención: sin solicitud todavía y de la misma delegación que la
    atención (el Delegado, además, solo las de su delegación)."""
    actividades = Actividad.objects.filter(solicitud__isnull=True).select_related('usuario', 'item')
    delegacion = atencion.delegacion()
    if usuario.es_delegado():
        actividades = actividades.filter(usuario__delegacion_id=usuario.delegacion_id)
    if delegacion is not None:
        actividades = actividades.filter(usuario__delegacion=delegacion)
    return actividades


def buscar_para_vincular(usuario, atencion, q):
    """Buscador del detalle de la atención: folio (ACT12 o 12), acción, problema o nombre/RUT de quien la registró."""
    filtro = (Q(accion__icontains=q) | Q(solicitud_problema__icontains=q) | Q(usuario__first_name__icontains=q)
              | Q(usuario__last_name__icontains=q) | Q(usuario__username__icontains=q))
    digitos = ''.join(c for c in q if c.isdigit())
    if q.upper() == 'ACT':  # solo el prefijo del folio: todas las que se pueden vincular
        filtro = Q()
    elif q.upper().startswith('ACT') and digitos:
        filtro = Q(pk=int(digitos))
    elif digitos and digitos == q:
        filtro = filtro | Q(pk=int(digitos))
    return actividades_vinculables(usuario, atencion).filter(filtro).order_by('-fecha')[:20]


@permiso_requerido('ActividadesApp.view_atencionsocial', 'Vincular Actividad')
def atencion_vincular(request, pk):
    """Vincula una actividad ya registrada a la atención (Admin, Coordinador y Delegado)."""
    atencion = get_object_or_404(AtencionSocial, pk=pk)
    detalle = reverse('actividades:atencion_detalle', args=[atencion.pk])
    if request.method != 'POST':
        return redirect(detalle)
    if not request.user.puede_vincular_atenciones() or not puede_ver_atencion(request.user, atencion):
        return acceso_denegado(request, 'Vincular Actividad')
    actividad = actividades_vinculables(request.user, atencion).filter(pk=request.POST.get('actividad', '0') or 0).first()
    if actividad is None:
        messages.error(request, "Esa actividad no se puede vincular: ya tiene una solicitud o es de otra delegación.")
        return redirect(detalle)
    actividad.solicitud = atencion
    actividad.save(update_fields=['solicitud'])
    registrar_auditoria(request.user, 'MODIFICACION', 'Actividad', actividad.pk, 'Sin solicitud social',
                        f"Vinculada a {atencion.codigo()}")
    messages.success(request, f"Actividad {actividad.folio()} vinculada a la atención {atencion.codigo()}.")
    return redirect(detalle)


@permiso_requerido('ActividadesApp.view_atencionsocial', 'Detalle de Atención Social')
def atencion_detalle(request, pk):
    """Ficha de una solicitud social: datos de la persona, quién la registró, su estado y las actividades con que
    se atiende."""
    atencion = get_object_or_404(AtencionSocial.objects.select_related(
        'usuario', 'usuario__delegacion', 'tipo_atencion', 'subtipo_atencion'), pk=pk)
    if not puede_ver_atencion(request.user, atencion):
        return acceso_denegado(request, f"la atención {atencion.codigo()}")
    actividades = atencion.actividades.select_related('usuario', 'encargado', 'item', 'territorio').order_by('fecha')
    puede_vincular = request.user.puede_vincular_atenciones()
    q = request.GET.get('q', '').strip()
    data = {
        'atencion': atencion,
        'actividades': actividades,
        'puede_vincular': puede_vincular,
        'q': q,
        'candidatas': buscar_para_vincular(request.user, atencion, q) if puede_vincular and q else None,
        'editable': puede_editar_atencion(request.user, atencion),
        'eliminable': request.user.es_administrador(),
    }
    return render(request, 'actividades/atencion_detalle.html', data)


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


@permiso_requerido('ActividadesApp.add_atencionsocial', 'Crear Atención Social')
def atencion_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    # Agregan atenciones el Funcionario y el Administrador; el Delegado y el Coordinador solo las visualizan
    if not request.user.puede_registrar():
        return acceso_denegado(request, 'Agregar Atención')
    return atencion_form(request)


@permiso_requerido('ActividadesApp.add_atencionsocial', 'Editar Atención Social')
def atencion_editar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    atencion = get_object_or_404(AtencionSocial, pk=pk)
    if not puede_editar_atencion(request.user, atencion):
        return acceso_denegado(request, f"la atención {atencion.codigo()}")
    return atencion_form(request, atencion)


@permiso_requerido('ActividadesApp.delete_atencionsocial', 'Eliminar Atención Social')
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
@permiso_requerido('ActividadesApp.validar_evidencia', 'Verificación')
def verificacion(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_verificar():
        return acceso_denegado(request, 'Verificación')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    # Las gestiones del Delegado no se validan: no suman puntaje
    pendientes = Evidencia.objects.filter(estado_revision='PENDIENTE', actividad__es_gestion=False).select_related(
        'actividad', 'actividad__usuario', 'actividad__item', 'actividad__encargado').order_by('fecha')
    # Buscador por funcionario: nombre, apellido o RUT de quien la registró o de su encargado
    q = request.GET.get('q', '').strip()
    if q:
        pendientes = pendientes.filter(
            Q(actividad__usuario__first_name__icontains=q) | Q(actividad__usuario__last_name__icontains=q)
            | Q(actividad__usuario__username__icontains=q) | Q(actividad__encargado__first_name__icontains=q)
            | Q(actividad__encargado__last_name__icontains=q) | Q(actividad__encargado__username__icontains=q))
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
    hoy = timezone.localdate()
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
            'nombre_usuario': evidencia.actividad.nombre_usuario,
            'telefono_usuario': evidencia.actividad.telefono_usuario,
            'dias_sin_validar': (hoy - timezone.localtime(evidencia.fecha).date()).days,
        }
        lista.append(fila)
        if str(evidencia.pk) == id_seleccionada:
            seleccionada = fila

    data = {
        'evidencias_pendientes': lista,
        'evidencia_seleccionada': seleccionada,
        'q': q,
    }
    return render(request, 'actividades/verificacion.html', data)


@permiso_requerido('ActividadesApp.validar_evidencia', 'Validar Evidencia')
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
        messages.error(request, "Para rechazar la evidencia debe escribir una observación que explique el motivo.")
        return redirect(reverse('actividades:verificacion') + f"?evidencia_id={evidencia.pk}")
    # Al validar, el Delegado decide si la actividad suma puntaje: la acción realizada sí, la coordinación previa no
    puntaje = request.POST.get('otorga_puntaje', '')
    if decision == 'APROBAR' and puntaje not in ['SI', 'NO']:
        messages.error(request, "Indique si la actividad suma puntaje (Sí o No).")
        return redirect(reverse('actividades:verificacion') + f"?evidencia_id={evidencia.pk}")

    otorga = decision == 'APROBAR' and puntaje == 'SI'
    Validacion.objects.create(evidencia=evidencia, decision=decision, observacion=observacion, verificador=request.user,
                              otorga_puntaje=otorga)
    nuevos_estados = {'APROBAR': 'APROBADA', 'RECHAZAR': 'RECHAZADA'}
    anterior = evidencia.estado_revision
    evidencia.estado_revision = nuevos_estados[decision]
    evidencia.save()
    evidencia.actividad.sincronizar_estado()
    nuevo = evidencia.estado_revision + (f" (suma puntaje: {'Sí' if otorga else 'No'})" if decision == 'APROBAR' else '')
    registrar_auditoria(request.user, 'MODIFICACION', 'Evidencia', evidencia.pk, anterior, nuevo)

    if decision == 'APROBAR':
        texto = "suma puntaje" if otorga else "no suma puntaje"
        messages.success(request, f"Actividad {evidencia.actividad.folio()} validada: queda completada y {texto}.")
    else:
        messages.success(request, f"Evidencia {evidencia.codigo()} rechazada: el funcionario debe agregarla de nuevo.")
    return redirect('actividades:verificacion')


@permiso_requerido('ActividadesApp.validar_evidencia', 'Puntaje de la actividad')
def cambiar_puntaje(request, pk):
    """Después de validar, el Delegado de la delegación (o el Administrador) puede cambiar si la actividad suma
    puntaje. El cambio queda en la auditoría."""
    actividad = get_object_or_404(Actividad, pk=pk)
    if request.method != 'POST':
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    if not puede_cambiar_puntaje(request.user, actividad):
        messages.error(request, "No puede cambiar el puntaje de esta actividad.")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    puntaje = request.POST.get('otorga_puntaje', '')
    if puntaje not in ['SI', 'NO']:
        messages.error(request, "Indique si la actividad suma puntaje (Sí o No).")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    validacion = actividad.validacion_vigente()
    antes = 'Sí' if validacion.otorga_puntaje else 'No'
    validacion.otorga_puntaje = puntaje == 'SI'
    validacion.save(update_fields=['otorga_puntaje'])
    despues = 'Sí' if validacion.otorga_puntaje else 'No'
    registrar_auditoria(request.user, 'MODIFICACION', 'Validacion', validacion.pk, f"Suma puntaje: {antes}",
                        f"Suma puntaje: {despues}")
    messages.success(request, f"Actividad {actividad.folio()}: suma puntaje = {despues}.")
    return redirect('actividades:actividad_detalle', pk=actividad.pk)

