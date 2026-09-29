from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import Actividad, Compromiso, Evidencia
from UsuarioApp.models import Delegacion
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


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class TuboColectivoYActividadDeCompromisoTest(TestCase):
    """HU-12 (agenda visible para la delegación, filtros) y registro de la actividad con la que
    el responsable ejecuta un compromiso."""

    def setUp(self):
        self.datos = crear_datos_base()
        compania = self.datos['delegacion']
        self.rural = Delegacion.objects.get(nombre='RURAL')
        self.resp = crear_usuario('55555555-5', 'Funcionario', compania, self.datos['cargo'])
        self.companero = crear_usuario('77777777-7', 'Funcionario', compania, self.datos['cargo'])
        self.otro = crear_usuario('88888888-8', 'Funcionario', self.rural, self.datos['cargo'])
        self.delegado = crear_usuario('33333333-3', 'Delegado', compania)
        self.compromiso = Compromiso.objects.create(
            origen='JJ.VV. Villa Ejemplo', solicitante='JJ.VV.', observacion='Reparar luminaria',
            territorio='Sector Alto', fecha_comprometida=timezone.localdate() + timedelta(days=5),
            delegacion=compania, registrado_por=self.delegado, responsable=self.resp)
        self.vencido = Compromiso.objects.create(
            origen='Vecina', solicitante='Vecina', observacion='Poda', territorio='Sector Bajo',
            fecha_comprometida=timezone.localdate() - timedelta(days=2),
            delegacion=compania, registrado_por=self.delegado, responsable=self.companero)
        self.url_tubo = reverse('actividades:tubo_trabajo')

    def folios(self, respuesta):
        return [c['id_compromiso'] for c in respuesta.context['compromisos']]

    def test_companero_de_delegacion_ve_todo_el_tubo(self):
        self.client.login(username='77777777-7', password=CLAVE)
        folios = self.folios(self.client.get(self.url_tubo))
        self.assertIn(self.compromiso.folio(), folios)
        self.assertIn(self.vencido.folio(), folios)

    def test_otra_delegacion_no_ve_el_tubo_ajeno(self):
        self.client.login(username='88888888-8', password=CLAVE)
        self.assertEqual(self.folios(self.client.get(self.url_tubo)), [])
        detalle = self.client.get(reverse('actividades:compromiso_detalle', args=[self.compromiso.pk]))
        self.assertNotIn(self.compromiso.origen, detalle.content.decode())

    def test_filtros(self):
        self.client.login(username='55555555-5', password=CLAVE)
        self.assertEqual(self.folios(self.client.get(self.url_tubo, {'mios': '1'})), [self.compromiso.folio()])
        self.assertEqual(self.folios(self.client.get(self.url_tubo, {'estado': 'VENCIDOS'})), [self.vencido.folio()])
        self.assertEqual(self.folios(self.client.get(self.url_tubo, {'territorio': 'alto'})), [self.compromiso.folio()])
        self.assertEqual(self.folios(self.client.get(self.url_tubo, {'responsable': self.companero.pk})), [self.vencido.folio()])
        # Una fecha mal escrita no rompe la página
        self.assertEqual(self.client.get(self.url_tubo, {'desde': 'no-es-fecha'}).status_code, 200)

    def test_companero_ve_detalle_pero_no_cambia_estado(self):
        self.client.login(username='77777777-7', password=CLAVE)
        url = reverse('actividades:compromiso_detalle', args=[self.compromiso.pk])
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context['puede_gestionar'])
        self.assertFalse(respuesta.context['puede_registrar_actividad'])
        self.client.post(url, {'estado': 'PENDIENTE', 'observacion': 'intento'})
        self.compromiso.refresh_from_db()
        self.assertEqual(self.compromiso.estado, 'INGRESADO')

    def test_responsable_registra_actividad_del_compromiso(self):
        self.client.login(username='55555555-5', password=CLAVE)
        url = reverse('actividades:actividad_crear') + f'?compromiso={self.compromiso.pk}'
        self.assertContains(self.client.get(url), self.compromiso.folio())
        foto = SimpleUploadedFile('foto.png', PNG, content_type='image/png')
        respuesta = self.client.post(url, {
            'compromiso': self.compromiso.pk, 'solicitud_problema': 'Se repara luminaria',
            'accion': 'Gestión con alumbrado', 'item_comision': '1', 'evidencia_imagen': foto,
            'ingreso_agenda_colectiva': 'on'})
        self.assertRedirects(respuesta, reverse('actividades:compromiso_detalle', args=[self.compromiso.pk]))
        actividad = Actividad.objects.get()
        self.assertEqual(actividad.compromiso, self.compromiso)
        self.assertTrue(actividad.ingreso_agenda_colectiva)
        self.assertEqual(Compromiso.objects.count(), 2)  # no se creó un compromiso nuevo
        detalle = self.client.get(reverse('actividades:compromiso_detalle', args=[self.compromiso.pk]))
        self.assertEqual(len(detalle.context['actividades']), 1)

    def test_quien_no_es_responsable_no_registra(self):
        self.client.login(username='77777777-7', password=CLAVE)
        self.client.post(reverse('actividades:actividad_crear'), {
            'compromiso': self.compromiso.pk, 'solicitud_problema': 'x', 'accion': 'y', 'item_comision': '1'})
        self.assertEqual(Actividad.objects.count(), 0)

    def test_compromiso_realizado_no_admite_actividades(self):
        self.compromiso.estado = 'REALIZADO'
        self.compromiso.save()
        self.client.login(username='55555555-5', password=CLAVE)
        self.client.post(reverse('actividades:actividad_crear'), {
            'compromiso': self.compromiso.pk, 'solicitud_problema': 'x', 'accion': 'y', 'item_comision': '1'})
        self.assertEqual(Actividad.objects.count(), 0)

    def test_sin_delegacion_la_casilla_no_queda_marcada(self):
        crear_usuario('99999999-9', 'Funcionario', None, self.datos['cargo'])
        self.client.login(username='99999999-9', password=CLAVE)
        self.client.post(reverse('actividades:actividad_crear'), {
            'solicitud_problema': 'x', 'accion': 'y', 'item_comision': '1', 'ingreso_agenda_colectiva': 'on'})
        actividad = Actividad.objects.get()
        self.assertFalse(actividad.ingreso_agenda_colectiva)
        self.assertIsNone(actividad.compromiso)