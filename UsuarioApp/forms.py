from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from UsuarioApp.choices import roles, opciones_delegacion
from UsuarioApp.funciones import limpiar_rut, validar_rut
from UsuarioApp.models import Usuario


class UsuarioCrearForm(forms.Form):
    rut = forms.CharField(max_length=15, label="RUT")
    email = forms.EmailField(max_length=254, label="Correo")
    first_name = forms.CharField(max_length=100, label="Nombres")
    last_name = forms.CharField(max_length=100, label="Apellidos")
    rol = forms.ChoiceField(choices=roles, label="Rol")
    cargo = forms.CharField(max_length=150, required=False, label="Cargo")
    password1 = forms.CharField(label="Contraseña")
    password2 = forms.CharField(label="Confirmar contraseña")

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
        fields = ['email', 'first_name', 'last_name', 'cargo', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
