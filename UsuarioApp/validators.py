"""Validadores de contraseña propios del SGR (se activan en AUTH_PASSWORD_VALIDATORS de config/settings.py)."""
import re

from django.core.exceptions import ValidationError


class ContrasenaSeguraValidator:
    """Exige que la contraseña combine mayúsculas, minúsculas, números y símbolos especiales.
    Se suma a los validadores de Django (largo mínimo de 8, no ser común, no ser solo números y no parecerse
    al RUT o al nombre). Se aplica al crear un usuario y al elegir una contraseña nueva en la recuperación."""

    reglas = [
        (r'[A-ZÁÉÍÓÚÜÑ]', 'una letra mayúscula'),
        (r'[a-záéíóúüñ]', 'una letra minúscula'),
        (r'\d', 'un número'),
        (r'[^\w\s]|_', 'un símbolo especial (por ejemplo ! # $ % & * ?)'),
    ]

    def validate(self, password, user=None):
        faltan = [texto for patron, texto in self.reglas if not re.search(patron, password)]
        if faltan:
            if len(faltan) == 1:
                lista = faltan[0]
            else:
                lista = ', '.join(faltan[:-1]) + ' y ' + faltan[-1]
            raise ValidationError(f"La contraseña debe tener al menos {lista}.", code='password_sin_complejidad')

    def get_help_text(self):
        return "Su contraseña debe combinar letras mayúsculas, minúsculas, números y símbolos especiales."
