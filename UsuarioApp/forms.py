from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from UsuarioApp.choices import roles
from UsuarioApp.funciones import opciones_delegacion
from UsuarioApp.funciones import limpiar_rut, validar_rut
from UsuarioApp.models import Usuario, Delegacion
from ActividadesApp.models import Territorio


def territorio_de_la_delegacion(territorio, codigo_delegacion):
    """El territorio debe ser de la misma delegación que el usuario."""
    if territorio is not None and (territorio.delegacion is None or territorio.delegacion.nombre != codigo_delegacion):
        raise ValidationError("El territorio no pertenece a la delegación elegida.")


class UsuarioCrearForm(forms.Form):
    rut = forms.CharField(max_length=15, label="RUT")
    email = forms.EmailField(max_length=254, label="Correo")
    first_name = forms.CharField(max_length=100, label="Nombres")
    last_name = forms.CharField(max_length=100, label="Apellidos")
    telefono = forms.CharField(max_length=20, required=False, label="Teléfono")
    rol = forms.ChoiceField(choices=roles, label="Perfil (grupo)")
    cargo = forms.CharField(max_length=150, required=False, label="Cargo")
    delegacion = forms.ChoiceField(choices=opciones_delegacion, required=False, label="Delegación")
    territorio = forms.ModelChoiceField(queryset=Territorio.objects.filter(estado='ACTIVO'), required=False,
                                        label="Territorio (solo Funcionarios)")
    password1 = forms.CharField(label="Contraseña")
    password2 = forms.CharField(label="Confirmar contraseña")

    def __init__(self, *args, roles_permitidos=None, **kwargs):
        super().__init__(*args, **kwargs)
        # El Coordinador no puede crear Coordinadores ni Administradores
        if roles_permitidos is not None:
            self.fields['rol'].choices = roles_permitidos

    def clean_rut(self):
        rut = limpiar_rut(self.cleaned_data['rut'])
        if len(rut) > 12 or not validar_rut(rut):
            raise ValidationError("El RUT no es válido.")
        if Usuario.objects.filter(username=rut).exists():
            raise ValidationError("Ya existe un usuario con ese RUT.")
        return rut

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise ValidationError("Ya existe un usuario con ese correo.")
        return email

    def clean(self):
        datos = super().clean()
        if datos.get('territorio') is not None and datos.get('rol') != 'Funcionario':
            datos['territorio'] = None  # solo los Funcionarios tienen territorio
        try:
            territorio_de_la_delegacion(datos.get('territorio'), datos.get('delegacion'))
        except ValidationError as error:
            self.add_error('territorio', error)
        clave1 = datos.get('password1')
        clave2 = datos.get('password2')
        if clave1 and clave2:
            if clave1 != clave2:
                self.add_error('password2', "Las contraseñas no coinciden.")
            else:
                try:
                    validate_password(clave1)
                except ValidationError as error:
                    self.add_error('password1', error)
        return datos


class UsuarioEditarForm(forms.ModelForm):
    rol = forms.ChoiceField(choices=roles, label="Rol")
    delegacion = forms.ChoiceField(choices=opciones_delegacion, label="Delegación")

    class Meta:
        model = Usuario
        fields = ['email', 'first_name', 'last_name', 'telefono', 'cargo', 'territorio', 'is_active']

    def __init__(self, *args, roles_permitidos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['territorio'].queryset = Territorio.objects.filter(estado='ACTIVO').select_related('delegacion')
        if roles_permitidos is not None:
            self.fields['rol'].choices = roles_permitidos

    def clean(self):
        datos = super().clean()
        if datos.get('territorio') is not None and datos.get('rol') != 'Funcionario':
            datos['territorio'] = None
        try:
            territorio_de_la_delegacion(datos.get('territorio'), datos.get('delegacion'))
        except ValidationError as error:
            self.add_error('territorio', error)
        return datos


class PerfilForm(forms.ModelForm):
    """Datos que cada usuario puede cambiar de sí mismo desde su perfil."""
    quitar_foto = forms.BooleanField(required=False, label="Quitar la foto actual")

    class Meta:
        model = Usuario
        fields = ['foto', 'telefono', 'email']
        labels = {'foto': "Foto de perfil (JPG o PNG, máx. 2 MB)", 'telefono': "Teléfono", 'email': "Correo electrónico"}
        widgets = {'foto': forms.FileInput(attrs={'accept': '.jpg,.jpeg,.png'})}

    def clean_foto(self):
        foto = self.cleaned_data.get('foto')
        if foto and hasattr(foto, 'size') and 'foto' in self.files:
            nombre = foto.name.lower()
            if not nombre.endswith(('.jpg', '.jpeg', '.png')):
                raise ValidationError("La foto debe ser JPG o PNG.")
            if foto.size > 2 * 1024 * 1024:
                raise ValidationError("La foto no puede superar 2 MB.")
        return foto

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un usuario con ese correo.")
        return email


class DelegacionForm(forms.ModelForm):
    """Delegación: el Administrador escribe el nombre; el código interno se arma solo (Las Compañías -> LAS_COMPANIAS)."""
    class Meta:
        model = Delegacion
        fields = ['nombre_visible', 'ambito', 'estado']
        labels = {'nombre_visible': "Nombre", 'ambito': "Ámbito (urbano o rural)"}

    def clean_nombre_visible(self):
        nombre = self.cleaned_data['nombre_visible'].strip()
        if not nombre:
            raise ValidationError("Escriba el nombre de la delegación.")
        codigo = codigo_delegacion(nombre)
        otras = Delegacion.objects.filter(nombre=codigo)
        if self.instance.pk:
            otras = otras.exclude(pk=self.instance.pk)
        if otras.exists():
            raise ValidationError("Ya existe una delegación con ese nombre.")
        return nombre

    def save(self, commit=True):
        delegacion = super().save(commit=False)
        if not delegacion.pk:
            delegacion.nombre = codigo_delegacion(delegacion.nombre_visible)
        if commit:
            delegacion.save()
        return delegacion


def codigo_delegacion(nombre):
    """'Las Compañías' -> 'LAS_COMPANIAS'"""
    import unicodedata
    sin_tildes = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode()
    return '_'.join(sin_tildes.upper().split())[:100]


# Territorios de una delegación, editables en la misma pantalla de la delegación
TerritorioFormSet = forms.inlineformset_factory(
    Delegacion, Territorio, fields=['nombre', 'estado'], extra=2, can_delete=False,
    labels={'nombre': "Territorio", 'estado': "Estado"})
