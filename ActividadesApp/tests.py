from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import Actividad, Evidencia
from UsuarioApp.models import Delegacion
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE

# PNG de 1x1 pixel
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
       b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


def foto():
    return SimpleUploadedFile('foto.png', PNG, content_type='image/png')


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class FlujoActividadTest(TestCase):
    """Con evidencia: REGISTRADA -> el Delegado valida (VALIDADA) (completada) o rechaza la evidencia (RECHAZADA -> se resube).
    Sin evidencia: compromiso en el Tubo (EN_TUBO) con fecha límite hasta que el mismo funcionario la ejecuta."""

    def setUp(self):
        self.datos = crear_datos_base()
        compania = self.datos['delegacion']
        self.func = crear_usuario('55555555-5', 'Funcionario', compania, self.datos['cargo'])
        self.companero = crear_usuario('77777777-7', 'Funcionario', compania, self.datos['cargo'])
        self.otro = crear_usuario('88888888-8', 'Funcionario', Delegacion.objects.get(nombre='RURAL'), self.datos['cargo'])
        self.delegado = crear_usuario('33333333-3', 'Delegado', compania)
        self.hoy = timezone.localdate()

    def entrar(self, rut):
        self.client.login(username=rut, password=CLAVE)

    def registrar(self, **extra):
        datos = {'solicitud_problema': 'Vecinos piden poda', 'accion': 'Inspección', 'item_comision': '1',
                 'contacto': 'Juan', 'telefono': '912345678', 'territorio': 'Sector Alto'}
        datos.update(extra)
        return self.client.post(reverse('actividades:actividad_crear'), datos)

    def en_tubo(self, usuario=None, dias=5, territorio='Sector Alto'):
        return Actividad.objects.create(
            solicitud_problema='Reparar luminaria', accion='Gestión con alumbrado', item=self.datos['item'],
            periodo=self.datos['periodo'], usuario=usuario or self.func, estado='EN_TUBO', ingreso_agenda_colectiva=True,
            fecha_comprometida=self.hoy + timedelta(days=dias), territorio=territorio)

    def folios_tubo(self, **filtros):
        return [c['folio'] for c in self.client.get(reverse('actividades:tubo_trabajo'), filtros).context['compromisos']]

    # ----- registro -----
    def test_con_evidencia_queda_registrada(self):
        self.entrar('55555555-5')
        self.registrar(evidencia_imagen=foto())
        actividad = Actividad.objects.get()
        self.assertEqual(actividad.estado, 'REGISTRADA')
        self.assertFalse(actividad.ingreso_agenda_colectiva)
        self.assertIsNone(actividad.fecha_comprometida)
        self.assertEqual(actividad.evidencias.count(), 1)

    def test_sin_evidencia_y_sin_tubo_no_se_guarda(self):
        self.entrar('55555555-5')
        self.assertEqual(self.registrar().status_code, 200)
        self.assertEqual(Actividad.objects.count(), 0)

    def test_sin_evidencia_pasa_al_tubo_con_fecha_limite(self):
        self.entrar('55555555-5')
        limite = self.hoy + timedelta(days=7)
        respuesta = self.registrar(ingreso_agenda_colectiva='on', fecha_comprometida=limite.isoformat())
        self.assertRedirects(respuesta, reverse('actividades:tubo_trabajo'))
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.estado, actividad.fecha_comprometida, actividad.ingreso_agenda_colectiva), ('EN_TUBO', limite, True))
        self.assertTrue(actividad.es_compromiso())
        self.assertEqual(actividad.evidencias.count(), 0)
        # El compañero de delegación lo ve en la agenda colectiva
        self.entrar('77777777-7')
        self.assertEqual(self.folios_tubo(), [actividad.folio()])

    def test_tubo_exige_fecha_limite_valida_y_sin_foto(self):
        self.entrar('55555555-5')
        self.registrar(ingreso_agenda_colectiva='on')
        self.registrar(ingreso_agenda_colectiva='on', fecha_comprometida=(self.hoy - timedelta(days=1)).isoformat())
        self.registrar(ingreso_agenda_colectiva='on', fecha_comprometida='no-es-fecha')
        self.registrar(ingreso_agenda_colectiva='on', fecha_comprometida=self.hoy.isoformat(), evidencia_imagen=foto())
        self.assertEqual(Actividad.objects.count(), 0)

    def test_telefono_muy_largo_no_rompe(self):
        self.entrar('55555555-5')
        self.assertEqual(self.registrar(telefono='9' * 30, evidencia_imagen=foto()).status_code, 200)
        self.assertEqual(Actividad.objects.count(), 0)

    # ----- ejecutar el compromiso -----
    def test_ejecutar_compromiso_lo_saca_del_tubo(self):
        actividad = self.en_tubo()
        self.entrar('55555555-5')
        self.client.post(reverse('actividades:subir_evidencia', args=[actividad.pk]), {'evidencia_imagen': foto(), 'comentario': 'Listo'})
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'REGISTRADA')
        self.assertTrue(actividad.ingreso_agenda_colectiva)  # queda la constancia de que fue compromiso
        self.assertEqual(self.folios_tubo(), [])
        self.assertEqual(self.folios_tubo(estado='EN_REVISION'), [actividad.folio()])
        self.assertEqual(self.folios_tubo(estado='COMPLETADOS'), [])

    def test_solo_el_mismo_funcionario_ejecuta(self):
        actividad = self.en_tubo()
        self.entrar('55555555-5')
        self.assertContains(self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk])), 'Subir evidencia')
        self.assertContains(self.client.get(reverse('actividades:mi_gestion')), 'Ejecutar')
        self.entrar('77777777-7')
        detalle = self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]))
        self.assertFalse(detalle.context['puede_subir'])
        self.client.post(reverse('actividades:subir_evidencia', args=[actividad.pk]), {'evidencia_imagen': foto()})
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'EN_TUBO')

    # ----- validación del Delegado -----
    def actividad_registrada(self):
        actividad = Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'],
                                             periodo=self.datos['periodo'], usuario=self.func)
        evidencia = Evidencia.objects.create(actividad=actividad, imagen='evidencias/x.png')
        actividad.sincronizar_estado()
        return actividad, evidencia

    def test_delegado_valida_y_suma_avance(self):
        actividad, evidencia = self.actividad_registrada()
        self.assertEqual(actividad.estado, 'REGISTRADA')
        self.entrar('33333333-3')
        pantalla = self.client.get(reverse('actividades:verificacion'), {'evidencia_id': evidencia.pk})
        self.assertContains(pantalla, actividad.folio())
        self.assertContains(pantalla, 'value="RECHAZAR"')
        self.assertNotContains(pantalla, 'value="CORREGIR"')
        self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]), {'decision': 'APROBAR'})
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'VALIDADA')
        self.assertTrue(actividad.completada())
        self.entrar('55555555-5')
        self.assertEqual(self.client.get(reverse('actividades:mi_gestion')).context['metas'][0]['avance_actual'], 1)

    def test_rechazo_exige_motivo_se_muestra_y_se_resube(self):
        actividad, evidencia = self.actividad_registrada()
        url = reverse('actividades:validar_evidencia', args=[evidencia.pk])
        self.entrar('33333333-3')
        self.client.post(url, {'decision': 'CORREGIR', 'observacion': 'x'})  # decisión que ya no existe
        self.client.post(url, {'decision': 'RECHAZAR'})                      # sin motivo
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.estado_revision, 'PENDIENTE')
        self.client.post(url, {'decision': 'RECHAZAR', 'observacion': 'La foto no muestra la luminaria'})
        actividad.refresh_from_db()
        evidencia.refresh_from_db()
        self.assertEqual((actividad.estado, evidencia.estado_revision), ('RECHAZADA', 'RECHAZADA'))
        # El funcionario la ve rechazada, con el motivo y la opción de resubir
        self.entrar('55555555-5')
        detalle = self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]))
        self.assertContains(detalle, 'RECHAZADA')
        self.assertContains(detalle, 'La foto no muestra la luminaria')
        self.assertTrue(detalle.context['puede_subir'])
        self.assertContains(self.client.get(reverse('actividades:mi_gestion')), 'Resubir evidencia')
        # Resube: nueva versión que reemplaza a la rechazada y vuelve a validación
        self.client.post(reverse('actividades:subir_evidencia', args=[actividad.pk]), {'evidencia_imagen': foto()})
        actividad.refresh_from_db()
        nueva = actividad.evidencia_vigente()
        self.assertEqual((actividad.estado, nueva.version, nueva.reemplaza_a_id), ('REGISTRADA', 2, evidencia.pk))

    def test_registrada_no_admite_otra_evidencia(self):
        actividad, evidencia = self.actividad_registrada()
        self.entrar('55555555-5')
        self.client.post(reverse('actividades:subir_evidencia', args=[actividad.pk]), {'evidencia_imagen': foto()})
        self.assertEqual(actividad.evidencias.count(), 1)

    # ----- Tubo de Trabajo -----
    def test_filtros_del_tubo(self):
        propio = self.en_tubo(dias=10, territorio='Sector Alto')
        vencido = Actividad.objects.create(
            solicitud_problema='Poda', accion='Poda', item=self.datos['item'], periodo=self.datos['periodo'],
            usuario=self.companero, estado='EN_TUBO', ingreso_agenda_colectiva=True,
            fecha_comprometida=self.hoy - timedelta(days=2), territorio='Sector Bajo')
        por_vencer = self.en_tubo(usuario=self.companero, dias=1, territorio='Sector Bajo')
        self.entrar('55555555-5')
        self.assertEqual(self.folios_tubo(), [vencido.folio(), por_vencer.folio(), propio.folio()])
        self.assertEqual(self.folios_tubo(estado='VENCIDOS'), [vencido.folio()])
        self.assertEqual(self.folios_tubo(estado='POR_VENCER'), [por_vencer.folio()])
        self.assertEqual(self.folios_tubo(territorio='alto'), [propio.folio()])
        self.assertEqual(self.folios_tubo(mios='1'), [propio.folio()])
        self.assertEqual(self.folios_tubo(responsable=self.companero.pk), [vencido.folio(), por_vencer.folio()])
        self.assertEqual(self.client.get(reverse('actividades:tubo_trabajo'), {'desde': 'no-es-fecha'}).status_code, 200)
        self.assertTrue(vencido.vencido())
        self.assertTrue(por_vencer.proximo_a_vencer())

    def test_otra_delegacion_no_ve_el_tubo_ajeno(self):
        actividad = self.en_tubo()
        self.entrar('88888888-8')
        self.assertEqual(self.folios_tubo(), [])
        self.assertRedirects(self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk])),
                             reverse('actividades:mi_gestion'))

    def test_dashboard_cuenta_compromisos_pendientes(self):
        self.en_tubo()
        self.actividad_registrada()
        self.entrar('33333333-3')
        self.assertEqual(self.client.get(reverse('indicadores:dashboard')).context['compromisos_pendientes_count'], 1)

    def test_compromiso_validado_queda_completado(self):
        actividad = self.en_tubo()
        self.entrar('55555555-5')
        self.client.post(reverse('actividades:subir_evidencia', args=[actividad.pk]), {'evidencia_imagen': foto()})
        evidencia = actividad.evidencias.get()
        self.entrar('33333333-3')
        self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]), {'decision': 'APROBAR'})
        actividad.refresh_from_db()
        self.assertTrue(actividad.completada())
        self.assertEqual(self.folios_tubo(estado='COMPLETADOS'), [actividad.folio()])
        self.assertEqual(self.folios_tubo(), [])
        self.assertContains(self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk])), 'VALIDADA (COMPLETADA)')

    def test_compromiso_cuenta_en_el_trimestre_en_que_se_ejecuta(self):
        from IndicadoresApp.models import Periodo
        # Registrado en un trimestre anterior (ya terminado) y ejecutado en el vigente
        anterior = Periodo.objects.create(nombre='Anterior', fecha_inicio=self.hoy - timedelta(days=60),
                                          fecha_termino=self.hoy - timedelta(days=10), dias_computables=40)
        actividad = self.en_tubo()
        actividad.periodo = anterior
        actividad.save()
        self.entrar('55555555-5')
        self.client.post(reverse('actividades:subir_evidencia', args=[actividad.pk]), {'evidencia_imagen': foto()})
        actividad.refresh_from_db()
        self.assertEqual(actividad.periodo, self.datos['periodo'])
