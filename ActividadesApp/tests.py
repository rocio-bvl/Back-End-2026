from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import Actividad, Compromiso, Evidencia
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE

# PNG de 1x1 pixel
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class ActividadYVerificacionTest(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        self.verif = crear_usuario('44444444-4', 'Verificador')

    def test_registrar_actividad_con_foto_y_tubo(self):
        self.client.login(username='55555555-5', password=CLAVE)
        foto = SimpleUploadedFile('foto.png', PNG, content_type='image/png')
        self.client.post(reverse('actividades:actividad_crear'), {
            'solicitud_problema': 'Vecinos piden poda', 'accion': 'Inspección', 'item_comision': '1',
            'contacto': 'Juan', 'telefono': '912345678', 'ingreso_agenda_colectiva': 'on', 'evidencia_imagen': foto})
        actividad = Actividad.objects.get()
        self.assertEqual(actividad.estado, 'EN_REVISION')
        self.assertIsNotNone(actividad.compromiso)
        self.assertEqual(actividad.compromiso.estado, 'INGRESADO')

    def test_telefono_muy_largo_no_rompe(self):
        self.client.login(username='55555555-5', password=CLAVE)
        respuesta = self.client.post(reverse('actividades:actividad_crear'), {
            'solicitud_problema': 'x', 'accion': 'y', 'item_comision': '1', 'telefono': '9' * 30})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Actividad.objects.count(), 0)

    def test_verificador_aprueba_y_suma_avance(self):
        actividad = Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'], periodo=self.datos['periodo'], usuario=self.func)
        evidencia = Evidencia.objects.create(actividad=actividad, imagen='evidencias/x.png')
        self.client.login(username='44444444-4', password=CLAVE)
        self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]), {'decision': 'APROBAR'})
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'VALIDADA')

        self.client.login(username='55555555-5', password=CLAVE)
        respuesta = self.client.get(reverse('actividades:mi_gestion'))
        self.assertEqual(respuesta.context['metas'][0]['avance_actual'], 1)


class CompromisoTest(TestCase):
    def setUp(self):
        datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', datos['delegacion'], datos['cargo'])
        self.delegado = crear_usuario('33333333-3', 'Delegado', datos['delegacion'])
        self.compromiso = Compromiso.objects.create(
            origen='JJ.VV.', solicitante='JJ.VV.', observacion='Luminarias',
            fecha_comprometida=timezone.localdate() + timedelta(days=5), delegacion=datos['delegacion'],
            registrado_por=self.delegado, responsable=self.func)

    def test_avanza_de_a_un_paso(self):
        ok, mensaje = self.compromiso.cambiar_estado('EN_PROCESO', self.func, 'salto')
        self.assertFalse(ok)
        ok, mensaje = self.compromiso.cambiar_estado('PENDIENTE', self.func, 'recibido')
        self.assertTrue(ok)
        self.assertEqual(self.compromiso.historial.count(), 1)

    def test_solo_supervision_retrocede(self):
        self.compromiso.cambiar_estado('PENDIENTE', self.func, 'recibido')
        ok, mensaje = self.compromiso.cambiar_estado('INGRESADO', self.func, 'volver')
        self.assertFalse(ok)
        ok, mensaje = self.compromiso.cambiar_estado('INGRESADO', self.delegado, 'volver')
        self.assertTrue(ok)

    def test_exige_observacion(self):
        ok, mensaje = self.compromiso.cambiar_estado('PENDIENTE', self.func, '  ')
        self.assertFalse(ok)

    def test_detalle_y_cambio_por_web(self):
        self.client.login(username='55555555-5', password=CLAVE)
        url = reverse('actividades:compromiso_detalle', args=[self.compromiso.pk])
        self.assertContains(self.client.get(url), 'INGRESADO')
        self.client.post(url, {'estado': 'PENDIENTE', 'observacion': 'ok'})
        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.estado, 'PENDIENTE')
