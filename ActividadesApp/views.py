from datetime import date

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import (Actividad, Evidencia, Validacion, Compromiso, HistorialCompromiso, AtencionSocial)
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
            'codigo_evidencia': codigo_evidencia,
            'esta_validada': act.estado == 'VALIDADA',
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
    }
    return render(request, 'actividades/mi_gestion.html', data)


# ---------------------------------------------------------------------------
# Registrar actividad (con evidencia opcional)
# ---------------------------------------------------------------------------
def actividad_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Funcionario']):
        return acceso_denegado(request, 'Registrar Actividad')

    # Actividad que responde a un compromiso del Tubo (viene de ?compromiso=ID o del campo oculto)
    compromiso_origen = None
    id_compromiso = request.POST.get('compromiso') or request.GET.get('compromiso')
    if id_compromiso:
        compromiso_origen = Compromiso.objects.filter(pk=id_compromiso if str(id_compromiso).isdigit() else 0).first()
        if compromiso_origen is None:
            messages.error(request, "El compromiso indicado no existe.")
            return redirect('actividades:tubo_trabajo')
        if compromiso_origen.responsable_id != request.user.pk:
            messages.error(request, "Solo el funcionario responsable puede registrar actividades de este compromiso.")
            return redirect('actividades:compromiso_detalle', pk=compromiso_origen.pk)
        if compromiso_origen.estado == 'REALIZADO':
            messages.error(request, "El compromiso ya está realizado; no admite nuevas actividades.")
            return redirect('actividades:compromiso_detalle', pk=compromiso_origen.pk)
    data_form = {'compromiso': compromiso_a_diccionario(compromiso_origen) if compromiso_origen else None}

    if request.method == 'POST':
        solicitud = request.POST.get('solicitud_problema', '').strip()
        accion = request.POST.get('accion', '').strip()
        contacto = request.POST.get('contacto', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        # Si la actividad responde a un compromiso existente no se crea otro
        ingresa_tubo = compromiso_origen is None and request.POST.get('ingreso_agenda_colectiva') == 'on'
        imagen = request.FILES.get('evidencia_imagen')
        item = Catalogo.objects.filter(pk=request.POST.get('item_comision') or 0, tipo='ITEM_GESTION', estado='ACTIVO').first()
        periodo = periodo_vigente()

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
        if item is None:
            errores.append("El ítem seleccionado no existe en el catálogo. Revise que se hayan cargado los datos iniciales.")
        if periodo is None:
            errores.append("No hay un periodo vigente para la fecha de hoy.")
        elif periodo.periodo_cerrado():
            errores.append("El periodo vigente está cerrado; no se pueden registrar actividades.")
        if imagen is not None:
            nombre_archivo = imagen.name.lower()
            if not (nombre_archivo.endswith('.jpg') or nombre_archivo.endswith('.jpeg') or nombre_archivo.endswith('.png')):
                errores.append("La fotografía debe ser JPG o PNG.")
            if imagen.size > settings.MAX_IMAGEN_EVIDENCIA:
                errores.append("La fotografía no puede superar 5 MB.")

        if errores:
            for error in errores:
                messages.error(request, error)
            return render(request, 'actividades/actividad_form.html', data_form)

        # ingreso_agenda_colectiva solo queda en True cuando la actividad queda enlazada a un compromiso
        actividad = Actividad.objects.create(
            solicitud_problema=solicitud,
            accion=accion,
            contacto=contacto,
            telefono=telefono,
            ingreso_agenda_colectiva=compromiso_origen is not None,
            compromiso=compromiso_origen,
            item=item,
            periodo=periodo,
            usuario=request.user,
        )
        registrar_auditoria(request.user, 'CREACION', 'Actividad', actividad.pk, '', actividad)

        if imagen is not None:
            evidencia = Evidencia.objects.create(actividad=actividad, imagen=imagen, version=1)
            actividad.sincronizar_estado()
            registrar_auditoria(request.user, 'CREACION', 'Evidencia', evidencia.pk, '', evidencia)

        # Si ingresa al Tubo de Trabajo se crea el compromiso automáticamente
        if ingresa_tubo:
            if request.user.delegacion is None:
                messages.warning(request, "La actividad se guardó, pero no se creó el compromiso porque " "usted no tiene delegación asignada.")
            else:
                compromiso = Compromiso.objects.create(
                    origen=f"Ingreso diario: {accion}"[:150],
                    solicitante=(contacto or 'Sin contacto')[:200],
                    territorio=str(request.user.delegacion),
                    area_apoyo=request.user.area()[:150],
                    observacion=solicitud,
                    fecha_comprometida=periodo.fecha_termino,
                    delegacion=request.user.delegacion,
                    registrado_por=request.user,
                    responsable=request.user,
                )
                HistorialCompromiso.objects.create(compromiso=compromiso, autor=request.user, estado_anterior='', estado_nuevo='INGRESADO', observacion="Ingreso desde actividad diaria.")
                actividad.marcar_ingreso_agenda(compromiso)
                registrar_auditoria(request.user, 'CREACION', 'Compromiso', compromiso.pk, '', compromiso)

        if compromiso_origen is not None:
            messages.success(request, f"Actividad registrada y asociada al compromiso {compromiso_origen.folio()}.")
            return redirect('actividades:compromiso_detalle', pk=compromiso_origen.pk)
        messages.success(request, "Actividad registrada correctamente.")
        return redirect('actividades:mi_gestion')

    return render(request, 'actividades/actividad_form.html', data_form)


# ---------------------------------------------------------------------------
# Tubo de Trabajo y compromisos
# ---------------------------------------------------------------------------
def compromiso_a_diccionario(compromiso):
    """Adapta un Compromiso a los nombres que usan los templates."""
    return {
        'pk': compromiso.pk,
        'id_compromiso': compromiso.folio(),
        'fecha_registro': compromiso.fecha_registro,
        'fecha_comprometida': compromiso.fecha_comprometida,
        'origen': compromiso.origen,
        'observacion': compromiso.observacion,
        'funcionario': compromiso.responsable,
        'responsable_id': compromiso.responsable_id,
        'territorio': compromiso.territorio or '-',
        'estado': compromiso.estado,
        'vencido': compromiso.vencido(),
        'proximo_a_vencer': compromiso.proximo_a_vencer(),
    }


def puede_ver_compromiso(usuario, compromiso):
    """HU-12: el compromiso es visible para la supervisión, para quienes participan en él
    y para los funcionarios de la misma delegación (agenda colectiva)."""
    if compromiso.puede_supervisar(usuario):
        return True
    if usuario.pk == compromiso.responsable_id or usuario.pk == compromiso.registrado_por_id:
        return True
    return usuario.delegacion_id is not None and usuario.delegacion_id == compromiso.delegacion_id


def fecha_de_filtro(texto):
    """Convierte 'AAAA-MM-DD' en fecha. Devuelve None si viene vacío o mal escrito."""
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def tubo_trabajo(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Funcionario']):
        return acceso_denegado(request, 'Tubo de Trabajo')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    compromisos = Compromiso.objects.select_related('responsable')
    if delegacion is not None:
        # HU-12: todos los funcionarios ven la agenda colectiva de su delegación
        compromisos = compromisos.filter(delegacion=delegacion)
    elif not request.user.tiene_rol(['Admin', 'Coordinador']):
        # Funcionario sin delegación asignada: solo lo que le concierne
        compromisos = compromisos.filter(responsable=request.user) | compromisos.filter(registrado_por=request.user)

    # Filtros de HU-12: responsable, estado, territorio, rango de fechas comprometidas y "solo míos"
    filtros = {
        'responsable': request.GET.get('responsable', ''),
        'estado': request.GET.get('estado', ''),
        'territorio': request.GET.get('territorio', '').strip(),
        'desde': request.GET.get('desde', ''),
        'hasta': request.GET.get('hasta', ''),
        'mios': request.GET.get('mios', ''),
    }
    responsables = Usuario.objects.filter(pk__in=compromisos.values('responsable')).order_by('first_name', 'last_name')

    if filtros['responsable'].isdigit():
        compromisos = compromisos.filter(responsable_id=int(filtros['responsable']))
    if filtros['estado'] in ['INGRESADO', 'PENDIENTE', 'EN_PROCESO', 'REALIZADO']:
        compromisos = compromisos.filter(estado=filtros['estado'])
    elif filtros['estado'] == 'VENCIDOS':
        compromisos = compromisos.exclude(estado='REALIZADO').filter(fecha_comprometida__lt=timezone.localdate())
    if filtros['territorio']:
        compromisos = compromisos.filter(territorio__icontains=filtros['territorio'])
    desde = fecha_de_filtro(filtros['desde'])
    hasta = fecha_de_filtro(filtros['hasta'])
    if desde is not None:
        compromisos = compromisos.filter(fecha_comprometida__gte=desde)
    if hasta is not None:
        compromisos = compromisos.filter(fecha_comprometida__lte=hasta)
    if filtros['mios'] == '1':
        compromisos = compromisos.filter(responsable=request.user)

    lista = []
    for compromiso in compromisos.order_by('fecha_comprometida'):
        lista.append(compromiso_a_diccionario(compromiso))

    data = {
        'compromisos': lista,
        'delegacion_actual': f"Delegación {nombre}",
        'codigo_delegacion': codigo,
        'filtros': filtros,
        'responsables': responsables,
        'estados_filtro': [('INGRESADO', 'Ingresado'), ('PENDIENTE', 'Pendiente'), ('EN_PROCESO', 'En proceso'), ('REALIZADO', 'Realizado'), ('VENCIDOS', 'Vencidos')],
    }
    return render(request, 'actividades/tubo_trabajo.html', data)


def compromiso_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Funcionario']):
        return acceso_denegado(request, 'Nuevo Compromiso')

    funcionarios = Usuario.objects.filter(is_active=True)
    if not request.user.tiene_rol(['Admin', 'Coordinador']) and request.user.delegacion is not None:
        funcionarios = funcionarios.filter(delegacion=request.user.delegacion)
    data = {'lista_funcionarios': funcionarios}

    if request.method == 'POST':
        origen = request.POST.get('origen', '').strip()
        observacion = request.POST.get('observacion', '').strip()
        territorio = request.POST.get('territorio', '').strip()
        responsable = funcionarios.filter(pk=request.POST.get('funcionario') or 0).first()
        try:
            fecha = date.fromisoformat(request.POST.get('fecha_comprometida', ''))
        except ValueError:
            fecha = None

        errores = []
        if not origen or len(origen) > 150:
            errores.append("El solicitante u organización es obligatorio (máximo 150 caracteres).")
        if not observacion:
            errores.append("Debe describir el requerimiento.")
        if len(territorio) > 150:
            errores.append("El territorio no puede superar 150 caracteres.")
        if responsable is None:
            errores.append("Debe seleccionar un funcionario responsable válido.")
        if fecha is None:
            errores.append("La fecha comprometida no es válida.")
        elif fecha < timezone.localdate():
            errores.append("La fecha comprometida no puede ser anterior a hoy.")

        # La delegación del compromiso es la del responsable (o la de quien lo registra)
        delegacion = None
        if responsable is not None:
            delegacion = responsable.delegacion or request.user.delegacion
            if delegacion is None:
                errores.append("El responsable no tiene delegación asignada. Asígnela en Administración.")

        if errores:
            for error in errores:
                messages.error(request, error)
            return render(request, 'actividades/compromiso_form.html', data)

        compromiso = Compromiso.objects.create(
            origen=origen,
            solicitante=origen,
            territorio=territorio,
            observacion=observacion,
            fecha_comprometida=fecha,
            delegacion=delegacion,
            registrado_por=request.user,
            responsable=responsable,
        )
        HistorialCompromiso.objects.create(compromiso=compromiso, autor=request.user, estado_anterior='', estado_nuevo='INGRESADO', observacion="Registro del compromiso.")
        registrar_auditoria(request.user, 'CREACION', 'Compromiso', compromiso.pk, '', compromiso)
        messages.success(request, f"Compromiso {compromiso.folio()} registrado.")
        return redirect('actividades:tubo_trabajo')

    return render(request, 'actividades/compromiso_form.html', data)


def compromiso_detalle(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')

    compromiso = get_object_or_404(Compromiso, pk=pk)
    if not puede_ver_compromiso(request.user, compromiso):
        return acceso_denegado(request, f"el compromiso {compromiso.folio()}")

    if request.method == 'POST':
        anterior = compromiso.estado
        ok, mensaje = compromiso.cambiar_estado(request.POST.get('estado', ''), request.user,
                                                request.POST.get('observacion', ''))
        if ok:
            registrar_auditoria(request.user, 'MODIFICACION', 'Compromiso', compromiso.pk, anterior, compromiso.estado)
            messages.success(request, mensaje)
        else:
            messages.error(request, mensaje)
        return redirect('actividades:compromiso_detalle', pk=compromiso.pk)

    es_responsable = request.user.pk == compromiso.responsable_id
    actividades = []
    for act in compromiso.actividades.select_related('usuario').order_by('-fecha'):
        actividades.append({
            'fecha': act.fecha,
            'accion': act.accion,
            'funcionario': act.usuario,
            'estado': act.get_estado_display(),
            'estado_codigo': act.estado,
        })

    data = {
        'object': compromiso_a_diccionario(compromiso),
        # Solo el responsable o la supervisión pueden cambiar el estado (misma regla que cambiar_estado)
        'puede_gestionar': es_responsable or compromiso.puede_supervisar(request.user),
        # Solo el responsable registra la actividad con la que ejecuta el compromiso
        'puede_registrar_actividad': es_responsable and compromiso.estado != 'REALIZADO',
        'actividades': actividades,
    }
    return render(request, 'actividades/compromiso_detail.html', data)


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
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Verificador']):
        return acceso_denegado(request, 'Verificación')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    pendientes = Evidencia.objects.filter(estado_revision='PENDIENTE').select_related(
        'actividad', 'actividad__usuario', 'actividad__item').order_by('fecha')
    if delegacion is not None:
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
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Verificador']):
        return acceso_denegado(request, 'Verificación')
    if request.method != 'POST':
        return redirect('actividades:verificacion')

    evidencia = get_object_or_404(Evidencia, pk=pk)
    decision = request.POST.get('decision', '')
    observacion = request.POST.get('observacion', '').strip()

    if evidencia.estado_revision != 'PENDIENTE' or Validacion.objects.filter(evidencia=evidencia).exists():
        messages.error(request, "Esta evidencia ya fue revisada.")
        return redirect('actividades:verificacion')
    if evidencia.actividad.usuario_id == request.user.pk:
        messages.error(request, "No puede verificar una evidencia registrada por usted mismo.")
        return redirect('actividades:verificacion')
    if decision not in ['APROBAR', 'CORREGIR', 'RECHAZAR']:
        messages.error(request, "Decisión no válida.")
        return redirect('actividades:verificacion')
    if decision != 'APROBAR' and not observacion:
        messages.error(request, "Para corregir o rechazar debe escribir una observación.")
        return redirect(reverse('actividades:verificacion') + f"?evidencia_id={evidencia.pk}")

    Validacion.objects.create(evidencia=evidencia, decision=decision, observacion=observacion, verificador=request.user)
    nuevos_estados = {'APROBAR': 'APROBADA', 'CORREGIR': 'OBSERVADA', 'RECHAZAR': 'RECHAZADA'}
    anterior = evidencia.estado_revision
    evidencia.estado_revision = nuevos_estados[decision]
    evidencia.save()
    evidencia.actividad.sincronizar_estado()
    registrar_auditoria(request.user, 'MODIFICACION', 'Evidencia', evidencia.pk, anterior, evidencia.estado_revision)

    messages.success(request, f"Evidencia {evidencia.codigo()} marcada como {evidencia.estado_revision}.")
    return redirect('actividades:verificacion')
