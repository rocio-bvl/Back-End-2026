from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import Actividad, Evidencia, Validacion, AtencionSocial, DIAS_POR_VENCER
from AuditoriaApp.registro import registrar_auditoria
from IndicadoresApp.calculos import indicadores_usuario, total_ponderado
from IndicadoresApp.models import periodo_vigente
from UsuarioApp.choices import opciones_delegacion
from UsuarioApp.funciones import delegacion_seleccionada, acceso_denegado
from UsuarioApp.models import Usuario, Catalogo


# ---------------------------------------------------------------------------
# Mi Gestión
# ---------------------------------------------------------------------------
def mi_gestion(request):
    if not request.user.is_authenticated:
        return redirect('users:login')

    usuario = request.user
    codigo, delegacion, nombre = delegacion_seleccionada(request)

    # Admin, Coordinador y Delegado ven las actividades de la delegación; el resto, solo las suyas
    actividades = Actividad.objects.select_related('item', 'usuario', 'usuario__delegacion')
    if usuario.tiene_rol(['Admin', 'Coordinador', 'Delegado']):
        if delegacion is not None:
            actividades = actividades.filter(usuario__delegacion=delegacion)
    else:
        actividades = actividades.filter(usuario=usuario)

    # Adaptamos cada actividad a los nombres que usa el template
    lista_actividades = []
    for act in actividades:
        evidencia = act.evidencia_vigente()
        codigo_evidencia = ''
        if evidencia is not None:
            codigo_evidencia = evidencia.codigo()
        lista_actividades.append({
            'id': act.pk,
            'codigo_meta': act.item.nombre,
            'nombre': act.accion,
            'delegacion': act.usuario.delegacion or 'General',
            'estado': act.get_estado_display(),
            'fecha': act.fecha,
            'solicitud_problema': act.solicitud_problema,
            'accion': act.accion,
            'contacto': act.contacto,
            'telefono': act.telefono,
            'ingreso_agenda_colectiva': act.ingreso_agenda_colectiva,
            'fecha_comprometida': act.fecha_comprometida,
            'codigo_evidencia': codigo_evidencia,
            'esta_validada': act.estado == 'VALIDADA',
            'estado_codigo': act.estado,
            'folio': act.folio(),
            'vencido': act.vencido(),
            'puede_subir': act.puede_subir_evidencia(usuario),
        })

    # Metas trimestrales del cargo del usuario conectado
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)
    indicadores = indicadores_usuario(usuario, periodo, hoy)
    metas = []
    for ind in indicadores:
        metas.append({
            'id': ind.meta.pk,
            'item_nombre': ind.meta.item.nombre,
            'ponderador': ind.meta.ponderador,
            'meta_trimestre': ind.meta.valor_objetivo,
            'avance_actual': ind.avance_actual,
            'porcentaje_cumplimiento': ind.cumplimiento,
            'cumplimiento_ponderado': ind.cumplimiento_ponderado,
            'ponderado': ind.cumplimiento_ponderado,
        })

    data = {
        'actividades': lista_actividades,
        'metas': metas,
        'total_ponderado': f"{total_ponderado(indicadores)}%",
        'opciones_delegacion': opciones_delegacion,
        'delegacion_activa': codigo,
        'delegacion_nombre': nombre,
    }
    return render(request, 'actividades/mi_gestion.html', data)


# ---------------------------------------------------------------------------
# Registrar actividad: con evidencia queda REGISTRADA; sin evidencia pasa al Tubo (compromiso)
# ---------------------------------------------------------------------------
def validar_imagen(imagen):
    """Devuelve la lista de errores de la fotografía (vacía si está bien)."""
    errores = []
    nombre_archivo = imagen.name.lower()
    if not (nombre_archivo.endswith('.jpg') or nombre_archivo.endswith('.jpeg') or nombre_archivo.endswith('.png')):
        errores.append("La fotografía debe ser JPG o PNG.")
    if imagen.size > settings.MAX_IMAGEN_EVIDENCIA:
        errores.append("La fotografía no puede superar 5 MB.")
    return errores


def fecha_de_texto(texto):
    """Convierte 'AAAA-MM-DD' en fecha. Devuelve None si viene vacío o mal escrito."""
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def actividad_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    # Registran actividades el Funcionario, el Coordinador y el Admin. El Delegado solo valida.
    if not request.user.puede_registrar():
        return acceso_denegado(request, 'Registrar Actividad')

    data_form = {'hoy': timezone.localdate(), 'al_tubo': request.GET.get('tubo') == '1'}

    if request.method == 'POST':
        solicitud = request.POST.get('solicitud_problema', '').strip()
        accion = request.POST.get('accion', '').strip()
        contacto = request.POST.get('contacto', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        territorio = request.POST.get('territorio', '').strip()
        al_tubo = request.POST.get('ingreso_agenda_colectiva') == 'on'
        imagen = request.FILES.get('evidencia_imagen')
        fecha_limite = fecha_de_texto(request.POST.get('fecha_comprometida', ''))
        item = Catalogo.objects.filter(pk=request.POST.get('item_comision') or 0, tipo='ITEM_GESTION', estado='ACTIVO').first()
        periodo = periodo_vigente()
        data_form['al_tubo'] = al_tubo

        # Validaciones (sin estas, MySQL en modo estricto lanzaría un error 500)
        errores = []
        if not solicitud:
            errores.append("Debe describir la actividad.")
        if not accion or len(accion) > 255:
            errores.append("La acción es obligatoria y no puede superar 255 caracteres.")
        if len(contacto) > 255:
            errores.append("El contacto no puede superar 255 caracteres.")
        if len(telefono) > 20:
            errores.append("El teléfono no puede superar 20 caracteres.")
        if len(territorio) > 150:
            errores.append("El territorio no puede superar 150 caracteres.")
        if item is None:
            errores.append("El ítem seleccionado no existe en el catálogo. Revise que se hayan cargado los datos iniciales.")
        if periodo is None:
            errores.append("No hay un periodo vigente para la fecha de hoy.")
        elif periodo.periodo_cerrado():
            errores.append("El periodo vigente está cerrado; no se pueden registrar actividades.")

        if al_tubo:
            # Sin evidencia: es un compromiso y necesita fecha límite de cumplimiento
            if imagen is not None:
                errores.append("Si la actividad pasa al Tubo de Trabajo no lleva evidencia todavía: "
                               "la subirá cuando la ejecute. Quite la fotografía o desmarque la opción.")
            if fecha_limite is None:
                errores.append("Indique la fecha límite comprometida para cumplir la actividad.")
            elif fecha_limite < timezone.localdate():
                errores.append("La fecha límite no puede ser anterior a hoy.")
        else:
            if imagen is None:
                errores.append("Adjunte la fotografía de evidencia. Si aún no puede realizar la actividad, "
                               "márquela para que pase al Tubo de Trabajo con una fecha límite.")
            else:
                errores.extend(validar_imagen(imagen))

        if errores:
            for error in errores:
                messages.error(request, error)
            return render(request, 'actividades/actividad_form.html', data_form)

        actividad = Actividad.objects.create(
            solicitud_problema=solicitud,
            accion=accion,
            contacto=contacto,
            telefono=telefono,
            territorio=territorio,
            ingreso_agenda_colectiva=al_tubo,
            fecha_comprometida=fecha_limite if al_tubo else None,
            estado='EN_TUBO' if al_tubo else 'REGISTRADA',
            item=item,
            periodo=periodo,
            usuario=request.user,
        )
        registrar_auditoria(request.user, 'CREACION', 'Actividad', actividad.pk, '', f"{actividad} [{actividad.estado}]")

        if al_tubo:
            messages.success(request, f"Actividad {actividad.folio()} ingresada al Tubo de Trabajo con fecha límite "
                                      f"{fecha_limite:%d/%m/%Y}. Suba la evidencia cuando la ejecute.")
            return redirect('actividades:tubo_trabajo')

        evidencia = Evidencia.objects.create(actividad=actividad, imagen=imagen, version=1)
        actividad.sincronizar_estado()
        registrar_auditoria(request.user, 'CREACION', 'Evidencia', evidencia.pk, '', evidencia)
        messages.success(request, f"Actividad {actividad.folio()} registrada. Queda a la espera de la validación del Delegado.")
        return redirect('actividades:mi_gestion')

    return render(request, 'actividades/actividad_form.html', data_form)


# ---------------------------------------------------------------------------
# Detalle de la actividad y carga de evidencia (ejecutar un compromiso o resubir una rechazada)
# ---------------------------------------------------------------------------
def puede_ver_actividad(usuario, actividad):
    """La ve su funcionario, la supervisión (Admin, Coordinador, Consulta) y los compañeros de su delegación."""
    if usuario.pk == actividad.usuario_id or usuario.tiene_rol(['Admin', 'Coordinador', 'Consulta']):
        return True
    delegacion = actividad.usuario.delegacion_id
    return usuario.delegacion_id is not None and usuario.delegacion_id == delegacion


def actividad_detalle(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    actividad = get_object_or_404(Actividad.objects.select_related('usuario', 'item', 'periodo'), pk=pk)
    if not puede_ver_actividad(request.user, actividad):
        return acceso_denegado(request, f"la actividad {actividad.folio()}")

    evidencias = []
    for evidencia in actividad.evidencias.order_by('-version'):
        validacion = getattr(evidencia, 'validacion', None)
        evidencias.append({
            'codigo': evidencia.codigo(),
            'version': evidencia.version,
            'fecha': evidencia.fecha,
            'imagen': evidencia.imagen,
            'estado': evidencia.get_estado_revision_display(),
            'estado_codigo': evidencia.estado_revision,
            'observacion': validacion.observacion if validacion else '',
            'verificador': validacion.verificador if validacion else None,
        })

    data = {
        'actividad': actividad,
        'evidencias': evidencias,
        'puede_subir': actividad.puede_subir_evidencia(request.user),
    }
    return render(request, 'actividades/actividad_detalle.html', data)


def subir_evidencia(request, pk):
    """El funcionario ejecuta su compromiso (sale del Tubo) o resube una evidencia rechazada."""
    if not request.user.is_authenticated:
        return redirect('users:login')
    actividad = get_object_or_404(Actividad, pk=pk)
    if request.method != 'POST':
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    if not actividad.puede_subir_evidencia(request.user):
        messages.error(request, "Solo el funcionario que registró la actividad puede subir su evidencia, "
                                "y solo cuando está en el Tubo o su evidencia fue rechazada.")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    imagen = request.FILES.get('evidencia_imagen')
    if imagen is None:
        messages.error(request, "Adjunte la fotografía de evidencia.")
        return redirect('actividades:actividad_detalle', pk=actividad.pk)
    errores = validar_imagen(imagen)
    if errores:
        for error in errores:
            messages.error(request, error)
        return redirect('actividades:actividad_detalle', pk=actividad.pk)

    anterior = actividad.evidencia_vigente()
    estado_anterior = actividad.estado
    evidencia = Evidencia.objects.create(
        actividad=actividad, imagen=imagen, comentario=request.POST.get('comentario', '').strip(),
        version=(anterior.version + 1) if anterior else 1, reemplaza_a=anterior)
    # Un compromiso que se ejecuta cuenta en el periodo en que se realiza
    if estado_anterior == 'EN_TUBO':
        periodo = periodo_vigente()
        if periodo is not None and not periodo.periodo_cerrado():
            actividad.periodo = periodo
    actividad.sincronizar_estado()
    registrar_auditoria(request.user, 'CREACION', 'Evidencia', evidencia.pk, '', evidencia)
    registrar_auditoria(request.user, 'MODIFICACION', 'Actividad', actividad.pk, estado_anterior, actividad.estado)

    if estado_anterior == 'EN_TUBO':
        messages.success(request, f"Compromiso {actividad.folio()} ejecutado: salió del Tubo y espera la validación del Delegado.")
    else:
        messages.success(request, f"Nueva evidencia de {actividad.folio()} enviada a validación (reemplaza a la rechazada).")
    return redirect('actividades:actividad_detalle', pk=actividad.pk)


# ---------------------------------------------------------------------------
# Tubo de Trabajo: las actividades sin evidencia (compromisos) de la delegación
# ---------------------------------------------------------------------------
def actividad_a_fila_tubo(actividad):
    """Adapta una actividad del Tubo a los nombres que usa el template."""
    return {
        'pk': actividad.pk,
        'folio': actividad.folio(),
        'fecha_registro': actividad.fecha,
        'fecha_comprometida': actividad.fecha_comprometida,
        'contacto': actividad.contacto or '-',
        'descripcion': actividad.solicitud_problema,
        'accion': actividad.accion,
        'territorio': actividad.territorio or '-',
        'funcionario': actividad.usuario,
        'usuario_id': actividad.usuario_id,
        'estado': actividad.estado,
        'estado_texto': actividad.get_estado_display(),
        'vencido': actividad.vencido(),
        'proximo_a_vencer': actividad.proximo_a_vencer(),
    }


ESTADOS_FILTRO_TUBO = [
    ('', 'En el Tubo (pendientes)'),
    ('VENCIDOS', 'Vencidos'),
    ('POR_VENCER', 'Por vencer'),
    ('EN_REVISION', 'Ejecutados, en revisión del Delegado'),
    ('COMPLETADOS', 'Completados (validados)'),
    ('TODOS', 'Todos'),
]


def tubo_trabajo(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Funcionario']):
        return acceso_denegado(request, 'Tubo de Trabajo')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    # El Tubo son las actividades que entraron como compromiso (sin evidencia al registrarse)
    actividades = Actividad.objects.filter(ingreso_agenda_colectiva=True).select_related('usuario')
    if delegacion is not None:
        # HU-12: todos los de la delegación ven la agenda colectiva
        actividades = actividades.filter(usuario__delegacion=delegacion)
    elif not request.user.tiene_rol(['Admin', 'Coordinador']):
        # Sin delegación asignada: solo lo propio
        actividades = actividades.filter(usuario=request.user)

    filtros = {
        'responsable': request.GET.get('responsable', ''),
        'estado': request.GET.get('estado', ''),
        'territorio': request.GET.get('territorio', '').strip(),
        'desde': request.GET.get('desde', ''),
        'hasta': request.GET.get('hasta', ''),
        'mios': request.GET.get('mios', ''),
    }
    responsables = Usuario.objects.filter(pk__in=actividades.values('usuario')).order_by('first_name', 'last_name')

    hoy = timezone.localdate()
    if filtros['responsable'].isdigit():
        actividades = actividades.filter(usuario_id=int(filtros['responsable']))
    if filtros['estado'] == 'VENCIDOS':
        actividades = actividades.filter(estado='EN_TUBO', fecha_comprometida__lt=hoy)
    elif filtros['estado'] == 'POR_VENCER':
        actividades = actividades.filter(estado='EN_TUBO', fecha_comprometida__gte=hoy,
                                         fecha_comprometida__lte=hoy + timedelta(days=DIAS_POR_VENCER))
    elif filtros['estado'] == 'EN_REVISION':
        actividades = actividades.filter(estado__in=['REGISTRADA', 'RECHAZADA'])
    elif filtros['estado'] == 'COMPLETADOS':
        actividades = actividades.filter(estado='VALIDADA')
    elif filtros['estado'] != 'TODOS':
        actividades = actividades.filter(estado='EN_TUBO')
    if filtros['territorio']:
        actividades = actividades.filter(territorio__icontains=filtros['territorio'])
    desde = fecha_de_texto(filtros['desde'])
    hasta = fecha_de_texto(filtros['hasta'])
    if desde is not None:
        actividades = actividades.filter(fecha_comprometida__gte=desde)
    if hasta is not None:
        actividades = actividades.filter(fecha_comprometida__lte=hasta)
    if filtros['mios'] == '1':
        actividades = actividades.filter(usuario=request.user)

    lista = [actividad_a_fila_tubo(a) for a in actividades.order_by('fecha_comprometida', 'fecha')]
    data = {
        'compromisos': lista,
        'delegacion_actual': f"Delegación {nombre}",
        'codigo_delegacion': codigo,
        'filtros': filtros,
        'responsables': responsables,
        'estados_filtro': ESTADOS_FILTRO_TUBO,
    }
    return render(request, 'actividades/tubo_trabajo.html', data)


# ---------------------------------------------------------------------------
# Gestión Social
# ---------------------------------------------------------------------------
def gestion_social(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Funcionario']):
        return acceso_denegado(request, 'Gestión Social')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    atenciones = AtencionSocial.objects.select_related('actividad', 'tipo_atencion', 'subtipo_atencion')
    if delegacion is not None:
        atenciones = atenciones.filter(actividad__usuario__delegacion=delegacion)
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado']):
        atenciones = atenciones.filter(actividad__usuario=request.user)

    lista = []
    for atencion in atenciones.order_by('-actividad__fecha'):
        fila = {
            'id': atencion.pk,
            'fecha_atencion': atencion.actividad.fecha,
            'tipo_atencion': atencion.tipo_atencion.nombre,
            'sub_atencion': atencion.subtipo_atencion or '-',
            'nombre_usuario': atencion.nombre_solicitante,
            'rut_usuario': atencion.rut_solicitante,
            'fono': atencion.telefono_solicitante,
            'requiere_visita': atencion.requiere_visita,
            'ingreso_tubo': atencion.actividad.ingreso_agenda_colectiva,
            'accion_1': '', 'fecha_visita': None,
            'accion_2': '', 'fecha_informe': None,
            'accion_3': '', 'fecha_beneficio': None,
            'codigo': atencion.codigo(),
            'verificado': atencion.verificado(),
        }
        # Cada gestión (1, 2 o 3) ocupa su columna en la tabla
        for gestion in atencion.gestiones.all():
            if gestion.numero_gestion == 1:
                fila['accion_1'] = gestion.accion
                fila['fecha_visita'] = gestion.fecha
            elif gestion.numero_gestion == 2:
                fila['accion_2'] = gestion.accion
                fila['fecha_informe'] = gestion.fecha
            elif gestion.numero_gestion == 3:
                fila['accion_3'] = gestion.accion
                fila['fecha_beneficio'] = gestion.fecha
        lista.append(fila)

    return render(request, 'actividades/gestion_social.html', {'atenciones': lista})


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
    if not request.user.puede_administrar():
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
            'fue_compromiso': evidencia.actividad.ingreso_agenda_colectiva,
            'fecha_comprometida': evidencia.actividad.fecha_comprometida,
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
    if not request.user.puede_administrar():
        delegacion_actividad = evidencia.actividad.usuario.delegacion_id
        if request.user.delegacion_id is None or request.user.delegacion_id != delegacion_actividad:
            messages.error(request, "Solo puede verificar evidencias de funcionarios de su delegación.")
            return redirect('actividades:verificacion')
    decision = request.POST.get('decision', '')
    observacion = request.POST.get('observacion', '').strip()

    if evidencia.estado_revision != 'PENDIENTE' or Validacion.objects.filter(evidencia=evidencia).exists():
        messages.error(request, "Esta evidencia ya fue revisada.")
        return redirect('actividades:verificacion')
    if evidencia.actividad.usuario_id == request.user.pk:
        messages.error(request, "No puede verificar una evidencia registrada por usted mismo.")
        return redirect('actividades:verificacion')
    # Rechazar invalida la evidencia, no la actividad: se debe cumplir igual y el funcionario la resube
    if decision not in ['APROBAR', 'RECHAZAR']:
        messages.error(request, "Decisión no válida.")
        return redirect('actividades:verificacion')
    if decision == 'RECHAZAR' and not observacion:
        messages.error(request, "Para rechazar la evidencia debe escribir una observación que explique por qué no es válida.")
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
        messages.success(request, f"Evidencia {evidencia.codigo()} rechazada: el funcionario debe subir una nueva.")
    return redirect('actividades:verificacion')
