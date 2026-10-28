"""Plan de Pruebas Unitarias: actividades (CP-ACT), registro de ejecución (CP-EVI), validación (CP-VAL),
compromisos y Tubo de Trabajo (CP-COM) y seguridad y permisos (CP-SEG, CP-PER)."""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from ActividadesApp.models import Actividad, Evidencia, Validacion
from ActividadesApp.tests import BaseActividades, foto, PNG
from ActividadesApp.views import puede_ver_actividad, validar_imagen
from AuditoriaApp.models import Auditoria
from IndicadoresApp.calculos import indicadores_usuario
from IndicadoresApp.models import Periodo


class BasePlan(BaseActividades):
    def mensajes(self, respuesta):
        return [str(m) for m in respuesta.context['messages']] if respuesta.context else []

    def errores(self, respuesta):
        """Errores del formulario de registro (por campo y generales)."""
        return respuesta.context['form'].errors


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PlanActividadesTest(BasePlan):
    def test_cp_act_001_registro_exitoso(self):
        self.entrar('55555555-5')
        self.assertRedirects(self.registrar(), reverse('actividades:mi_gestion'))
        actividad = Actividad.objects.get()
        self.assertEqual(actividad.folio(), f"ACT{actividad.pk}")
        self.assertEqual((actividad.usuario, actividad.periodo, actividad.item, actividad.territorio),
                         (self.func, self.datos['periodo'], self.datos['item'], self.territorio))
        self.assertEqual(actividad.estado, 'REGISTRADA')

    def test_cp_act_002_descripcion_vacia(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(solicitud_problema='')
        self.assertIn('solicitud_problema', self.errores(respuesta))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_003_accion_vacia_o_muy_larga(self):
        self.entrar('55555555-5')
        self.assertIn('accion', self.errores(self.registrar(accion='')))
        self.assertIn('accion', self.errores(self.registrar(accion='x' * 256)))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_004_item_inexistente(self):
        self.entrar('55555555-5')
        self.assertIn('item', self.errores(self.registrar(item='999')))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_005_periodo_inexistente(self):
        Periodo.objects.update(fecha_inicio=self.hoy + timedelta(days=30), fecha_termino=self.hoy + timedelta(days=60))
        self.entrar('55555555-5')
        respuesta = self.registrar()
        self.assertIn("No hay un periodo vigente abierto: no se pueden registrar actividades.",
                      respuesta.context['form'].non_field_errors())
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_006_periodo_cerrado(self):
        self.datos['periodo'].cerrar()
        self.entrar('55555555-5')
        respuesta = self.registrar()
        self.assertIn("No hay un periodo vigente abierto: no se pueden registrar actividades.",
                      respuesta.context['form'].non_field_errors())
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_007_actividad_al_tubo(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(depende_externos='on', fecha_realizacion='')
        self.assertRedirects(respuesta, reverse('actividades:tubo_trabajo'))
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.estado, actividad.depende_externos, actividad.fecha_realizacion), ('EN_TUBO', True, None))

    def test_cp_act_008_registro_de_ejecucion_al_crear(self):
        self.entrar('55555555-5')
        self.registrar(imagen=foto())
        ejecucion = Actividad.objects.get().evidencias.get()
        self.assertEqual((ejecucion.version, ejecucion.estado_revision), (1, 'PENDIENTE'))
        self.assertTrue(ejecucion.codigo().startswith('ORC'))

    def test_cp_act_009_fecha_futura_es_compromiso(self):
        self.entrar('55555555-5')
        futura = self.hoy + timedelta(days=10)
        self.registrar(fecha_realizacion=futura.isoformat(), comentario='', imagen=foto())
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.estado, actividad.fecha_realizacion, actividad.evidencias.count()),
                         ('PROGRAMADA', futura, 0))  # la foto de un compromiso se ignora hasta que se ejecute

    def test_cp_act_010_sin_fecha_de_realizacion(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(fecha_realizacion='')
        self.assertIn('fecha_realizacion', self.errores(respuesta))
        self.assertEqual(Actividad.objects.count(), 0)


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PlanEvidenciasTest(BasePlan):
    def ejecutar_y_seguir(self, actividad, **datos):
        datos.setdefault('comentario', 'Trabajo realizado')
        return self.client.post(reverse('actividades:registrar_ejecucion', args=[actividad.pk]), datos, follow=True)

    def test_cp_evi_001_ejecucion_con_foto(self):
        actividad = self.crear()
        self.entrar('55555555-5')
        self.ejecutar_y_seguir(actividad, imagen=SimpleUploadedFile('evidencia.jpg', PNG, content_type='image/jpeg'))
        actividad.refresh_from_db()
        self.assertEqual((actividad.evidencias.count(), actividad.estado), (1, 'REGISTRADA'))
        detalle = self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]))
        self.assertEqual(len(detalle.context['ejecuciones']), 1)

    def test_cp_evi_002_formato_pdf(self):
        self.assertEqual(validar_imagen(SimpleUploadedFile('evidencia.pdf', b'%PDF-1.4', content_type='application/pdf')),
                         ["La fotografía debe ser JPG o PNG."])
        actividad = self.crear()
        self.entrar('55555555-5')
        respuesta = self.ejecutar_y_seguir(actividad, imagen=SimpleUploadedFile('evidencia.pdf', b'%PDF-1.4'))
        self.assertTrue(self.mensajes(respuesta))  # se informa el error
        self.assertEqual(actividad.evidencias.count(), 0)

    def test_cp_evi_003_formato_no_permitido(self):
        for nombre in ['evidencia.gif', 'evidencia.exe', 'evidencia.docx']:
            self.assertEqual(validar_imagen(SimpleUploadedFile(nombre, b'contenido')), ["La fotografía debe ser JPG o PNG."])

    def test_cp_evi_004_imagen_superior_a_5mb(self):
        grande = SimpleUploadedFile('grande.png', b'0' * (5 * 1024 * 1024 + 1), content_type='image/png')
        self.assertEqual(validar_imagen(grande), ["La fotografía no puede superar 5 MB."])

    def test_cp_evi_005_sin_foto_es_valido_sin_comentario_no(self):
        actividad = self.crear()
        self.entrar('55555555-5')
        self.ejecutar_y_seguir(actividad, comentario='')
        self.assertEqual(actividad.evidencias.count(), 0)
        self.ejecutar_y_seguir(actividad, comentario='Se realizó la visita')
        self.assertEqual(actividad.evidencias.count(), 1)
        self.assertFalse(actividad.evidencias.get().imagen)

    def test_cp_evi_006_nueva_version_de_ejecucion(self):
        actividad, evidencia = self.ejecutada()
        evidencia.estado_revision = 'RECHAZADA'
        evidencia.save()
        actividad.sincronizar_estado()
        self.entrar('55555555-5')
        self.ejecutar_y_seguir(actividad)
        nueva = actividad.ejecucion_vigente()
        self.assertEqual((nueva.version, nueva.reemplaza_a), (2, evidencia))
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'REGISTRADA')


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PlanValidacionTest(BasePlan):
    def decidir(self, evidencia, **datos):
        return self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]), datos, follow=True)

    def test_cp_val_001_aprobacion(self):
        actividad, evidencia = self.ejecutada()
        self.entrar('33333333-3')
        self.decidir(evidencia, decision='APROBAR', observacion='Bien registrada')
        evidencia.refresh_from_db()
        actividad.refresh_from_db()
        self.assertEqual((evidencia.estado_revision, actividad.estado), ('APROBADA', 'VALIDADA'))
        indicador = indicadores_usuario(self.func, self.datos['periodo'], self.hoy)[0]
        self.assertEqual(indicador.avance_actual, 1)

    def test_cp_val_002_rechazo(self):
        actividad, evidencia = self.ejecutada()
        self.entrar('33333333-3')
        self.decidir(evidencia, decision='RECHAZAR', observacion='Comentario incompleto')
        evidencia.refresh_from_db()
        actividad.refresh_from_db()
        self.assertEqual((evidencia.estado_revision, actividad.estado), ('RECHAZADA', 'RECHAZADA'))
        self.assertEqual(evidencia.validacion.observacion, 'Comentario incompleto')
        indicador = indicadores_usuario(self.func, self.datos['periodo'], self.hoy)[0]
        self.assertEqual(indicador.avance_actual, 0)

    def test_cp_val_003_rechazo_sin_observacion(self):
        actividad, evidencia = self.ejecutada()
        self.entrar('33333333-3')
        respuesta = self.decidir(evidencia, decision='RECHAZAR', observacion='')
        self.assertTrue(any('debe escribir una observación' in m for m in self.mensajes(respuesta)))
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.estado_revision, 'PENDIENTE')

    def test_cp_val_004_ejecucion_ya_validada(self):
        actividad, evidencia = self.ejecutada()
        self.entrar('33333333-3')
        self.decidir(evidencia, decision='APROBAR')
        respuesta = self.decidir(evidencia, decision='RECHAZAR', observacion='Cambio de opinión')
        self.assertIn("Esta evidencia ya fue revisada.", self.mensajes(respuesta))
        self.assertEqual(Validacion.objects.count(), 1)

    def test_cp_val_005_decision_invalida(self):
        actividad, evidencia = self.ejecutada()
        self.entrar('33333333-3')
        respuesta = self.decidir(evidencia, decision='BORRAR')
        self.assertIn("Decisión no válida.", self.mensajes(respuesta))
        self.assertEqual(Validacion.objects.count(), 0)

    def test_cp_val_006_validacion_de_actividad_propia(self):
        actividad, evidencia = self.ejecutada(usuario=self.admin)
        self.entrar('11111111-1')
        respuesta = self.decidir(evidencia, decision='APROBAR')
        self.assertIn("No puede validar una actividad que usted registró o tiene a su cargo.", self.mensajes(respuesta))
        self.assertEqual(Validacion.objects.count(), 0)

    def test_cp_val_007_validacion_fuera_de_delegacion(self):
        actividad, evidencia = self.ejecutada()  # funcionario de Las Compañías
        self.entrar('44444444-4')  # Delegado Rural
        respuesta = self.decidir(evidencia, decision='APROBAR')
        self.assertIn("Solo puede verificar evidencias de funcionarios de su delegación.", self.mensajes(respuesta))
        self.assertEqual(Validacion.objects.count(), 0)


class PlanCompromisosTest(BasePlan):
    def test_cp_com_001_registro_de_compromiso(self):
        self.entrar('55555555-5')
        futura = self.hoy + timedelta(days=10)
        self.registrar(fecha_realizacion=futura.isoformat())
        compromiso = Actividad.objects.get()
        self.assertTrue(compromiso.es_compromiso())
        self.assertEqual((compromiso.usuario, compromiso.fecha_realizacion), (self.func, futura))

    def test_cp_com_002_cambio_de_estado_queda_en_auditoria(self):
        compromiso = self.crear()
        self.entrar('55555555-5')
        self.ejecutar(compromiso)
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.estado, 'REGISTRADA')
        cambio = Auditoria.objects.get(evento='MODIFICACION', entidad='Actividad', id_entidad=str(compromiso.pk))
        self.assertEqual((cambio.valor_anterior, cambio.valor_nuevo, cambio.usuario), ('PROGRAMADA', 'REGISTRADA', self.func))

    def test_cp_com_003_compromiso_vencido(self):
        vencido = self.crear(dias=-2)
        self.assertTrue(vencido.vencido())
        self.entrar('55555555-5')
        pendientes = self.client.get(reverse('actividades:mi_gestion')).context['pendientes']
        self.assertEqual([(a['folio'], a['vencido']) for a in pendientes], [(vencido.folio(), True)])

    def test_cp_com_004_compromiso_proximo_a_vencer(self):
        proximo = self.crear(dias=2)
        lejano = self.crear(dias=20)
        self.assertTrue(proximo.proximo_a_vencer())
        self.assertFalse(lejano.proximo_a_vencer())
        self.entrar('55555555-5')
        pendientes = self.client.get(reverse('actividades:mi_gestion')).context['pendientes']
        self.assertEqual([a['folio'] for a in pendientes], [proximo.folio(), lejano.folio()])  # ordenados por fecha

    def test_cp_com_005_tubo_filtro_por_responsable(self):
        propio = self.crear('EN_TUBO')
        ajeno = self.crear('EN_TUBO', usuario=self.companero)
        self.entrar('55555555-5')
        self.assertEqual(self.folios_tubo(responsable=str(self.companero.pk)), [ajeno.folio()])
        self.assertEqual(self.folios_tubo(mios='1'), [propio.folio()])

    def test_cp_com_006_tubo_filtro_por_estado(self):
        pendiente = self.crear('EN_TUBO')
        ejecutada = self.crear('EN_TUBO')
        Evidencia.objects.create(actividad=ejecutada, comentario='Hecho', version=1)
        ejecutada.sincronizar_estado()
        self.entrar('55555555-5')
        self.assertEqual(self.folios_tubo(), [pendiente.folio()])
        self.assertEqual(self.folios_tubo(estado='EJECUTADAS'), [ejecutada.folio()])

    def test_cp_com_007_tubo_filtro_por_territorio(self):
        alto = self.crear('EN_TUBO')
        self.crear('EN_TUBO', territorio=self.territorio_bajo)
        self.entrar('55555555-5')
        self.assertEqual(self.folios_tubo(territorio=self.territorio.pk), [alto.folio()])

    def test_cp_com_008_asignacion_de_encargado_queda_en_auditoria(self):
        compromiso = self.crear()
        self.entrar('33333333-3')
        self.client.post(reverse('actividades:asignar_encargado', args=[compromiso.pk]), {'encargado': self.companero.pk})
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.encargado, self.companero)
        cambio = Auditoria.objects.get(evento='MODIFICACION', entidad='Actividad', id_entidad=str(compromiso.pk))
        self.assertIn('encargado=', cambio.valor_nuevo)


class PlanSeguridadTest(BasePlan):
    def test_cp_seg_001_acceso_fuera_del_ambito(self):
        actividad = self.crear(usuario=self.otro, territorio=self.territorio_rural)
        self.entrar('55555555-5')
        respuesta = self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]))
        self.assertRedirects(respuesta, reverse('actividades:mi_gestion'))
        self.assertTrue(Auditoria.objects.filter(evento='ACCESO_DENEGADO', usuario=self.func).exists())

    def test_cp_seg_002_restriccion_por_permisos(self):
        self.entrar('55555555-5')
        for nombre in ['users:administracion', 'auditoria:logs', 'actividades:verificacion']:
            self.assertRedirects(self.client.get(reverse(nombre)), reverse('actividades:mi_gestion'), msg_prefix=nombre)
        self.assertEqual(Auditoria.objects.filter(evento='ACCESO_DENEGADO').count(), 3)

    def test_cp_seg_004_actividad_de_otra_delegacion(self):
        actividad = self.crear(usuario=self.otro, territorio=self.territorio_rural)
        self.assertFalse(puede_ver_actividad(self.func, actividad))
        self.assertFalse(puede_ver_actividad(self.delegado, actividad))
        self.assertTrue(puede_ver_actividad(self.coordinador, actividad))

    def test_cp_seg_005_acceso_dentro_de_la_delegacion(self):
        actividad = self.crear()
        self.assertTrue(puede_ver_actividad(self.companero, actividad))
        self.assertTrue(puede_ver_actividad(self.delegado, actividad))
        self.entrar('77777777-7')
        self.assertEqual(self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk])).status_code, 200)

    def test_cp_per_001_intento_queda_registrado(self):
        actividad = self.crear(usuario=self.otro, territorio=self.territorio_rural)
        self.entrar('55555555-5')
        self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]))
        intento = Auditoria.objects.get(evento='ACCESO_DENEGADO')
        self.assertIn(actividad.folio(), intento.valor_nuevo)

    def test_cp_per_002_filtrado_por_ambito(self):
        propio = self.crear('EN_TUBO')
        self.crear('EN_TUBO', usuario=self.otro, territorio=self.territorio_rural)
        self.entrar('33333333-3')  # Delegado de Las Compañías
        self.assertEqual(self.folios_tubo(estado='TODOS'), [propio.folio()])
        # Aunque pida otra delegación por la URL, el Delegado sigue viendo solo la suya
        self.assertEqual(self.folios_tubo(estado='TODOS', delegacion='RURAL'), [propio.folio()])
