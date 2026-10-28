"""Formularios de ActividadesApp. Cada formulario valida sus propios datos: la vista solo pregunta
form.is_valid() y, si hay errores, la plantilla los muestra junto al campo que corresponde."""
from django import forms
from django.conf import settings
from django.utils import timezone

from ActividadesApp.models import Territorio, AtencionSocial
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
    (el Administrador, de todas). Quien registra no aparece: dejar el campo vacío significa que la ejecuta él."""
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


class ActividadForm(forms.Form):
    """Registrar una actividad. La fecha de ingreso se guarda sola; la fecha de ejecución la elige quien registra:
    - hoy o antes: se registra ejecutada (comentario obligatorio, foto opcional);
    - después de hoy: queda como compromiso pendiente (PROGRAMADA);
    - si depende de factores externos, va al Tubo de Trabajo. Ahí la fecha de ejecución es opcional:
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
    fecha_realizacion = forms.DateField(required=False, label="Fecha de ejecución",
                                        widget=forms.DateInput(attrs={'type': 'date'}))
    comentario = forms.CharField(required=False, label="Comentario de lo que se hizo",
                                 widget=forms.Textarea(attrs={'rows': 2}))
    imagen = forms.ImageField(required=False, label="Fotografía (opcional)")
    encargado = forms.ModelChoiceField(queryset=Usuario.objects.none(), required=False, label="Encargado de la actividad",
                                       empty_label="Yo mismo (quien registra)")
    solicitud = forms.ModelChoiceField(queryset=AtencionSocial.objects.none(), required=False,
                                       label="Vincular a una solicitud social")

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = Catalogo.objects.filter(tipo='ITEM_GESTION', estado='ACTIVO').order_by('id')
        self.fields['territorio'].queryset = territorios_para(usuario) if usuario else Territorio.objects.none()
        if usuario is not None:
            self.fields['encargado'].queryset = funcionarios_para(usuario)
            self.fields['solicitud'].queryset = solicitudes_para(usuario)
        if not self.is_bound:
            self.initial.setdefault('fecha_realizacion', timezone.localdate())

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if imagen:
            for error in validar_imagen(imagen):
                self.add_error('imagen', error)
        return imagen

    def clean(self):
        datos = super().clean()
        hoy = timezone.localdate()
        if datos.get('depende_externos'):
            # En el Tubo todavía no hay ejecución. La fecha es opcional: si se elige, no puede ser pasada
            fecha = datos.get('fecha_realizacion')
            if fecha is not None and fecha < hoy:
                self.add_error('fecha_realizacion', "La fecha de ejecución no puede ser anterior a hoy.")
            datos['comentario'] = ''
            datos['imagen'] = None
            return datos

        fecha = datos.get('fecha_realizacion')
        if fecha is None:
            if 'fecha_realizacion' not in self.errors:
                self.add_error('fecha_realizacion', "Indique la fecha de ejecución de la actividad, "
                                                    "o márquela como dependiente de factores externos.")
            return datos
        if fecha <= hoy:
            # Se registra ejecutada: el comentario es obligatorio, la foto no
            if not (datos.get('comentario') or '').strip():
                self.add_error('comentario', "Escriba un comentario de lo que se hizo en la actividad.")
        else:
            # Es un compromiso: se ejecuta (comentario y foto) cuando llegue la fecha
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
        return 'REGISTRADA'


class EjecucionForm(forms.Form):
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


class AtencionForm(forms.ModelForm):
    """Solicitud social de una persona natural. La fecha de ingreso y quién la registra se guardan solos."""
    class Meta:
        model = AtencionSocial
        fields = ['nombre_solicitante', 'rut_solicitante', 'telefono_solicitante', 'tipo_atencion', 'subtipo_atencion',
                  'requiere_visita']
        labels = {'nombre_solicitante': "Nombre del solicitante", 'rut_solicitante': "RUT del solicitante",
                  'telefono_solicitante': "Teléfono", 'requiere_visita': "Requiere visita domiciliaria"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_atencion'].queryset = Catalogo.objects.filter(tipo='TIPO_ATENCION', estado='ACTIVO')
        self.fields['subtipo_atencion'].queryset = Catalogo.objects.filter(tipo='SUBTIPO_ATENCION', estado='ACTIVO')
        self.fields['tipo_atencion'].empty_label = "Seleccione el tipo..."
        self.fields['subtipo_atencion'].empty_label = "Sin subtipo"

    def clean_rut_solicitante(self):
        rut = limpiar_rut(self.cleaned_data['rut_solicitante'])
        if len(rut) > 12 or not validar_rut(rut):
            raise forms.ValidationError("El RUT del solicitante no es válido.")
        return rut

    def clean(self):
        datos = super().clean()
        tipo = datos.get('tipo_atencion')
        subtipo = datos.get('subtipo_atencion')
        if tipo and subtipo and subtipo.padre_id not in (None, tipo.pk):
            self.add_error('subtipo_atencion', "El subtipo no corresponde al tipo de atención elegido.")
        return datos
