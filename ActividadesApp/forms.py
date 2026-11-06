"""Formularios de ActividadesApp. Cada formulario valida sus propios datos: la vista solo pregunta
form.is_valid() y, si hay errores, la plantilla los muestra junto al campo que corresponde."""
from datetime import datetime, time, timedelta

from django import forms
from django.conf import settings
from django.utils import timezone

from ActividadesApp.choices import MAX_ACTIVIDADES_DIA, ITEM_FELICITACIONES, cargos_representante
from ActividadesApp.models import Actividad, Territorio, AtencionSocial, Organizacion, Solicitante, Representante
from UsuarioApp.funciones import limpiar_rut, validar_rut
from UsuarioApp.models import Catalogo, Usuario


def validar_imagen(imagen):
    """Devuelve la lista de errores de la fotografía (vacía si está bien)."""
    errores = []
    nombre_archivo = imagen.name.lower()
    if not (nombre_archivo.endswith('.jpg') or nombre_archivo.endswith('.jpeg') or nombre_archivo.endswith('.png')):
        errores.append("La fotografía debe ser JPG o PNG.")
    if imagen.size > settings.MAX_IMAGEN_EVIDENCIA:
        errores.append("La fotografía no puede superar 5 MB.")
    return errores


def territorios_para(usuario):
    """Territorios que puede elegir el usuario: los de su delegación (o todos, si no tiene delegación)."""
    territorios = Territorio.objects.filter(estado='ACTIVO').select_related('delegacion')
    if usuario.delegacion_id is not None:
        territorios = territorios.filter(delegacion_id=usuario.delegacion_id)
    return territorios


def funcionarios_para(usuario):
    """Funcionarios activos que se pueden elegir como encargado: los de la delegación de quien registra
    (el Administrador, de todas). Quien registra no aparece: dejar el campo vacío significa que la realiza él."""
    funcionarios = Usuario.objects.filter(is_active=True, roles_asignados__rol__codigo='Funcionario').select_related('delegacion', 'territorio')
    if not usuario.es_administrador():
        funcionarios = funcionarios.filter(delegacion_id=usuario.delegacion_id)
    return funcionarios.exclude(pk=usuario.pk).distinct().order_by('first_name', 'last_name')


def solicitudes_para(usuario):
    """Solicitudes sociales visibles: las de la delegación del usuario (Administrador y Coordinador, todas)."""
    solicitudes = AtencionSocial.objects.select_related('usuario', 'usuario__delegacion', 'tipo_atencion')
    if not usuario.tiene_rol(['Admin', 'Coordinador']):
        solicitudes = solicitudes.filter(usuario__delegacion_id=usuario.delegacion_id)
    return solicitudes.order_by('-fecha')


def inicio_semana_abierta(hoy):
    """Primer día en que todavía se pueden ingresar actividades ya realizadas. Se trabaja de lunes a viernes y la
    semana se cierra el lunes siguiente: el lunes aún se ingresa lo de la semana pasada; desde el martes, solo lo
    de la semana en curso."""
    lunes = hoy - timedelta(days=hoy.weekday())
    if hoy.weekday() == 0:
        return lunes - timedelta(days=7)
    return lunes


def actividades_ingresadas_hoy(usuario):
    """Cuántas actividades ingresó hoy el usuario (por fecha de ingreso, sin importar su fecha de realización).
    Se usa un rango de fecha y hora en vez de fecha__date: así funciona aunque MySQL no tenga cargadas las
    zonas horarias."""
    hoy = timezone.localdate()
    inicio = timezone.make_aware(datetime.combine(hoy, time.min))
    return Actividad.objects.filter(usuario=usuario, fecha__gte=inicio, fecha__lt=inicio + timedelta(days=1)).count()


def solo_digitos(texto):
    return ''.join(c for c in (texto or '') if c.isdigit())


def es_item_felicitaciones(item):
    return item is not None and item.nombre == ITEM_FELICITACIONES


# ---------------------------------------------------------------------------
# Solicitante: lo comparten Agregar atención y Agregar actividad
# ---------------------------------------------------------------------------
OPCIONES_CARGO = [('', 'Seleccione el cargo...')] + list(cargos_representante)


class SolicitanteMixin:
    """Persona atendida, identificada por su RUT (obligatorio).
    - Si el RUT está registrado, nombre y teléfono se completan con sus datos (y si se corrigen, se actualizan).
    - Si no está, se pregunta "¿Desea agregar solicitante al sistema?": con "Sí" (agregar_solicitante) se registra
      al guardar, y puede quedar como presidente, secretario o tesorero de una organización.
    El formulario que lo usa llama a agregar_campos_solicitante() en __init__ y a resolver_solicitante() en clean()."""

    def agregar_campos_solicitante(self):
        self.fields['rut_solicitante'] = forms.CharField(max_length=15, required=False, label="RUT del solicitante")
        self.fields['nombre_solicitante'] = forms.CharField(max_length=200, required=False, label="Nombre del solicitante")
        self.fields['telefono_solicitante'] = forms.CharField(max_length=20, required=False, label="Teléfono")
        self.fields['agregar_solicitante'] = forms.BooleanField(required=False, widget=forms.HiddenInput)
        self.fields['organizacion'] = forms.ModelChoiceField(queryset=Organizacion.objects.all(), required=False,
                                                             label="Organización que representa (opcional)",
                                                             empty_label="No representa a una organización")
        self.fields['cargo'] = forms.ChoiceField(choices=OPCIONES_CARGO, required=False, label="Cargo en la organización")
        self.solicitante = None          # el registrado (o el recién creado, después de guardar)
        self.nuevo_solicitante = False   # True: se crea al guardar
        self.cambio_solicitante = None   # para la auditoría: ('CREACION' o 'MODIFICACION', antes, después)

    def datos_iniciales_solicitante(self, solicitante):
        """Para modificar: el formulario parte con los datos del solicitante guardado."""
        if solicitante is not None and not self.is_bound:
            self.initial.update({'rut_solicitante': solicitante.rut, 'nombre_solicitante': solicitante.nombre,
                                 'telefono_solicitante': solicitante.telefono})

    def resolver_solicitante(self, datos):
        texto = (datos.get('rut_solicitante') or '').strip()
        if not texto:
            self.add_error('rut_solicitante', "Ingrese el RUT del solicitante: sin él, no queda registrado a quién se atendió.")
            return
        rut = limpiar_rut(texto)
        if len(rut) > 12 or not validar_rut(rut):
            self.add_error('rut_solicitante', "El RUT no es válido.")
            return
        datos['rut_solicitante'] = rut
        nombre = (datos.get('nombre_solicitante') or '').strip()
        telefono = (datos.get('telefono_solicitante') or '').strip()
        self.solicitante = Solicitante.objects.filter(rut=rut).first()
        if self.solicitante is not None:
            nombre = nombre or self.solicitante.nombre
            telefono = telefono or self.solicitante.telefono
        elif not datos.get('agregar_solicitante'):
            self.add_error('rut_solicitante', "Este RUT no está registrado. ¿Desea agregar solicitante al sistema? "
                                              "Confirme para registrarlo.")
            return
        else:
            self.nuevo_solicitante = True
            self.revisar_cargo(datos)
        if not nombre:
            self.add_error('nombre_solicitante', "Indique el nombre del solicitante.")
        if not telefono:
            self.add_error('telefono_solicitante', "Indique el teléfono del solicitante.")
        elif not 8 <= len(solo_digitos(telefono)) <= 12:
            self.add_error('telefono_solicitante', "Escriba un teléfono válido (entre 8 y 12 dígitos).")
        datos['nombre_solicitante'] = nombre
        datos['telefono_solicitante'] = telefono

    def revisar_cargo(self, datos):
        """Organización y cargo van juntos, y cada cargo lo ocupa una sola persona por organización."""
        organizacion, cargo = datos.get('organizacion'), datos.get('cargo')
        if organizacion and not cargo:
            self.add_error('cargo', "Indique el cargo que ocupa en la organización.")
        elif cargo and not organizacion:
            self.add_error('organizacion', "Indique la organización en que ocupa ese cargo.")
        elif organizacion:
            ocupado = Representante.objects.filter(organizacion=organizacion, cargo=cargo).select_related('solicitante').first()
            if ocupado is not None:
                self.add_error('cargo', f"{organizacion} ya tiene {ocupado.get_cargo_display().lower()}: {ocupado.solicitante}.")

    def guardar_solicitante(self):
        """Crea el solicitante nuevo (y su cargo) o actualiza nombre y teléfono del registrado si se corrigieron."""
        datos = self.cleaned_data
        nombre, telefono = datos['nombre_solicitante'], datos['telefono_solicitante']
        if self.nuevo_solicitante:
            self.solicitante = Solicitante.objects.create(rut=datos['rut_solicitante'], nombre=nombre, telefono=telefono)
            if datos.get('organizacion') and datos.get('cargo'):
                Representante.objects.create(organizacion=datos['organizacion'], solicitante=self.solicitante,
                                             cargo=datos['cargo'])
            self.cambio_solicitante = ('CREACION', '', str(self.solicitante))
        elif (self.solicitante.nombre, self.solicitante.telefono) != (nombre, telefono):
            antes = f"{self.solicitante} - {self.solicitante.telefono}"
            self.solicitante.nombre, self.solicitante.telefono = nombre, telefono
            self.solicitante.save()
            self.cambio_solicitante = ('MODIFICACION', antes, f"{self.solicitante} - {telefono}")
        return self.solicitante


class ActividadForm(SolicitanteMixin, forms.Form):
    """Registrar una actividad. La fecha de ingreso se guarda sola; la fecha de realización la elige quien registra:
    - hoy o antes: se agrega la evidencia (comentario obligatorio, foto opcional);
    - después de hoy: queda como compromiso pendiente (PROGRAMADA);
    - si depende de factores externos, va al Tubo de Trabajo. Ahí la fecha de realización es opcional:
    sin fecha queda EN_TUBO (se agrega después); con fecha queda PROGRAMADA, sin salir del Tubo."""
    solicitud_problema = forms.CharField(label="Descripción de la actividad / solicitud / problema",
                                        widget=forms.Textarea(attrs={'rows': 3}))
    accion = forms.CharField(max_length=255, label="Acción")
    item = forms.ModelChoiceField(queryset=Catalogo.objects.none(), label="Ítem / comisión a medir",
                                empty_label="Seleccione una opción...")
    territorio = forms.ModelChoiceField(queryset=Territorio.objects.none(), label="Territorio / sector",
                                        empty_label="Seleccione un territorio...")
    depende_externos = forms.BooleanField(required=False,
                                        label="Depende de factores externos: pasa al Tubo de Trabajo")
    fecha_realizacion = forms.DateField(required=False, label="Fecha de realización",
                                        widget=forms.DateInput(attrs={'type': 'date'}))
    comentario = forms.CharField(required=False, label="Comentario de lo que se hizo",
                                widget=forms.Textarea(attrs={'rows': 2}))
    imagen = forms.ImageField(required=False, label="Fotografía (opcional)")
    encargado = forms.ModelChoiceField(queryset=Usuario.objects.none(), required=False, label="Encargado de la actividad",
                                    empty_label="Yo mismo (quien registra)")
    solicitud = forms.ModelChoiceField(queryset=AtencionSocial.objects.none(), required=False,
                                    label="Vincular a una solicitud social")
    # Persona atendida: los campos del solicitante (RUT obligatorio) los agrega SolicitanteMixin

    def __init__(self, *args, usuario=None, actividad=None, **kwargs):
        """actividad: la que se modifica (modo edición). En edición no se aplica el máximo diario, y el cierre de
        semana solo se revisa si cambia la fecha de realización."""
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.actividad = actividad
        self.solicitud_encontrada = None  # solicitud social que el sistema vinculó sola, por el solicitante
        self.agregar_campos_solicitante()
        self.datos_iniciales_solicitante(actividad.solicitante if actividad is not None else None)
        items = Catalogo.objects.filter(tipo='ITEM_GESTION', estado='ACTIVO').order_by('id')
        if usuario is not None and not (usuario.es_administrador() or usuario.es_delegado()):
            # Las felicitaciones las informa el Delegado, nunca el propio funcionario
            items = items.exclude(nombre=ITEM_FELICITACIONES)
        self.fields['item'].queryset = items
        self.fields['territorio'].queryset = territorios_para(usuario) if usuario else Territorio.objects.none()
        if usuario is not None:
            self.fields['encargado'].queryset = funcionarios_para(usuario)
            self.fields['solicitud'].queryset = solicitudes_para(usuario)
            if usuario.es_delegado():
                self.fields['encargado'].label = "Funcionario felicitado (solo para Felicitaciones de usuarios)"
                self.fields['encargado'].empty_label = "Seleccione..."
        if not self.is_bound:
            self.initial.setdefault('fecha_realizacion', timezone.localdate())

    def vincular_solicitud(self, datos):
        """La solicitud social y la persona atendida deben coincidir. Sin solicitud elegida, si el solicitante tiene
        una sola solicitud sin atender, la actividad se vincula sola a ella."""
        solicitud = datos.get('solicitud')
        if 'rut_solicitante' in self.errors:
            return
        if solicitud is not None:
            if self.solicitante is None or solicitud.solicitante_id != self.solicitante.pk:
                self.add_error('solicitud', f"La solicitud {solicitud.codigo()} es de {solicitud.solicitante}, "
                                            f"no de la persona atendida.")
            return
        if self.solicitante is None:  # persona nueva: todavía no tiene solicitudes
            return
        candidatas = [s for s in self.fields['solicitud'].queryset.filter(solicitante=self.solicitante)
                      if s.estado() != 'ATENDIDA']
        if len(candidatas) == 1:
            self.solicitud_encontrada = candidatas[0]
            datos['solicitud'] = candidatas[0]

    def es_felicitacion(self):
        return es_item_felicitaciones(self.cleaned_data.get('item'))

    def es_gestion(self):
        """Lo que ingresa el Delegado es una gestión (sin puntaje), salvo las felicitaciones de usuarios."""
        return self.usuario is not None and self.usuario.es_delegado() and not self.es_felicitacion()

    def revisar_reglas_de_ingreso(self, datos, hoy):
        """Máximo de actividades por día (el Administrador queda exento) y cierre de la semana."""
        if self.usuario is not None and self.actividad is None and not self.usuario.es_administrador():
            if actividades_ingresadas_hoy(self.usuario) >= MAX_ACTIVIDADES_DIA:
                self.add_error(None, f"Ya ingresó {MAX_ACTIVIDADES_DIA} actividades hoy, el máximo diario. Ingrese sus "
                                     "actividades cada día, sin acumularlas.")
        fecha = datos.get('fecha_realizacion')
        cambio_fecha = self.actividad is None or fecha != self.actividad.fecha_realizacion
        if fecha is not None and fecha <= hoy and cambio_fecha:
            desde = inicio_semana_abierta(hoy)
            if fecha < desde:
                self.add_error('fecha_realizacion', f"La semana de esa fecha ya está cerrada: solo se pueden ingresar "
                                                    f"actividades desde el {desde:%d/%m/%Y}.")

    def revisar_felicitacion(self, datos, hoy):
        if not self.es_felicitacion():
            if self.usuario is not None and self.usuario.es_delegado():
                datos['encargado'] = None  # la gestión es del propio Delegado
            return
        if not datos.get('encargado'):
            self.add_error('encargado', "Indique el funcionario felicitado.")
        if datos.get('depende_externos') or datos.get('fecha_realizacion') is None or datos['fecha_realizacion'] > hoy:
            self.add_error('fecha_realizacion', "Una felicitación se informa cuando ya se recibió: use la fecha de hoy "
                                                "o una anterior.")

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if imagen:
            for error in validar_imagen(imagen):
                self.add_error('imagen', error)
        return imagen

    def clean(self):
        datos = super().clean()
        hoy = timezone.localdate()
        if not (datos.get('rut_solicitante') or '').strip() and datos.get('solicitud') is not None:
            datos['rut_solicitante'] = datos['solicitud'].solicitante.rut  # la persona de la solicitud elegida
        self.resolver_solicitante(datos)
        self.vincular_solicitud(datos)
        self.revisar_reglas_de_ingreso(datos, hoy)
        self.revisar_felicitacion(datos, hoy)
        if datos.get('depende_externos'):
            # En el Tubo todavía no hay evidencia. La fecha es opcional: si se elige, no puede ser pasada
            fecha = datos.get('fecha_realizacion')
            if fecha is not None and fecha < hoy:
                self.add_error('fecha_realizacion', "La fecha de realización no puede ser anterior a hoy.")
            datos['comentario'] = ''
            datos['imagen'] = None
            return datos

        fecha = datos.get('fecha_realizacion')
        if fecha is None:
            if 'fecha_realizacion' not in self.errors:
                self.add_error('fecha_realizacion', "Indique la fecha de realización de la actividad, "
                                                    "o márquela como dependiente de factores externos.")
            return datos
        if fecha <= hoy:
            # Se agrega la evidencia: el comentario es obligatorio, la foto no
            if not (datos.get('comentario') or '').strip():
                self.add_error('comentario', "Escriba un comentario de lo que se hizo en la actividad.")
        else:
            # Es un compromiso: la evidencia (comentario y foto) se agrega cuando llegue la fecha
            datos['comentario'] = ''
            datos['imagen'] = None
        return datos

    def estado_inicial(self):
        """Estado con el que nace la actividad según lo que se llenó."""
        datos = self.cleaned_data
        if datos['depende_externos']:
            return 'PROGRAMADA' if datos['fecha_realizacion'] else 'EN_TUBO'
        if datos['fecha_realizacion'] > timezone.localdate():
            return 'PROGRAMADA'
        return 'EVIDENCIA_INGRESADA'


class EvidenciaForm(forms.Form):
    """Registrar que la actividad se hizo: comentario obligatorio y foto opcional."""
    comentario = forms.CharField(label="Comentario de lo que se hizo", widget=forms.Textarea(attrs={'rows': 3}))
    imagen = forms.ImageField(required=False, label="Fotografía (opcional, JPG o PNG, máx. 5 MB)")

    def clean_comentario(self):
        comentario = self.cleaned_data['comentario'].strip()
        if not comentario:
            raise forms.ValidationError("Escriba un comentario de lo que se hizo en la actividad.")
        return comentario

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if imagen:
            errores = validar_imagen(imagen)
            if errores:
                raise forms.ValidationError(errores)
        return imagen


class FechaRealizacionForm(forms.Form):
    """Asignar (o cambiar) la fecha en que se realizará una actividad pendiente."""
    fecha_realizacion = forms.DateField(label="Fecha en que se realizará", widget=forms.DateInput(attrs={'type': 'date'}))

    def clean_fecha_realizacion(self):
        fecha = self.cleaned_data['fecha_realizacion']
        if fecha < timezone.localdate():
            raise forms.ValidationError("La fecha no puede ser anterior a hoy.")
        return fecha


class ComentarioForm(forms.Form):
    """Actualización de la bitácora de la actividad."""
    texto = forms.CharField(label="Nueva actualización", max_length=2000, widget=forms.Textarea(attrs={'rows': 2}))

    def clean_texto(self):
        texto = self.cleaned_data['texto'].strip()
        if not texto:
            raise forms.ValidationError("Escriba la actualización.")
        return texto


class EncargadoForm(forms.Form):
    """Asignar el Funcionario encargado de una actividad pendiente."""
    encargado = forms.ModelChoiceField(queryset=None, label="Funcionario encargado", empty_label="Seleccione...")

    def __init__(self, *args, candidatos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['encargado'].queryset = candidatos


class AtencionForm(SolicitanteMixin, forms.ModelForm):
    """Solicitud social de una persona natural. La fecha de ingreso y quién la registra se guardan solos.
    El solicitante (RUT, nombre y teléfono) se busca o se registra con SolicitanteMixin."""
    class Meta:
        model = AtencionSocial
        fields = ['tipo_atencion', 'subtipo_atencion', 'requiere_visita']
        labels = {'requiere_visita': "Requiere visita domiciliaria"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_atencion'].queryset = Catalogo.objects.filter(tipo='TIPO_ATENCION', estado='ACTIVO')
        self.fields['subtipo_atencion'].queryset = Catalogo.objects.filter(tipo='SUBTIPO_ATENCION', estado='ACTIVO')
        self.fields['tipo_atencion'].empty_label = "Seleccione el tipo..."
        self.fields['subtipo_atencion'].empty_label = "Sin subtipo"
        self.agregar_campos_solicitante()
        self.datos_iniciales_solicitante(self.instance.solicitante if self.instance.solicitante_id else None)

    def clean(self):
        datos = super().clean()
        self.resolver_solicitante(datos)
        tipo = datos.get('tipo_atencion')
        subtipo = datos.get('subtipo_atencion')
        if tipo and subtipo and subtipo.padre_id not in (None, tipo.pk):
            self.add_error('subtipo_atencion', "El subtipo no corresponde al tipo de atención elegido.")
        return datos
