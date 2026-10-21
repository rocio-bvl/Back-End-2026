"""Plan de Pruebas Unitarias: registro de auditoría (CP-AUD)."""
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings
from django.urls import reverse

from ActividadesApp.models import Actividad, Evidencia
from ActividadesApp.tests import foto
from AuditoriaApp.models import Auditoria
from AuditoriaApp.registro import registrar_auditoria
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PlanAuditoriaTest(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        self.delegado = crear_usuario('33333333-3', 'Delegado', self.datos['delegacion'])

    def registrar_actividad(self):
        self.client.login(username='55555555-5', password=CLAVE)
        return self.client.post(reverse('actividades:actividad_crear'), {
            'solicitud_problema': 'Vecinos piden poda', 'accion': 'Inspección', 'item_comision': '1',
            'contacto': 'Juan', 'telefono': '912345678', 'territorio': 'Sector Alto', 'evidencia_imagen': foto()})

    def test_cp_aud_001_registro_operacion_critica(self):
        registro = registrar_auditoria(self.func, 'CREACION', 'Actividad', 15, '', 'ACT15 - Inspección')
        guardado = Auditoria.objects.get(pk=registro.pk)
        self.assertEqual((guardado.usuario, guardado.evento, guardado.entidad, guardado.id_entidad),
                         (self.func, 'CREACION', 'Actividad', '15'))
        self.assertEqual(guardado.valor_nuevo, 'ACT15 - Inspección')
        self.assertIsNotNone(guardado.fecha)

    def test_cp_aud_002_registro_de_modificacion(self):
        self.registrar_actividad()
        evidencia = Evidencia.objects.get()
        self.client.login(username='33333333-3', password=CLAVE)
        self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]), {'decision': 'APROBAR'})
        cambio = Auditoria.objects.get(evento='MODIFICACION', entidad='Evidencia')
        self.assertEqual((cambio.usuario, cambio.valor_anterior, cambio.valor_nuevo), (self.delegado, 'PENDIENTE', 'APROBADA'))

    def test_cp_aud_003_registro_sin_usuario_autenticado(self):
        registro = registrar_auditoria(AnonymousUser(), 'ACCESO_DENEGADO', 'Vista', '/auditoria/', '', 'Intento sin sesión')
        self.assertIsNone(Auditoria.objects.get(pk=registro.pk).usuario)

    def test_cp_aud_004_registro_creacion_evidencia(self):
        self.registrar_actividad()
        evidencia = Evidencia.objects.get()
        self.assertTrue(Auditoria.objects.filter(evento='CREACION', entidad='Evidencia',
                                                 id_entidad=str(evidencia.pk), usuario=self.func).exists())

    def test_cp_aud_005_registro_creacion_actividad(self):
        self.registrar_actividad()
        actividad = Actividad.objects.get()
        self.assertTrue(Auditoria.objects.filter(evento='CREACION', entidad='Actividad',
                                                 id_entidad=str(actividad.pk), usuario=self.func).exists())
