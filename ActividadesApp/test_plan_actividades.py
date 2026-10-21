"""Plan de Pruebas Unitarias: actividades (CP-ACT), evidencias (CP-EVI), validación (CP-VAL),
compromisos del Tubo de Trabajo (CP-COM) y seguridad y permisos (CP-SEG, CP-PER)."""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import Actividad, Evidencia, Validacion
from ActividadesApp.tests import foto, PNG
from ActividadesApp.views import puede_ver_actividad, validar_imagen
from AuditoriaApp.models import Auditoria
from IndicadoresApp.calculos import indicadores_usuario
from IndicadoresApp.models import Periodo
from UsuarioApp.models import Delegacion
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE


class BasePlan(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()
        compania = self.datos['delegacion']
        self.rural = Delegacion.objects.get(nombre='RURAL')
        self.func = crear_usuario('55555555-5', 'Funcionario', compania, self.datos['cargo'])
        self.companero = crear_usuario('77777777-7', 'Funcionario', compania, self.datos['cargo'])
        self.otro = crear_usuario('88888888-8', 'Funcionario', self.rural, self.datos['cargo'])
        self.delegado = crear_usuario('33333333-3', 'Delegado', compania)
        self.delegado_rural = crear_usuario('44444444-4', 'Delegado', self.rural)
        self.coordinador = crear_usuario('22222222-2', 'Coordinador')
        self.hoy = timezone.localdate()

    def entrar(self, rut):
        self.client.login(username=rut, password=CLAVE)

    def registrar(self, **extra):
        datos = {'solicitud_problema': 'Vecinos piden poda de árboles', 'accion': 'Inspección en terreno',
                 'item_comision': '1', 'contacto': 'Juan Pérez', 'telefono': '912345678', 'territorio': 'Sector Alto'}
        datos.update(extra)
        return self.client.post(reverse('actividades:actividad_crear'), datos)

    def mensajes(self, respuesta):
        return [str(m) for m in respuesta.context['messages']] if respuesta.context else []

    def compromiso(self, usuario=None, dias=5, territorio='Sector Alto'):
        return Actividad.objects.create(
            solicitud_problema='Reparar luminaria', accion='Gestión con alumbrado', item=self.datos['item'],
            periodo=self.datos['periodo'], usuario=usuario or self.func, estado='EN_TUBO',
            ingreso_agenda_colectiva=True, fecha_comprometida=self.hoy + timedelta(days=dias), territorio=territorio)

    def con_evidencia(self, usuario=None):
        actividad = Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'],
                                             periodo=self.datos['periodo'], usuario=usuario or self.func)
        evidencia = Evidencia.objects.create(actividad=actividad, imagen=foto(), version=1)
        actividad.sincronizar_estado()
        return actividad, evidencia


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PlanActividadesTest(BasePlan):
    def test_cp_act_001_registro_exitoso(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(evidencia_imagen=foto())
        self.assertRedirects(respuesta, reverse('actividades:mi_gestion'))
        actividad = Actividad.objects.get()
        self.assertEqual(actividad.folio(), f"ACT{actividad.pk}")
        self.assertEqual((actividad.usuario, actividad.periodo, actividad.item),
                         (self.func, self.datos['periodo'], self.datos['item']))
        self.assertEqual(actividad.estado, 'REGISTRADA')

    def test_cp_act_002_descripcion_vacia(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(solicitud_problema='', evidencia_imagen=foto())
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Debe describir la actividad.", self.mensajes(respuesta))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_003_accion_vacia(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(accion='', evidencia_imagen=foto())
        self.assertIn("La acción es obligatoria y no puede superar 255 caracteres.", self.mensajes(respuesta))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_004_item_inexistente(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(item_comision='999', evidencia_imagen=foto())
        self.assertTrue(any('ítem seleccionado no existe' in m for m in self.mensajes(respuesta)))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_005_periodo_inexistente(self):
        Periodo.objects.update(fecha_inicio=self.hoy + timedelta(days=30), fecha_termino=self.hoy + timedelta(days=60))
        self.entrar('55555555-5')
        respuesta = self.registrar(evidencia_imagen=foto())
        self.assertIn("No hay un periodo vigente para la fecha de hoy.", self.mensajes(respuesta))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_006_periodo_cerrado(self):
        self.datos['periodo'].cerrar()
        self.entrar('55555555-5')
        respuesta = self.registrar(evidencia_imagen=foto())
        self.assertIn("El periodo vigente está cerrado; no se pueden registrar actividades.", self.mensajes(respuesta))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_007_actividad_al_tubo(self):
        self.entrar('55555555-5')
        limite = self.hoy + timedelta(days=7)
        respuesta = self.registrar(ingreso_agenda_colectiva='on', fecha_comprometida=limite.isoformat())
        self.assertRedirects(respuesta, reverse('actividades:tubo_trabajo'))
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.estado, actividad.ingreso_agenda_colectiva, actividad.fecha_comprometida),
                         ('EN_TUBO', True, limite))

    def test_cp_act_008_actividad_con_evidencia_valida(self):
        self.entrar('55555555-5')
        self.registrar(evidencia_imagen=foto())
        actividad = Actividad.objects.get()
        evidencia = actividad.evidencias.get()
        self.assertEqual((evidencia.version, evidencia.estado_revision), (1, 'PENDIENTE'))
        self.assertTrue(evidencia.codigo().startswith('ORC'))

    def test_cp_act_009_fecha_comprometida_anterior_a_hoy(self):
        self.entrar('55555555-5')
        ayer = self.hoy - timedelta(days=1)
        respuesta = self.registrar(ingreso_agenda_colectiva='on', fecha_comprometida=ayer.isoformat())
        self.assertIn("La fecha límite no puede ser anterior a hoy.", self.mensajes(respuesta))
        self.assertEqual(Actividad.objects.count(), 0)

    def test_cp_act_010_tubo_sin_fecha_comprometida(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(ingreso_agenda_colectiva='on')
        self.assertIn("Indique la fecha límite comprometida para cumplir la actividad.", self.mensajes(respuesta))
        self.assertEqual(Actividad.objects.count(), 0)


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PlanEvidenciasTest(BasePlan):
    def subir(self, actividad, archivo):
        datos = {'comentario': 'Trabajo realizado'}
        if archivo is not None:
            datos['evidencia_imagen'] = archivo
        return self.client.post(reverse('actividades:subir_evidencia', args=[actividad.pk]), datos, follow=True)

    def test_cp_evi_001_carga_valida(self):
        actividad = self.compromiso()
        self.entrar('55555555-5')
        self.subir(actividad, SimpleUploadedFile('evidencia.jpg', PNG, content_type='image/jpeg'))
        actividad.refresh_from_db()
        self.assertEqual(actividad.evidencias.count(), 1)
        self.assertEqual(actividad.estado, 'REGISTRADA')
        detalle = self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]))
        self.assertEqual(len(detalle.context['evidencias']), 1)

    def test_cp_evi_002_formato_pdf(self):
        self.assertEqual(validar_imagen(SimpleUploadedFile('evidencia.pdf', b'%PDF-1.4', content_type='application/pdf')),
                         ["La fotografía debe ser JPG o PNG."])
        actividad = self.compromiso()
        self.entrar('55555555-5')
        respuesta = self.subir(actividad, SimpleUploadedFile('evidencia.pdf', b'%PDF-1.4', content_type='application/pdf'))
        self.assertIn("La fotografía debe ser JPG o PNG.", self.mensajes(respuesta))
        self.assertEqual(actividad.evidencias.count(), 0)

    def test_cp_evi_003_formato_no_permitido(self):
        for nombre in ['evidencia.gif', 'evidencia.exe', 'evidencia.docx']:
            self.assertEqual(validar_imagen(SimpleUploadedFile(nombre, b'contenido')), ["La fotografía debe ser JPG o PNG."])

    def test_cp_evi_004_imagen_superior_a_5mb(self):
        grande = SimpleUploadedFile('grande.png', b'0' * (5 * 1024 * 1024 + 1), content_type='image/png')
        self.assertEqual(validar_imagen(grande), ["La fotografía no puede superar 5 MB."])

    def test_cp_evi_005_evidencia_vacia(self):
        actividad = self.compromiso()
        self.entrar('55555555-5')
        respuesta = self.subir(actividad, None)
        self.assertIn("Adjunte la fotografía de evidencia.", self.mensajes(respuesta))
        self.assertEqual(actividad.evidencias.count(), 0)

    def test_cp_evi_006_nueva_version_de_evidencia(self):
        actividad, evidencia = self.con_evidencia()
        evidencia.estado_revision = 'RECHAZADA'
        evidencia.save()
        actividad.sincronizar_estado()
        self.entrar('55555555-5')
        self.subir(actividad, foto())
        nueva = actividad.evidencia_vigente()
        self.assertEqual((nueva.version, nueva.reemplaza_a), (2, evidencia))
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'REGISTRADA')


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PlanValidacionTest(BasePlan):
    def decidir(self, evidencia, **datos):
        return self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]), datos, follow=True)

    def test_cp_val_001_aprobacion(self):
        actividad, evidencia = self.con_evidencia()
        self.entrar('33333333-3')
        self.decidir(evidencia, decision='APROBAR', observacion='Evidencia clara')
        evidencia.refresh_from_db()
        actividad.refresh_from_db()
        self.assertEqual((evidencia.estado_revision, actividad.estado), ('APROBADA', 'VALIDADA'))
        indicador = indicadores_usuario(self.func, self.datos['periodo'], self.hoy)[0]
        self.assertEqual(indicador.avance_actual, 1)  # aporta al avance del indicador

    def test_cp_val_002_rechazo(self):
        actividad, evidencia = self.con_evidencia()
        self.entrar('33333333-3')
        self.decidir(evidencia, decision='RECHAZAR', observacion='Evidencia borrosa')
        evidencia.refresh_from_db()
        actividad.refresh_from_db()
        self.assertEqual((evidencia.estado_revision, actividad.estado), ('RECHAZADA', 'RECHAZADA'))
        self.assertEqual(evidencia.validacion.observacion, 'Evidencia borrosa')
        indicador = indicadores_usuario(self.func, self.datos['periodo'], self.hoy)[0]
        self.assertEqual(indicador.avance_actual, 0)  # no aporta al avance

    def test_cp_val_003_rechazo_sin_observacion(self):
        actividad, evidencia = self.con_evidencia()
        self.entrar('33333333-3')
        respuesta = self.decidir(evidencia, decision='RECHAZAR', observacion='')
        self.assertTrue(any('debe escribir una observación' in m for m in self.mensajes(respuesta)))
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.estado_revision, 'PENDIENTE')

    def test_cp_val_004_evidencia_ya_validada(self):
        actividad, evidencia = self.con_evidencia()
        self.entrar('33333333-3')
        self.decidir(evidencia, decision='APROBAR')
        respuesta = self.decidir(evidencia, decision='RECHAZAR', observacion='Cambio de opinión')
        self.assertIn("Esta evidencia ya fue revisada.", self.mensajes(respuesta))
        self.assertEqual(Validacion.objects.count(), 1)
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.estado_revision, 'APROBADA')

    def test_cp_val_005_decision_invalida(self):
        actividad, evidencia = self.con_evidencia()
        self.entrar('33333333-3')
        respuesta = self.decidir(evidencia, decision='BORRAR')
        self.assertIn("Decisión no válida.", self.mensajes(respuesta))
        self.assertEqual(Validacion.objects.count(), 0)

    def test_cp_val_006_verificacion_de_evidencia_propia(self):
        actividad, evidencia = self.con_evidencia(usuario=self.coordinador)
        self.entrar('22222222-2')
        respuesta = self.decidir(evidencia, decision='APROBAR')
        self.assertIn("No puede verificar una evidencia registrada por usted mismo.", self.mensajes(respuesta))
        self.assertEqual(Validacion.objects.count(), 0)

    def test_cp_val_007_verificacion_fuera_de_delegacion(self):
        actividad, evidencia = self.con_evidencia()  # funcionario de Las Compañías
        self.entrar('44444444-4')  # Delegado Rural
        respuesta = self.decidir(evidencia, decision='APROBAR')
        self.assertIn("Solo puede verificar evidencias de funcionarios de su delegación.", self.mensajes(respuesta))
        self.assertEqual(Validacion.objects.count(), 0)


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PlanCompromisosTest(BasePlan):
    def folios(self, **filtros):
        return [c['folio'] for c in self.client.get(reverse('actividades:tubo_trabajo'), filtros).context['compromisos']]

    def test_cp_com_001_registro_de_compromiso(self):
        self.entrar('55555555-5')
        limite = self.hoy + timedelta(days=10)
        self.registrar(ingreso_agenda_colectiva='on', fecha_comprometida=limite.isoformat())
        compromiso = Actividad.objects.get()
        self.assertTrue(compromiso.es_compromiso())
        self.assertEqual((compromiso.usuario, compromiso.fecha_comprometida), (self.func, limite))

    def test_cp_com_002_cambio_de_estado(self):
        compromiso = self.compromiso()
        self.entrar('55555555-5')
        self.client.post(reverse('actividades:subir_evidencia', args=[compromiso.pk]), {'evidencia_imagen': foto()})
        compromiso.refresh_from_db()
        self.assertEqual(compromiso.estado, 'REGISTRADA')
        cambio = Auditoria.objects.get(evento='MODIFICACION', entidad='Actividad', id_entidad=str(compromiso.pk))
        self.assertEqual((cambio.valor_anterior, cambio.valor_nuevo, cambio.usuario), ('EN_TUBO', 'REGISTRADA', self.func))
        self.assertIsNotNone(cambio.fecha)

    def test_cp_com_003_compromiso_vencido(self):
        vencido = self.compromiso(dias=-2)
        self.assertTrue(vencido.vencido())
        self.entrar('55555555-5')
        self.assertEqual(self.folios(estado='VENCIDOS'), [vencido.folio()])

    def test_cp_com_004_compromiso_proximo_a_vencer(self):
        proximo = self.compromiso(dias=2)
        lejano = self.compromiso(dias=20)
        self.assertTrue(proximo.proximo_a_vencer())
        self.assertFalse(lejano.proximo_a_vencer())
        self.entrar('55555555-5')
        self.assertEqual(self.folios(estado='POR_VENCER'), [proximo.folio()])

    def test_cp_com_005_filtro_por_responsable(self):
        propio = self.compromiso()
        ajeno = self.compromiso(usuario=self.companero)
        self.entrar('55555555-5')
        self.assertEqual(self.folios(responsable=str(self.companero.pk)), [ajeno.folio()])
        self.assertEqual(self.folios(mios='1'), [propio.folio()])

    def test_cp_com_006_filtro_por_estado(self):
        pendiente = self.compromiso()
        ejecutado = self.compromiso(dias=8)
        Evidencia.objects.create(actividad=ejecutado, imagen=foto(), version=1)
        ejecutado.sincronizar_estado()
        self.entrar('55555555-5')
        self.assertEqual(self.folios(), [pendiente.folio()])
        self.assertEqual(self.folios(estado='EN_REVISION'), [ejecutado.folio()])

    def test_cp_com_007_filtro_por_territorio(self):
        alto = self.compromiso(territorio='Sector Alto')
        self.compromiso(territorio='Villa El Indio')
        self.entrar('55555555-5')
        self.assertEqual(self.folios(territorio='alto'), [alto.folio()])

    def test_cp_com_008_filtro_por_rango_de_fechas(self):
        cercano = self.compromiso(dias=3)
        self.compromiso(dias=30)
        self.entrar('55555555-5')
        desde, hasta = self.hoy.isoformat(), (self.hoy + timedelta(days=5)).isoformat()
        self.assertEqual(self.folios(desde=desde, hasta=hasta), [cercano.folio()])


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PlanSeguridadTest(BasePlan):
    def test_cp_seg_001_acceso_fuera_del_ambito(self):
        actividad = self.compromiso(usuario=self.otro)  # actividad de la delegación Rural
        self.entrar('55555555-5')  # funcionario de Las Compañías
        respuesta = self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]))
        self.assertRedirects(respuesta, reverse('actividades:mi_gestion'))
        self.assertTrue(Auditoria.objects.filter(evento='ACCESO_DENEGADO', usuario=self.func).exists())

    def test_cp_seg_002_restriccion_por_permisos(self):
        self.entrar('55555555-5')
        for nombre in ['users:administracion', 'auditoria:logs', 'actividades:verificacion']:
            self.assertRedirects(self.client.get(reverse(nombre)), reverse('actividades:mi_gestion'), msg_prefix=nombre)
        self.assertEqual(Auditoria.objects.filter(evento='ACCESO_DENEGADO').count(), 3)

    def test_cp_seg_004_actividad_de_otra_delegacion(self):
        actividad = self.compromiso(usuario=self.otro)
        self.assertFalse(puede_ver_actividad(self.func, actividad))
        self.assertFalse(puede_ver_actividad(self.delegado, actividad))

    def test_cp_seg_005_acceso_dentro_de_la_delegacion(self):
        actividad = self.compromiso(usuario=self.func)
        self.assertTrue(puede_ver_actividad(self.companero, actividad))
        self.assertTrue(puede_ver_actividad(self.delegado, actividad))
        self.entrar('77777777-7')
        self.assertEqual(self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk])).status_code, 200)

    def test_cp_per_001_restriccion_por_permisos_actividad(self):
        actividad = self.compromiso(usuario=self.otro)
        self.assertFalse(puede_ver_actividad(self.func, actividad))
        self.entrar('55555555-5')
        self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]))
        intento = Auditoria.objects.get(evento='ACCESO_DENEGADO')
        self.assertIn(actividad.folio(), intento.valor_nuevo)

    def test_cp_per_002_filtrado_por_ambito(self):
        propio = self.compromiso(usuario=self.func)
        self.compromiso(usuario=self.otro)  # Rural
        self.entrar('33333333-3')  # Delegado de Las Compañías
        compromisos = self.client.get(reverse('actividades:tubo_trabajo'), {'estado': 'TODOS'}).context['compromisos']
        self.assertEqual([c['folio'] for c in compromisos], [propio.folio()])
        # Aunque pida otra delegación por la URL, el Delegado sigue viendo solo la suya
        compromisos = self.client.get(reverse('actividades:tubo_trabajo'), {'estado': 'TODOS', 'delegacion': 'RURAL'}).context['compromisos']
        self.assertEqual([c['folio'] for c in compromisos], [propio.folio()])
