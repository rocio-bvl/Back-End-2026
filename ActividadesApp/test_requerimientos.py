"""Pruebas de los requerimientos de la municipalidad (noviembre 2026): persona atendida obligatoria, máximo diario,
cierre de semana, puntaje decidido por el Delegado, gestiones del Delegado, tope de 120%, ausencias,
alertas de validación y reporte de atrasos."""
from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.choices import MAX_ACTIVIDADES_DIA
from ActividadesApp.forms import inicio_semana_abierta
from ActividadesApp.models import Actividad, AtencionSocial, Evidencia, Validacion, Organizacion, Solicitante, Representante
from ActividadesApp.tests import BaseActividades
from AuditoriaApp.models import Auditoria
from IndicadoresApp.calculos import indicadores_usuario
from IndicadoresApp.forms import AusenciaForm
from IndicadoresApp.models import Ausencia, MetaDesempeno, AjusteDesempeno, Felicitacion, Reclamo
from UsuarioApp.models import Catalogo


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PersonaAtendidaTest(BaseActividades):
    def test_rut_de_la_persona_atendida_es_obligatorio(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(rut_solicitante='', nombre_solicitante='', telefono_solicitante='')
        self.assertIn('rut_solicitante', respuesta.context['form'].errors)
        self.assertEqual(Actividad.objects.count(), 0)

    def test_se_vincula_sola_a_la_solicitud_de_esa_persona(self):
        juan = Solicitante.objects.create(rut='11222333-9', nombre='Juan Pérez', telefono='+56 9 1234 5678')
        solicitud = AtencionSocial.objects.create(usuario=self.func, solicitante=juan, tipo_atencion=self.tipo_atencion())
        self.entrar('55555555-5')
        self.registrar(rut_solicitante='11.222.333-9', nombre_solicitante='', telefono_solicitante='')
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.solicitud, actividad.solicitante), (solicitud, juan))

    def test_la_solicitud_elegida_debe_ser_de_la_persona_atendida(self):
        juan = Solicitante.objects.create(rut='11222333-9', nombre='Juan Pérez', telefono='912345678')
        solicitud = AtencionSocial.objects.create(usuario=self.func, solicitante=juan, tipo_atencion=self.tipo_atencion())
        self.entrar('55555555-5')
        respuesta = self.registrar(solicitud=solicitud.pk)  # persona atendida: Juan Pérez de setUp, otro RUT
        self.assertIn('solicitud', respuesta.context['form'].errors)

    def test_solicitud_social_exige_telefono(self):
        self.entrar('55555555-5')
        self.client.post(reverse('actividades:atencion_crear'), {
            'nombre_solicitante': 'Ana', 'rut_solicitante': '11.222.333-9', 'telefono_solicitante': '',
            'agregar_solicitante': 'True', 'tipo_atencion': self.tipo_atencion().pk})
        self.assertFalse(AtencionSocial.objects.exists())
        self.assertFalse(Solicitante.objects.filter(rut='11222333-9').exists())

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
        rosa = Solicitante.objects.create(rut='9876543-3', nombre='Rosa Prueba', telefono='933334444')
        self.atencion = AtencionSocial.objects.create(usuario=self.func, solicitante=rosa, tipo_atencion=tipo)
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
        # El Funcionario no tiene la pestaña de su delegación ni Resumen: se abre Mis actividades
        self.assertEqual(self.pagina('55555555-5', pestana='delegacion').context['pestana'], 'mias')
        self.assertEqual(self.pagina('55555555-5', pestana='resumen').context['pestana'], 'mias')
        self.assertNotContains(self.pagina('55555555-5'), 'id="tab-resumen"')
        self.assertNotContains(self.pagina('55555555-5'), '>Indicadores<')

    def test_tabla_lateral_avance_del_mismo_cargo_de_mayor_a_menor(self):
        # Felicitación al Funcionario de Rural: queda primero aunque sea de otra delegación
        self.entrar('11111111-1')
        self.client.post(reverse('indicadores:felicitacion_crear'),
                         {'felicitacion-persona': self.otro.username, 'felicitacion-fecha': self.hoy.isoformat(),
                          'felicitacion-motivo': 'Gracias'})
        respuesta = self.pagina('55555555-5')
        ranking = respuesta.context['ranking_cargo']
        self.assertEqual({fila['id'] for fila in ranking}, {self.func.pk, self.companero.pk, self.otro.pk})
        self.assertEqual(ranking[0]['id'], self.otro.pk)
        self.assertEqual(ranking[0]['delegacion'], str(self.rural))
        avances = [fila['avance'] for fila in ranking]
        self.assertEqual(avances, sorted(avances, reverse=True))
        self.assertEqual([fila['lugar'] for fila in ranking], [1, 2, 2])  # empate: comparten el lugar
        self.assertEqual([fila['es_yo'] for fila in ranking if fila['id'] == self.func.pk], [True])
        self.assertContains(respuesta, 'Avance Actual')
        # Sin cargo (Delegado y Admin de los datos de prueba) no hay tabla lateral
        self.assertEqual(self.pagina('33333333-3').context['ranking_cargo'], [])


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class SolicitantesTest(BaseActividades):
    """Solicitantes registrados por RUT y representantes de organizaciones."""
    def setUp(self):
        super().setUp()
        self.tipo = Catalogo.objects.create(tipo='TIPO_ATENCION', nombre='Ayuda social', estado='ACTIVO')
        self.junta = Organizacion.objects.create(nombre='JJVV Villa Ejemplo', numero_registro_pj='100',
                                                 fecha_inscripcion=self.hoy, delegacion=self.datos['delegacion'])
        self.entrar('55555555-5')

    def atencion(self, **extra):
        datos = {'rut_solicitante': '11.222.333-9', 'nombre_solicitante': 'Juan Ficticio', 'telefono_solicitante': '987654321',
                 'tipo_atencion': self.tipo.pk, 'subtipo_atencion': '', 'detalle_solicitud': 'Consulta por beneficio'}
        datos.update(extra)
        return self.client.post(reverse('actividades:atencion_crear'), datos)

    def buscar(self, rut):
        return self.client.get(reverse('actividades:buscar_solicitante'), {'rut': rut}).json()

    def test_rut_no_registrado_pregunta_antes_de_agregar(self):
        respuesta = self.atencion()
        self.assertIn('no está registrado', str(respuesta.context['form'].errors['rut_solicitante']))
        self.assertFalse(AtencionSocial.objects.exists())
        self.assertFalse(self.buscar('11222333-9')['encontrado'])

    def test_agregar_solicitante_como_representante(self):
        self.atencion(agregar_solicitante='True', organizacion=self.junta.pk, cargo='PRESIDENTE')
        solicitante = Solicitante.objects.get(rut='11222333-9')
        self.assertEqual(AtencionSocial.objects.get().solicitante, solicitante)
        self.assertEqual(Representante.objects.get().cargo, 'PRESIDENTE')
        self.assertTrue(Auditoria.objects.filter(entidad='Solicitante', evento='CREACION').exists())
        datos = self.buscar('11.222.333-9')
        self.assertEqual((datos['encontrado'], datos['nombre']), (True, 'Juan Ficticio'))
        self.assertEqual(datos['cargos'], ['Presidente de JJVV Villa Ejemplo'])

    def test_registrado_se_reutiliza_sin_repetir_sus_datos(self):
        self.atencion(agregar_solicitante='True')
        self.atencion(nombre_solicitante='', telefono_solicitante='')  # solo el RUT
        self.assertEqual((Solicitante.objects.count(), AtencionSocial.objects.count()), (1, 2))
        self.assertEqual(set(AtencionSocial.objects.values_list('solicitante__nombre', flat=True)), {'Juan Ficticio'})

    def test_corregir_el_telefono_lo_actualiza_en_un_solo_lugar(self):
        self.atencion(agregar_solicitante='True')
        self.atencion(telefono_solicitante='955554444')
        self.assertEqual(Solicitante.objects.get().telefono, '+56 9 5555 4444')
        self.assertTrue(Auditoria.objects.filter(entidad='Solicitante', evento='MODIFICACION').exists())

    def test_telefono_del_solicitante_debe_ser_chileno(self):
        respuesta = self.atencion(agregar_solicitante='True', telefono_solicitante='1234')
        self.assertIn('telefono_solicitante', respuesta.context['form'].errors)
        self.atencion(agregar_solicitante='True', telefono_solicitante='+56 9 8765 4321')
        self.assertEqual(Solicitante.objects.get().telefono, '+56 9 8765 4321')

    def sugerir(self, texto):
        return self.client.get(reverse('actividades:sugerir_solicitantes'), {'q': texto}).json()['sugerencias']

    def test_sugiere_por_inicio_del_rut_o_del_nombre(self):
        Solicitante.objects.create(rut='12345678-5', nombre='María Ejemplo', telefono='+56 9 1111 2222')
        Solicitante.objects.create(rut='12349999-1', nombre='Mario Rojas', telefono='+56 9 3333 4444')
        self.assertEqual([s['nombre'] for s in self.sugerir('12.345')], ['María Ejemplo'])
        self.assertEqual([s['nombre'] for s in self.sugerir('123456785')], ['María Ejemplo'])  # sin guion
        self.assertEqual([s['rut'] for s in self.sugerir('1234')], ['12345678-5', '12349999-1'])
        self.assertEqual([s['nombre'] for s in self.sugerir('mari')], ['María Ejemplo', 'Mario Rojas'])

    def test_sugerencias_con_minimo_de_caracteres_y_maximo_de_personas(self):
        for numero in range(7):
            Solicitante.objects.create(rut=f'1500000{numero}-0', nombre=f'Persona {numero}')
        self.assertEqual(self.sugerir('150'), [])          # menos de 4 caracteres: nada
        self.assertEqual(len(self.sugerir('1500')), 5)     # a lo más 5
        self.client.logout()
        self.assertEqual(self.client.get(reverse('actividades:sugerir_solicitantes'), {'q': '1500'}).status_code, 302)

    def test_cargo_ocupado_no_se_repite(self):
        self.atencion(agregar_solicitante='True', organizacion=self.junta.pk, cargo='PRESIDENTE')
        respuesta = self.atencion(rut_solicitante='12345678-5', agregar_solicitante='True', organizacion=self.junta.pk,
                                  cargo='PRESIDENTE')
        self.assertIn('ya tiene presidente', str(respuesta.context['form'].errors['cargo']))

    def test_actividad_con_rut_registrado(self):
        Solicitante.objects.create(rut='11222333-9', nombre='Juan Ficticio', telefono='987654321')
        self.registrar(rut_solicitante='11222333-9', nombre_solicitante='', telefono_solicitante='',
                       agregar_solicitante='')
        self.assertEqual(Actividad.objects.get().solicitante.nombre, 'Juan Ficticio')

    def test_actividad_con_rut_nuevo_pregunta_y_lo_registra(self):
        respuesta = self.registrar(rut_solicitante='11222333-9', agregar_solicitante='')
        self.assertIn('no está registrado', str(respuesta.context['form'].errors['rut_solicitante']))
        self.registrar(rut_solicitante='11222333-9')  # "Sí": agregar_solicitante viene en True
        self.assertEqual(Actividad.objects.get().solicitante.rut, '11222333-9')


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class FelicitacionesYReclamosTest(BaseActividades):
    """Pantalla solo para Delegado y Administrador; la felicitación suma puntos al cumplimiento total."""
    def setUp(self):
        super().setUp()
        self.periodo = self.datos['periodo']
        self.url = reverse('indicadores:felicitaciones_reclamos')

    def total(self, usuario):
        from IndicadoresApp.calculos import seguimiento_usuario
        return seguimiento_usuario(usuario, self.periodo, self.hoy)['avance_logrado']

    def felicitar(self, funcionario, **extra):
        datos = {'persona': funcionario.username, 'fecha': self.hoy.isoformat(), 'motivo': 'Muy buena atención'}
        datos = {f'felicitacion-{campo}': valor for campo, valor in datos.items()}
        datos.update({f'felicitacion-{campo}': valor for campo, valor in extra.items()})
        return self.client.post(reverse('indicadores:felicitacion_crear'), datos)

    def test_solo_delegado_y_admin_ven_la_pantalla_y_el_enlace(self):
        for rut in ['33333333-3', '11111111-1']:
            self.entrar(rut)
            self.assertEqual(self.client.get(self.url).status_code, 200, rut)
            self.assertIn(self.url, self.client.get(reverse('actividades:mi_gestion')).content.decode(), rut)
        for rut in ['55555555-5', '22222222-2']:  # Funcionario y Coordinador
            self.entrar(rut)
            self.assertRedirects(self.client.get(self.url), reverse('actividades:mi_gestion'), msg_prefix=rut)
            self.assertNotIn(self.url, self.client.get(reverse('actividades:mi_gestion')).content.decode(), rut)

    def test_la_felicitacion_suma_aunque_el_item_no_este_en_las_metas(self):
        self.periodo.puntos_felicitacion = 2
        self.periodo.save()
        antes = self.total(self.func)
        self.entrar('33333333-3')
        self.felicitar(self.func)
        felicitacion = Felicitacion.objects.get()
        self.assertEqual((felicitacion.funcionario, felicitacion.ajuste.valor), (self.func, 2))
        self.assertEqual(self.total(self.func), antes + 2)
        self.assertTrue(Auditoria.objects.filter(entidad='Felicitacion', evento='CREACION').exists())
        # Al eliminarla, los puntos dejan de sumar
        self.client.post(reverse('indicadores:felicitacion_eliminar', args=[felicitacion.pk]))
        self.assertFalse(AjusteDesempeno.objects.exists())
        self.assertEqual(self.total(self.func), antes)

    def test_el_delegado_solo_elige_funcionarios_de_su_delegacion(self):
        self.entrar('33333333-3')
        self.felicitar(self.otro)  # Rural
        self.assertFalse(Felicitacion.objects.exists())
        self.entrar('11111111-1')  # el Administrador, a cualquiera
        self.felicitar(self.otro)
        self.assertEqual(Felicitacion.objects.get().funcionario, self.otro)

    def test_las_felicitaciones_respetan_el_tope(self):
        self.periodo.puntos_felicitacion = 500
        self.periodo.save()
        self.entrar('33333333-3')
        self.felicitar(self.func)
        self.assertEqual(self.total(self.func), self.periodo.tope_cumplimiento)

    def test_sin_metas_se_registra_y_avisa(self):
        self.func.cargo = None
        self.func.save()
        self.entrar('33333333-3')
        respuesta = self.client.post(reverse('indicadores:felicitacion_crear'),
                                     {'felicitacion-persona': self.func.username, 'felicitacion-fecha': self.hoy.isoformat(),
                                      'felicitacion-motivo': 'Gracias'},
                                     follow=True)
        self.assertTrue(Felicitacion.objects.exists())
        self.assertIn('no tiene metas', respuesta.content.decode())

    def test_reclamo_queda_pendiente_hasta_que_se_responde(self):
        self.entrar('33333333-3')
        self.client.post(reverse('indicadores:reclamo_crear'),
                         {'reclamo-persona': self.func.username, 'reclamo-fecha': self.hoy.isoformat(),
                          'reclamo-motivo': 'No llegó a la visita'})
        reclamo = Reclamo.objects.get()
        self.assertEqual(reclamo.estado, 'PENDIENTE')
        antes = self.total(self.func)
        self.client.post(reverse('indicadores:reclamo_responder', args=[reclamo.pk]), {'respuesta': ''})
        reclamo.refresh_from_db()
        self.assertEqual(reclamo.estado, 'PENDIENTE')  # sin respuesta no se cierra
        self.client.post(reverse('indicadores:reclamo_responder', args=[reclamo.pk]), {'respuesta': 'Se reprogramó'})
        reclamo.refresh_from_db()
        self.assertEqual((reclamo.estado, reclamo.respondido_por), ('RESUELTO', self.delegado))
        self.assertEqual(self.total(self.func), antes)  # el reclamo no afecta el puntaje


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class RequerimientosPendientesTest(BaseActividades):
    """RF-005 (validación del periodo), RF-015 (hasta 3 gestiones por atención) y RF-033 (exportar el Semáforo)."""

    # ----- RF-005 -----
    def test_periodo_rechaza_termino_anterior_al_inicio(self):
        from django.core.exceptions import ValidationError
        from IndicadoresApp.models import Periodo
        periodo = Periodo(nombre='Prueba', fecha_inicio=self.hoy, fecha_termino=self.hoy - timedelta(days=1))
        with self.assertRaises(ValidationError) as error:
            periodo.full_clean()
        self.assertIn('fecha_termino', error.exception.message_dict)

    def test_periodo_calcula_sus_dias_y_no_acepta_mas_dias_que_los_del_periodo(self):
        from datetime import date
        from django.core.exceptions import ValidationError
        from IndicadoresApp.models import Periodo
        periodo = Periodo(nombre='T3 prueba', fecha_inicio=date(2026, 7, 1), fecha_termino=date(2026, 9, 30))
        periodo.full_clean()
        self.assertEqual(periodo.dias_computables, 92)  # 1 de julio al 30 de septiembre, ambos incluidos
        periodo.dias_computables = 100
        with self.assertRaises(ValidationError):
            periodo.full_clean()

    # ----- RF-015 -----
    def atencion_con_gestiones(self, cantidad):
        tipo = Catalogo.objects.get_or_create(tipo='TIPO_ATENCION', nombre='Ayuda social')[0]
        persona = Solicitante.objects.create(rut='11222333-9', nombre='Juan Pérez', telefono='912345678')
        atencion = AtencionSocial.objects.create(usuario=self.func, solicitante=persona, tipo_atencion=tipo)
        for _ in range(cantidad):
            actividad = self.crear()
            actividad.solicitud = atencion
            actividad.save()
        return atencion

    def test_atencion_admite_hasta_tres_gestiones(self):
        atencion = self.atencion_con_gestiones(3)
        self.assertFalse(atencion.admite_gestion())
        cuarta = self.crear()
        self.entrar('33333333-3')
        self.client.post(reverse('actividades:atencion_vincular', args=[atencion.pk]), {'actividad': cuarta.pk})
        cuarta.refresh_from_db()
        self.assertIsNone(cuarta.solicitud)
        self.assertEqual(atencion.cantidad_gestiones(), 3)

    def test_con_dos_gestiones_todavia_se_puede_vincular_una_tercera(self):
        atencion = self.atencion_con_gestiones(2)
        tercera = self.crear()
        self.entrar('33333333-3')
        self.client.post(reverse('actividades:atencion_vincular', args=[atencion.pk]), {'actividad': tercera.pk})
        tercera.refresh_from_db()
        self.assertEqual(tercera.solicitud, atencion)

    def test_formulario_no_vincula_una_cuarta_gestion(self):
        atencion = self.atencion_con_gestiones(3)
        self.entrar('55555555-5')
        respuesta = self.registrar(solicitud=atencion.pk, rut_solicitante='11.222.333-9', nombre_solicitante='',
                                   telefono_solicitante='')
        self.assertIn('solicitud', respuesta.context['form'].errors)
        self.assertEqual(atencion.cantidad_gestiones(), 3)

    # ----- RF-033 -----
    def test_exportar_semaforo_en_csv_con_filtros_y_fecha(self):
        self.entrar('33333333-3')
        respuesta = self.client.get(reverse('indicadores:semaforo_exportar'), {'q': 'zzz-sin-coincidencias'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta['Content-Type'].startswith('text/csv'))
        self.assertIn('attachment', respuesta['Content-Disposition'])
        texto = respuesta.content.decode('utf-8-sig')
        self.assertIn('Búsqueda;zzz-sin-coincidencias', texto)
        self.assertIn('Fecha de generación', texto)
        self.assertIn('Área;Responsable;Delegación', texto)
        self.assertTrue(Auditoria.objects.filter(entidad='Exportación', id_entidad='Semáforo').exists())

    def test_exportar_trae_las_mismas_filas_que_la_pantalla(self):
        self.entrar('11111111-1')
        pantalla = self.client.get(reverse('indicadores:semaforo')).context['seguimiento']
        texto = self.client.get(reverse('indicadores:semaforo_exportar')).content.decode('utf-8-sig')
        for fila in pantalla:
            self.assertIn(fila['responsable'], texto)

    def test_funcionario_no_puede_exportar(self):
        self.entrar('55555555-5')
        respuesta = self.client.get(reverse('indicadores:semaforo_exportar'))
        self.assertEqual(respuesta.status_code, 302)


class HitosTest(BaseActividades):
    """Hitos: los compromisos (PROGRAMADA) por fecha límite, con su responsable."""

    def test_muestra_compromisos_de_la_delegacion_agrupados(self):
        vencido = self.crear(dias=-2)
        semana = self.crear(dias=3, encargado=self.companero)
        despues = self.crear(dias=20)
        self.crear(estado='EN_TUBO')                                  # el Tubo no es un hito
        self.crear(usuario=self.otro, territorio=self.territorio_rural)  # otra delegación
        self.entrar('77777777-7')
        respuesta = self.client.get(reverse('actividades:hitos'))
        self.assertEqual(respuesta.status_code, 200)
        grupos = {g['clave']: [h['actividad'] for h in g['hitos']] for g in respuesta.context['grupos']}
        self.assertEqual(grupos, {'vencidos': [vencido], 'semana': [semana], 'despues': [despues]})
        self.assertContains(respuesta, reverse('actividades:actividad_detalle', args=[semana.pk]) + '?desde=hitos')
        self.assertEqual(respuesta.context['grupos'][1]['hitos'][0]['responsable'], self.companero)

    def test_solo_los_mios(self):
        mio = self.crear(dias=4)
        self.crear(dias=4, usuario=self.companero)
        self.entrar('55555555-5')
        respuesta = self.client.get(reverse('actividades:hitos'), {'mios': '1'})
        self.assertEqual([h['actividad'] for g in respuesta.context['grupos'] for h in g['hitos']], [mio])

    def test_detalle_vuelve_a_hitos(self):
        actividad = self.crear(dias=4)
        self.entrar('55555555-5')
        respuesta = self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]), {'desde': 'hitos'})
        self.assertContains(respuesta, 'title="Volver a Hitos"')


class SeguimientoTuboTest(BaseActividades):
    """Etapas de las actividades del Tubo: Ingresado, Pendiente, En proceso y Realizado (guía 4.2)."""

    def cambiar(self, actividad, estado, **extra):
        return self.client.post(reverse('actividades:cambiar_estado_tubo', args=[actividad.pk]),
                                {'estado_tubo': estado, **extra})

    def test_parte_ingresado_y_el_responsable_lo_cambia_con_observacion(self):
        actividad = self.crear(estado='EN_TUBO')
        self.assertEqual(actividad.seguimiento_tubo(), 'INGRESADO')
        self.entrar('55555555-5')
        self.cambiar(actividad, 'PENDIENTE', observacion='Esperando respuesta de la empresa eléctrica')
        actividad.refresh_from_db()
        self.assertEqual(actividad.seguimiento_tubo(), 'PENDIENTE')
        self.assertTrue(actividad.comentarios.filter(texto__contains='Esperando respuesta').exists())
        self.assertTrue(Auditoria.objects.filter(entidad='Actividad', id_entidad=str(actividad.pk),
                                                 valor_nuevo='Tubo: PENDIENTE').exists())

    def test_realizado_no_se_elige_y_llega_con_la_ejecucion(self):
        actividad = self.crear(estado='EN_TUBO')
        self.entrar('55555555-5')
        self.cambiar(actividad, 'REALIZADO')
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado_tubo, 'INGRESADO')
        actividad.estado = 'EVIDENCIA_INGRESADA'
        actividad.save()
        self.assertEqual(actividad.seguimiento_tubo(), 'REALIZADO')

    def test_otro_funcionario_ni_otra_delegacion_lo_cambian(self):
        actividad = self.crear(estado='EN_TUBO')
        for rut in ['77777777-7', '44444444-4']:
            self.entrar(rut)
            self.cambiar(actividad, 'EN_PROCESO')
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado_tubo, 'INGRESADO')
        self.entrar('33333333-3')  # su Delegado sí
        self.cambiar(actividad, 'EN_PROCESO')
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado_tubo, 'EN_PROCESO')

    def test_actividad_normal_no_tiene_seguimiento(self):
        actividad = self.crear(dias=3)
        self.assertIsNone(actividad.seguimiento_tubo())
        self.entrar('55555555-5')
        self.cambiar(actividad, 'PENDIENTE')
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado_tubo, 'INGRESADO')

    def test_resumen_y_filtro_en_el_tubo(self):
        uno = self.crear(estado='EN_TUBO')
        dos = self.crear(estado='EN_TUBO', usuario=self.companero)
        Actividad.objects.filter(pk=dos.pk).update(estado_tubo='EN_PROCESO')
        tres = self.crear(estado='EN_TUBO')
        Actividad.objects.filter(pk=tres.pk).update(estado='VALIDADA')
        self.entrar('33333333-3')
        respuesta = self.client.get(reverse('actividades:tubo_trabajo'))
        resumen = respuesta.context['resumen_tubo']
        self.assertEqual(resumen['total'], 3)
        self.assertEqual({e['codigo']: e['cantidad'] for e in resumen['estados']},
                         {'INGRESADO': 1, 'PENDIENTE': 0, 'EN_PROCESO': 1, 'REALIZADO': 1})
        self.assertEqual(resumen['porcentaje'], 33.3)
        filtrado = self.client.get(reverse('actividades:tubo_trabajo'), {'seguimiento': 'REALIZADO'})
        self.assertEqual([a['id'] for a in filtrado.context['actividades']], [tres.pk])
        filtrado = self.client.get(reverse('actividades:tubo_trabajo'), {'seguimiento': 'INGRESADO'})
        self.assertEqual([a['id'] for a in filtrado.context['actividades']], [uno.pk])


class JuntaDeVecinosTest(BaseActividades):
    def test_junta_de_vecinos_es_un_tipo_de_organizacion(self):
        organizacion = Organizacion.objects.create(nombre='Junta de Vecinos Villa Ejemplo', tipo='JUNTA_VECINOS', fecha_inscripcion=self.hoy)
        self.assertEqual(organizacion.get_tipo_display(), 'Junta de vecinos')


class TendenciaSemanalTest(BaseActividades):
    """Tendencia semanal de Mi Gestión: avance contra lo esperado al cierre de cada semana del periodo."""

    def validada(self, usuario, dias_atras):
        return Actividad.objects.create(
            solicitud_problema='Atención', accion='Atención realizada', item=self.datos['item'], periodo=self.datos['periodo'],
            usuario=usuario, estado='VALIDADA', fecha_realizacion=self.hoy - timedelta(days=dias_atras), territorio=self.territorio)

    def test_cortes_semanales_terminan_hoy(self):
        from IndicadoresApp.calculos import cortes_semanales
        cortes = cortes_semanales(self.datos['periodo'], self.hoy)
        self.assertEqual(cortes[-1], self.hoy)
        self.assertTrue(all(c.weekday() == 6 for c in cortes[:-1]))  # domingos
        self.assertTrue(all(self.datos['periodo'].fecha_inicio <= c <= self.hoy for c in cortes))

    def test_cuenta_en_la_semana_en_que_se_realizo(self):
        from IndicadoresApp.calculos import tendencia_semanal
        self.validada(self.func, dias_atras=5)
        puntos = tendencia_semanal(self.datos['periodo'], self.hoy, [self.func])
        hace_cinco = (self.hoy - timedelta(days=5)).isoformat()
        antes = [p for p in puntos if p['fecha'] < hace_cinco]
        despues = [p for p in puntos if p['fecha'] >= hace_cinco]
        self.assertTrue(all(p['avance'] == 0 for p in antes))
        self.assertTrue(despues and all(p['avance'] > 0 for p in despues))  # meta 10: una actividad = 10%
        self.assertEqual(puntos[-1]['avance'], 10.0)
        self.assertEqual(puntos[-1]['esperado'], float(self.datos['periodo'].porcentaje_transcurrido(self.hoy)))

    def test_funcionario_ve_la_suya_y_no_puede_elegir_otra(self):
        self.validada(self.companero, dias_atras=2)
        self.entrar('55555555-5')
        contexto = self.client.get(reverse('actividades:mi_gestion'), {'tendencia': self.companero.pk}).context
        self.assertEqual(contexto['tendencia']['titulo'], 'Mi avance semana a semana')
        self.assertEqual(contexto['tendencia']['puntos'][-1]['avance'], 0.0)
        self.assertEqual(contexto['opciones_tendencia'], [])

    def test_delegado_ve_el_colectivo_y_elige_un_funcionario(self):
        self.validada(self.func, dias_atras=2)
        self.entrar('33333333-3')
        colectivo = self.client.get(reverse('actividades:mi_gestion')).context
        self.assertIn('Puntaje colectivo', colectivo['tendencia']['titulo'])
        self.assertEqual(colectivo['tendencia']['puntos'][-1]['avance'], 5.0)  # promedio de 10% y 0%
        self.assertNotIn(self.otro, colectivo['opciones_tendencia'])  # otra delegación
        uno = self.client.get(reverse('actividades:mi_gestion'), {'tendencia': self.func.pk}).context
        self.assertEqual(uno['tendencia']['puntos'][-1]['avance'], 10.0)
        ajeno = self.client.get(reverse('actividades:mi_gestion'), {'tendencia': self.otro.pk}).context
        self.assertIn('Puntaje colectivo', ajeno['tendencia']['titulo'])  # fuera de su delegación: se ignora

    def test_ultimo_punto_cuadra_con_mi_gestion_y_el_semaforo(self):
        from IndicadoresApp.calculos import tendencia_semanal, seguimiento_usuario
        self.validada(self.func, dias_atras=3)
        Ausencia.objects.create(usuario=self.func, tipo='VACACIONES', desde=self.hoy + timedelta(days=2),
                                hasta=self.hoy + timedelta(days=4), registrado_por=self.delegado)
        hoy = seguimiento_usuario(self.func, self.datos['periodo'], self.hoy)
        puntos = tendencia_semanal(self.datos['periodo'], self.hoy, [self.func])
        self.assertEqual(puntos[-1]['avance'], float(hoy['avance_logrado']))
        self.assertEqual(puntos[-1]['esperado'], float(hoy['objetivo_hoy']))
        self.entrar('55555555-5')
        mi_gestion = self.client.get(reverse('actividades:mi_gestion')).context
        self.assertEqual(mi_gestion['tendencia']['puntos'][-1]['avance'], float(mi_gestion['mi_avance']['avance_logrado']))

    def test_la_ausencia_cuenta_desde_que_se_registro(self):
        from IndicadoresApp.calculos import tendencia_semanal
        self.validada(self.func, dias_atras=8)
        sin_ausencia = tendencia_semanal(self.datos['periodo'], self.hoy, [self.func])
        # Vacaciones registradas hoy: las semanas anteriores no cambian; el punto de hoy sube (la meta baja)
        Ausencia.objects.create(usuario=self.func, tipo='VACACIONES', desde=self.hoy, hasta=self.hoy + timedelta(days=4),
                                registrado_por=self.delegado)
        con_ausencia = tendencia_semanal(self.datos['periodo'], self.hoy, [self.func])
        self.assertEqual([p['avance'] for p in sin_ausencia[:-1]], [p['avance'] for p in con_ausencia[:-1]])
        self.assertGreater(con_ausencia[-1]['avance'], sin_ausencia[-1]['avance'])


class EncargadoPorDefectoTest(BaseActividades):
    """El encargado es quien registra, salvo que elija otro en la lista con buscador."""
    def test_formulario_muestra_a_quien_registra_y_la_opcion_de_elegir_otro(self):
        self.entrar('55555555-5')
        for url in (reverse('actividades:actividad_crear'), reverse('actividades:actividad_crear_tubo')):
            respuesta = self.client.get(url)
            self.assertContains(respuesta, 'Seleccionar otro encargado')
            self.assertContains(respuesta, '(quien registra)')
            self.assertContains(respuesta, f'data-id="{self.companero.pk}"')
            self.assertNotContains(respuesta, f'data-id="{self.func.pk}"')
            self.assertNotContains(respuesta, 'Yo mismo')

    def test_sin_elegir_otro_el_encargado_es_quien_registra(self):
        self.entrar('55555555-5')
        self.registrar(encargado='')
        actividad = Actividad.objects.latest('pk')
        self.assertEqual(actividad.usuario, self.func)
        self.assertIsNone(actividad.encargado)

    def test_puede_elegir_a_otro_encargado(self):
        self.entrar('55555555-5')
        self.registrar(encargado=str(self.companero.pk))
        self.assertEqual(Actividad.objects.latest('pk').encargado, self.companero)
