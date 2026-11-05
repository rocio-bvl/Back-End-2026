"""Pruebas de los requerimientos de la municipalidad (noviembre 2026): persona atendida obligatoria, máximo diario,
cierre de semana, puntaje decidido por el Delegado, gestiones del Delegado, felicitaciones, tope de 120%, ausencias,
alertas de validación y reporte de atrasos."""
from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.choices import ITEM_FELICITACIONES, MAX_ACTIVIDADES_DIA
from ActividadesApp.forms import inicio_semana_abierta
from ActividadesApp.models import Actividad, AtencionSocial, Evidencia, Validacion
from ActividadesApp.tests import BaseActividades
from AuditoriaApp.models import Auditoria
from IndicadoresApp.calculos import indicadores_usuario
from IndicadoresApp.forms import AusenciaForm
from IndicadoresApp.models import Ausencia, MetaDesempeno
from UsuarioApp.models import Catalogo


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PersonaAtendidaTest(BaseActividades):
    def test_nombre_y_telefono_son_obligatorios(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(nombre_usuario='', telefono_usuario='')
        self.assertIn('nombre_usuario', respuesta.context['form'].errors)
        self.assertIn('telefono_usuario', respuesta.context['form'].errors)
        self.assertEqual(Actividad.objects.count(), 0)

    def test_se_vincula_sola_a_la_solicitud_con_el_mismo_telefono(self):
        solicitud = AtencionSocial.objects.create(usuario=self.func, nombre_solicitante='Juan Pérez', rut_solicitante='11222333-9',
                                                  telefono_solicitante='+56 9 1234 5678', tipo_atencion=self.tipo_atencion())
        self.entrar('55555555-5')
        self.registrar(nombre_usuario='', telefono_usuario='912345678')
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.solicitud, actividad.nombre_usuario), (solicitud, 'Juan Pérez'))

    def test_solicitud_social_exige_telefono(self):
        self.entrar('55555555-5')
        self.client.post(reverse('actividades:atencion_crear'), {
            'nombre_solicitante': 'Ana', 'rut_solicitante': '11.222.333-9', 'telefono_solicitante': '',
            'tipo_atencion': self.tipo_atencion().pk})
        self.assertFalse(AtencionSocial.objects.exists())

    def tipo_atencion(self):
        return Catalogo.objects.get_or_create(tipo='TIPO_ATENCION', nombre='Ayuda social')[0]


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class ReglasDeIngresoTest(BaseActividades):
    def test_maximo_diario_para_el_funcionario_y_admin_exento(self):
        self.entrar('55555555-5')
        for _ in range(MAX_ACTIVIDADES_DIA):
            self.registrar()
        respuesta = self.registrar()
        self.assertIn(f"Ya ingresó {MAX_ACTIVIDADES_DIA} actividades hoy", str(respuesta.context['form'].non_field_errors()))
        self.assertEqual(Actividad.objects.filter(usuario=self.func).count(), MAX_ACTIVIDADES_DIA)
        self.entrar('11111111-1')
        for _ in range(MAX_ACTIVIDADES_DIA + 1):
            self.registrar(fecha_realizacion=(self.hoy + timedelta(days=3)).isoformat())
        self.assertEqual(Actividad.objects.filter(usuario=self.admin).count(), MAX_ACTIVIDADES_DIA + 1)

    def test_semana_cerrada_no_recibe_actividades_ni_del_admin(self):
        cerrada = inicio_semana_abierta(self.hoy) - timedelta(days=1)
        for rut in ['55555555-5', '11111111-1']:
            self.entrar(rut)
            respuesta = self.registrar(fecha_realizacion=cerrada.isoformat())
            self.assertIn('fecha_realizacion', respuesta.context['form'].errors)
        self.assertEqual(Actividad.objects.count(), 0)
        self.entrar('55555555-5')
        self.registrar(fecha_realizacion=inicio_semana_abierta(self.hoy).isoformat())
        self.assertEqual(Actividad.objects.count(), 1)

    def test_la_semana_se_cierra_el_lunes_siguiente(self):
        lunes = self.hoy - timedelta(days=self.hoy.weekday())
        self.assertEqual(inicio_semana_abierta(lunes), lunes - timedelta(days=7))      # el lunes aún entra la semana pasada
        self.assertEqual(inicio_semana_abierta(lunes + timedelta(days=1)), lunes)      # desde el martes, ya no


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PuntajeTest(BaseActividades):
    def avance(self, usuario):
        return indicadores_usuario(usuario, self.datos['periodo'], self.hoy)[0].avance_actual

    def test_el_delegado_decide_si_suma_y_puede_cambiarlo(self):
        actividad, evidencia = self.con_evidencia()
        self.entrar('33333333-3')
        url = reverse('actividades:validar_evidencia', args=[evidencia.pk])
        self.client.post(url, {'decision': 'APROBAR'})  # sin decidir el puntaje no se valida
        self.assertFalse(Validacion.objects.exists())
        self.client.post(url, {'decision': 'APROBAR', 'otorga_puntaje': 'NO'})
        actividad.refresh_from_db()
        self.assertEqual((actividad.estado, actividad.otorga_puntaje(), self.avance(self.func)), ('VALIDADA', False, 0))
        self.client.post(reverse('actividades:cambiar_puntaje', args=[actividad.pk]), {'otorga_puntaje': 'SI'})
        self.assertEqual(self.avance(self.func), 1)
        cambio = Auditoria.objects.get(entidad='Validacion')
        self.assertEqual((cambio.valor_anterior, cambio.valor_nuevo), ('Suma puntaje: No', 'Suma puntaje: Sí'))

    def test_funcionario_y_coordinador_no_cambian_el_puntaje(self):
        actividad, evidencia = self.con_evidencia()
        Validacion.objects.create(evidencia=evidencia, decision='APROBAR', verificador=self.delegado, otorga_puntaje=False)
        evidencia.estado_revision = 'APROBADA'
        evidencia.save()
        actividad.sincronizar_estado()
        for rut in ['55555555-5', '22222222-2']:
            self.entrar(rut)
            self.client.post(reverse('actividades:cambiar_puntaje', args=[actividad.pk]), {'otorga_puntaje': 'SI'})
        self.assertFalse(actividad.validacion_vigente().otorga_puntaje)

    def test_gestion_del_delegado_no_se_verifica_ni_suma(self):
        self.entrar('33333333-3')
        self.registrar()
        gestion = Actividad.objects.get()
        self.assertTrue(gestion.es_gestion)
        self.assertEqual(self.client.get(reverse('actividades:verificacion')).context['evidencias_pendientes'], [])

    def test_tope_de_120_por_item(self):
        meta = self.datos['periodo'].metas.get()  # 10 actividades del ítem 1
        for _ in range(15):
            self.crear(estado='VALIDADA')
        indicador = indicadores_usuario(self.func, self.datos['periodo'], self.hoy)[0]
        self.assertEqual((indicador.cumplimiento, indicador.en_tope()), (120, True))
        self.entrar('55555555-5')
        html = self.client.get(reverse('actividades:mi_gestion')).content.decode()
        self.assertIn('TOPE ALCANZADO', html)
        self.assertEqual(meta.periodo.tope_cumplimiento, 120)


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class FelicitacionesTest(BaseActividades):
    def setUp(self):
        super().setUp()
        self.item = Catalogo.objects.get(tipo='ITEM_GESTION', nombre=ITEM_FELICITACIONES)

    def test_el_funcionario_no_puede_elegir_felicitaciones(self):
        self.entrar('55555555-5')
        items = self.client.get(reverse('actividades:actividad_crear')).context['form'].fields['item'].queryset
        self.assertNotIn(self.item, items)

    def test_el_delegado_informa_la_felicitacion_y_suma_al_funcionario(self):
        MetaDesempeno.objects.create(valor_objetivo=2, ponderador=0, cargo=self.datos['cargo'], item=self.item,
                                     periodo=self.datos['periodo'])
        self.entrar('33333333-3')
        self.registrar(item=self.item.pk)  # sin funcionario felicitado no se guarda
        self.assertFalse(Actividad.objects.exists())
        self.registrar(item=self.item.pk, encargado=self.func.pk)
        felicitacion = Actividad.objects.get()
        self.assertEqual((felicitacion.estado, felicitacion.es_gestion, felicitacion.otorga_puntaje()), ('VALIDADA', False, True))
        avance = {ind.meta.item_id: ind.avance_actual for ind in indicadores_usuario(self.func, self.datos['periodo'], self.hoy)}
        self.assertEqual(avance[self.item.pk], 1)


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class AusenciasTest(BaseActividades):
    def test_la_ausencia_ajusta_la_meta(self):
        periodo = self.datos['periodo']  # 20 días computables; meta de 10 actividades
        Ausencia.objects.create(usuario=self.func, tipo='VACACIONES', desde=periodo.fecha_inicio,
                                hasta=periodo.fecha_inicio + timedelta(days=4), registrado_por=self.delegado)
        indicador = indicadores_usuario(self.func, periodo, self.hoy)[0]
        self.assertEqual((indicador.dias_ausencia(), indicador.objetivo_ajustado()), (5, 7.5))

    def test_delegado_registra_solo_a_su_equipo(self):
        periodo = self.datos['periodo']
        datos = {'tipo': 'LICENCIA', 'desde': self.hoy.isoformat(), 'hasta': self.hoy.isoformat()}
        self.entrar('33333333-3')
        self.client.post(reverse('indicadores:ausencia_crear'), dict(datos, persona=self.otro.username))  # otra delegación
        self.assertFalse(Ausencia.objects.exists())
        self.client.post(reverse('indicadores:ausencia_crear'), dict(datos, persona=self.func.username))
        self.assertEqual(Ausencia.objects.get().usuario, self.func)
        self.assertTrue(Auditoria.objects.filter(entidad='Ausencia', evento='CREACION').exists())
        self.assertIn('Ausencias del periodo', self.client.get(reverse('indicadores:semaforo')).content.decode())
        self.assertEqual(periodo, self.datos['periodo'])

    def test_coordinador_registra_ausencia_de_un_delegado(self):
        self.entrar('22222222-2')
        form = self.client.get(reverse('indicadores:semaforo')).context['form_ausencia']
        self.assertIn(self.delegado, form.personas)
        # El buscador encuentra por RUT (la sugerencia elegida lo trae) o por el nombre completo
        datos = {'tipo': 'VACACIONES', 'desde': self.hoy.isoformat(), 'hasta': self.hoy.isoformat()}
        self.client.post(reverse('indicadores:ausencia_crear'), dict(datos, persona=AusenciaForm.texto_persona(self.delegado)))
        # Un nombre que comparten dos personas no basta: hay que elegir de la lista (trae el RUT)
        self.client.post(reverse('indicadores:ausencia_crear'), dict(datos, persona=self.func.get_full_name()))
        self.assertFalse(Ausencia.objects.filter(usuario=self.func).exists())
        self.func.first_name, self.func.last_name = 'Camila', 'Rojas'
        self.func.save()
        self.client.post(reverse('indicadores:ausencia_crear'), dict(datos, persona='camila rojas'))
        self.assertEqual(set(Ausencia.objects.values_list('usuario', flat=True)), {self.delegado.pk, self.func.pk})


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class AlertasYAtrasosTest(BaseActividades):
    def atrasada(self, dias):
        actividad, evidencia = self.con_evidencia()
        Evidencia.objects.filter(pk=evidencia.pk).update(fecha=timezone.now() - timedelta(days=dias))
        return actividad

    def test_alerta_al_delegado_con_evidencias_atrasadas(self):
        self.atrasada(3)
        self.entrar('33333333-3')
        alerta = self.client.get(reverse('actividades:mi_gestion')).context['alerta_validacion']
        self.assertEqual((alerta['cantidad'], alerta['mas_antigua'], alerta['nivel']), (1, 3, 'danger'))
        self.entrar('55555555-5')
        self.assertNotIn('alerta_validacion', self.client.get(reverse('actividades:mi_gestion')).context)

    def test_reporte_de_atrasos_para_admin_y_coordinador(self):
        self.atrasada(4)
        for rut in ['11111111-1', '22222222-2']:
            self.entrar(rut)
            filas = self.client.get(reverse('indicadores:atrasos_validacion')).context['filas']
            compania = [fila for fila in filas if fila['delegacion'] == self.datos['delegacion']][0]
            self.assertEqual((compania['pendientes'], compania['atrasadas'], compania['mas_antigua']), (1, 1, 4))
        self.entrar('33333333-3')
        self.assertRedirects(self.client.get(reverse('indicadores:atrasos_validacion')), reverse('actividades:mi_gestion'))

    def test_buscador_de_verificacion_por_funcionario(self):
        self.con_evidencia()
        self.con_evidencia(usuario=self.companero)
        self.entrar('33333333-3')
        url = reverse('actividades:verificacion')
        self.assertEqual(len(self.client.get(url).context['evidencias_pendientes']), 2)
        filas = self.client.get(url, {'q': '77777777'}).context['evidencias_pendientes']
        self.assertEqual([fila['funcionario'] for fila in filas], [self.companero])


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class DetalleAtencionTest(BaseActividades):
    def setUp(self):
        super().setUp()
        tipo = Catalogo.objects.create(tipo='TIPO_ATENCION', nombre='Ayuda social', estado='ACTIVO')
        self.atencion = AtencionSocial.objects.create(usuario=self.func, nombre_solicitante='Rosa Prueba',
                                                      rut_solicitante='9876543-3', tipo_atencion=tipo)
        self.url = reverse('actividades:atencion_detalle', args=[self.atencion.pk])

    def test_ven_el_detalle_admin_coordinador_delegado_y_quien_la_registro(self):
        for rut in ['11111111-1', '22222222-2', '33333333-3', '55555555-5']:
            self.entrar(rut)
            self.assertContains(self.client.get(self.url), 'Rosa Prueba', msg_prefix=rut)
            self.assertIn(self.url, self.client.get(reverse('actividades:gestion_social')).content.decode(), rut)

    def test_coordinador_y_delegado_vinculan_una_actividad(self):
        url = reverse('actividades:atencion_vincular', args=[self.atencion.pk])
        for rut in ['22222222-2', '33333333-3']:
            actividad = self.crear()
            self.entrar(rut)
            buscada = self.client.get(self.url, {'q': actividad.folio()}).context['candidatas']
            self.assertEqual(list(buscada), [actividad], rut)
            self.client.post(url, {'actividad': actividad.pk})
            actividad.refresh_from_db()
            self.assertEqual(actividad.solicitud, self.atencion, rut)
        self.assertEqual(Auditoria.objects.filter(entidad='Actividad', valor_nuevo='Vinculada a ' + self.atencion.codigo()).count(), 2)

    def test_no_se_vincula_otra_delegacion_ni_lo_hace_el_funcionario(self):
        url = reverse('actividades:atencion_vincular', args=[self.atencion.pk])
        ajena = self.crear(usuario=self.otro, territorio=self.territorio_rural)  # Rural
        self.entrar('22222222-2')
        self.client.post(url, {'actividad': ajena.pk})
        propia = self.crear()
        self.entrar('55555555-5')
        self.client.post(url, {'actividad': propia.pk})
        self.assertFalse(Actividad.objects.filter(solicitud=self.atencion).exists())

    def test_no_la_ven_otro_funcionario_ni_otra_delegacion(self):
        for rut in ['77777777-7', '44444444-4']:
            self.entrar(rut)
            self.assertRedirects(self.client.get(self.url), reverse('actividades:mi_gestion'), msg_prefix=rut)


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class MiGestionUnificadaTest(BaseActividades):
    def pagina(self, rut, **parametros):
        self.entrar(rut)
        return self.client.get(reverse('actividades:mi_gestion'), parametros)

    def test_titulo_segun_perfil(self):
        for rut, titulo in [('11111111-1', 'Gestión Admin'), ('22222222-2', 'Gestión Coordinador'),
                            ('33333333-3', 'Gestión Delegado'), ('55555555-5', 'Gestión Funcionario')]:
            self.assertContains(self.pagina(rut), titulo, msg_prefix=rut)

    def test_accesos_de_gestion_sobre_las_pestanas_y_sin_titulo(self):
        url_funcionarios = reverse('users:administracion') + '?pestana=usuarios'
        html = self.pagina('33333333-3').content.decode()
        self.assertLess(html.index(url_funcionarios), html.index('id="pestanasGestion"'))
        self.assertNotIn('>Mantenedores<', html)
        self.assertNotIn(url_funcionarios, self.pagina('55555555-5').content.decode())

    def test_pestana_pedida_o_resumen(self):
        self.assertEqual(self.pagina('33333333-3', pestana='delegacion').context['pestana'], 'delegacion')
        # El Funcionario no tiene la pestaña de su delegación: se abre Resumen
        self.assertEqual(self.pagina('55555555-5', pestana='delegacion').context['pestana'], 'resumen')
        self.assertNotContains(self.pagina('55555555-5'), '>Indicadores<')
