from django.test import TestCase
from django.urls import reverse

from AuditoriaApp.models import Auditoria
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE


class AuditoriaTest(TestCase):
    def test_acceso_denegado_queda_registrado(self):
        crear_datos_base()
        crear_usuario('55555555-5', 'Funcionario')
        self.client.login(username='55555555-5', password=CLAVE)
        self.client.get(reverse('auditoria:logs'))
        self.assertEqual(Auditoria.objects.filter(evento='ACCESO_DENEGADO').count(), 1)
