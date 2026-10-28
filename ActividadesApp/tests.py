import io
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from ActividadesApp.models import Actividad, Evidencia, ComentarioActividad, Territorio, AtencionSocial
from IndicadoresApp.calculos import indicadores_usuario
from UsuarioApp.models import Delegacion, Catalogo
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE


def png_valido():
    """PNG de 1x1 píxel generado con Pillow (ImageField exige una imagen que Pillow pueda abrir)."""
    salida = io.BytesIO()
    Image.new('RGB', (1, 1), (173, 0, 0)).save(salida, 'PNG')
    return salida.getvalue()


PNG = png_valido()


def foto(nombre='foto.png'):
    return SimpleUploadedFile(nombre, PNG, content_type='image/png')


class BaseActividades(TestCase):
    """Datos comunes: dos Funcionarios y un Delegado en Las Compañías; un Funcionario y un Delegado en Rural."""

    def setUp(self):
        self.datos = crear_datos_base()
        compania = self.datos['delegacion']
        self.rural = Delegacion.objects.get(nombre='RURAL')
        self.territorio = self.datos['territorio']                       # Sector Alto (Las Compañías)
        self.territorio_bajo = Territorio.objects.get(nombre='Sector Bajo')
        self.territorio_rural = Territorio.objects.get(nombre='Localidad Norte')
        self.func = crear_usuario('55555555-5', 'Funcionario', compania, self.datos['cargo'])
        self.companero = crear_usuario('77777777-7', 'Funcionario', compania, self.datos['cargo'])
        self.otro = crear_usuario('88888888-8', 'Funcionario', self.rural, self.datos['cargo'])
        self.delegado = crear_usuario('33333333-3', 'Delegado', compania)
        self.delegado_rural = crear_usuario('44444444-4', 'Delegado', self.rural)
        self.coordinador = crear_usuario('22222222-2', 'Coordinador')
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.hoy = timezone.localdate()

    def entrar(self, rut):
        self.client.login(username=rut, password=CLAVE)

    def registrar(self, **extra):
        datos = {'solicitud_problema': 'Vecinos piden poda', 'accion': 'Inspección', 'item': '1',
                 'territorio': self.territorio.pk,
                 'fecha_realizacion': self.hoy.isoformat(), 'comentario': 'Se inspeccionó el sector'}
        datos.update(extra)
        return self.client.post(reverse('actividades:actividad_crear'), datos)

    def crear(self, estado='PROGRAMADA', usuario=None, dias=5, territorio=None, encargado=None):
        """Actividad pendiente creada directo en la base: PROGRAMADA (con fecha) o EN_TUBO (sin fecha)."""
        en_tubo = estado == 'EN_TUBO'
        return Actividad.objects.create(
            solicitud_problema='Reparar luminaria', accion='Gestión con alumbrado', item=self.datos['item'],
            periodo=self.datos['periodo'], usuario=usuario or self.func, estado=estado, depende_externos=en_tubo,
            fecha_realizacion=None if en_tubo else self.hoy + timedelta(days=dias),
            territorio=territorio or self.territorio, encargado=encargado)

    def ejecutada(self, usuario=None, encargado=None):
        actividad = self.crear(usuario=usuario, encargado=encargado)
        evidencia = Evidencia.objects.create(actividad=actividad, comentario='Hecho', version=1)
        actividad.sincronizar_estado()
        return actividad, evidencia

    def ejecutar(self, actividad, **datos):
        datos.setdefault('comentario', 'Listo')
        return self.client.post(reverse('actividades:registrar_ejecucion', args=[actividad.pk]), datos)

    def folios_tubo(self, **filtros):
        return [a['folio'] for a in self.client.get(reverse('actividades:tubo_trabajo'), filtros).context['actividades']]


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class RegistroActividadTest(BaseActividades):
    """La fecha de realización decide el estado: hoy o antes = ejecutada; después = compromiso;
    depende de factores externos = Tubo de Trabajo sin fecha."""

    def test_hoy_con_comentario_y_sin_foto_queda_registrada(self):
        self.entrar('55555555-5')
        self.assertRedirects(self.registrar(), reverse('actividades:mi_gestion'))
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.estado, actividad.fecha_realizacion, actividad.depende_externos),
                         ('REGISTRADA', self.hoy, False))
        ejecucion = actividad.evidencias.get()
        self.assertEqual((ejecucion.comentario, bool(ejecucion.imagen)), ('Se inspeccionó el sector', False))

    def test_hoy_con_foto_guarda_la_foto(self):
        self.entrar('55555555-5')
        self.registrar(imagen=foto())
        self.assertTrue(Actividad.objects.get().evidencias.get().imagen)

    def test_hoy_sin_comentario_no_se_guarda(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(comentario='  ')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('comentario', respuesta.context['form'].errors)
        self.assertEqual(Actividad.objects.count(), 0)

    def test_fecha_futura_queda_como_compromiso(self):
        self.entrar('55555555-5')
        futura = self.hoy + timedelta(days=7)
        self.assertRedirects(self.registrar(fecha_realizacion=futura.isoformat(), comentario=''),
                             reverse('actividades:mi_gestion'))
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.estado, actividad.fecha_realizacion), ('PROGRAMADA', futura))
        self.assertTrue(actividad.es_compromiso())
        self.assertEqual(actividad.evidencias.count(), 0)
        self.assertEqual(self.folios_tubo(), [])  # un compromiso con fecha no va al Tubo

    def test_factores_externos_va_al_tubo_sin_fecha(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(depende_externos='on', fecha_realizacion='')
        self.assertRedirects(respuesta, reverse('actividades:tubo_trabajo'))
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.estado, actividad.fecha_realizacion, actividad.depende_externos), ('EN_TUBO', None, True))
        self.assertEqual(actividad.evidencias.count(), 0)
        self.entrar('77777777-7')  # el compañero de delegación lo ve en el Tubo
        self.assertEqual(self.folios_tubo(), [actividad.folio()])

    def test_sin_fecha_y_sin_tubo_no_se_guarda(self):
        self.entrar('55555555-5')
        respuesta = self.registrar(fecha_realizacion='')
        self.assertIn('fecha_realizacion', respuesta.context['form'].errors)
        self.assertEqual(Actividad.objects.count(), 0)

    def test_territorio_de_la_lista_de_su_delegacion(self):
        self.entrar('55555555-5')
        opciones = list(self.client.get(reverse('actividades:actividad_crear')).context['form'].fields['territorio'].queryset)
        self.assertEqual(sorted(t.nombre for t in opciones), ['Sector Alto', 'Sector Bajo'])
        self.registrar(territorio=self.territorio_rural.pk)  # territorio de otra delegación
        self.registrar(territorio='')                        # sin territorio
        self.assertEqual(Actividad.objects.count(), 0)

    def test_fecha_anterior_al_periodo_no_se_guarda(self):
        self.entrar('55555555-5')
        antigua = self.datos['periodo'].fecha_inicio - timedelta(days=1)
        self.assertEqual(self.registrar(fecha_realizacion=antigua.isoformat()).status_code, 200)
        self.assertEqual(Actividad.objects.count(), 0)

    def test_tubo_con_fecha_de_ejecucion_opcional(self):
        self.entrar('55555555-5')
        futura = self.hoy + timedelta(days=6)
        self.assertRedirects(self.registrar(depende_externos='on', fecha_realizacion=futura.isoformat()),
                             reverse('actividades:tubo_trabajo'))
        actividad = Actividad.objects.get()
        self.assertEqual((actividad.estado, actividad.fecha_realizacion, actividad.depende_externos), ('PROGRAMADA', futura, True))
        self.assertEqual(self.folios_tubo(), [actividad.folio()])  # sigue en el Tubo, ahora con fecha
        # Una fecha pasada en el Tubo no se acepta
        self.registrar(depende_externos='on', fecha_realizacion=(self.hoy - timedelta(days=1)).isoformat())
        self.assertEqual(Actividad.objects.count(), 1)
        # La tabla dice que aún no hay fecha cuando no se eligió
        self.registrar(depende_externos='on', fecha_realizacion='')
        self.assertContains(self.client.get(reverse('actividades:tubo_trabajo')), 'Aún no se ha agregado fecha de ejecución')

    def test_ya_no_hay_contacto_ni_telefono_en_la_actividad(self):
        self.assertFalse(hasattr(Actividad(), 'contacto'))
        self.assertFalse(hasattr(Actividad(), 'telefono'))

    def test_encargado_desde_el_formulario_solo_de_su_delegacion(self):
        self.entrar('55555555-5')
        candidatos = list(self.client.get(reverse('actividades:actividad_crear')).context['form'].fields['encargado'].queryset)
        self.assertEqual(candidatos, [self.companero])  # ni él mismo ni el de Rural
        self.registrar(encargado=self.otro.pk)  # de otra delegación: no se acepta
        self.assertEqual(Actividad.objects.count(), 0)
        self.registrar(encargado=self.companero.pk, fecha_realizacion=(self.hoy + timedelta(days=2)).isoformat())
        self.assertEqual(Actividad.objects.get().encargado, self.companero)


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class EjecucionYEncargadoTest(BaseActividades):
    def test_ejecutar_compromiso_sin_foto(self):
        actividad = self.crear(dias=3)
        self.entrar('55555555-5')
        self.ejecutar(actividad)
        actividad.refresh_from_db()
        self.assertEqual((actividad.estado, actividad.fecha_realizacion), ('REGISTRADA', self.hoy))

    def test_ejecucion_exige_comentario(self):
        actividad = self.crear()
        self.entrar('55555555-5')
        self.ejecutar(actividad, comentario='', imagen=foto())
        actividad.refresh_from_db()
        self.assertEqual((actividad.estado, actividad.evidencias.count()), ('PROGRAMADA', 0))

    def test_solo_quien_registro_o_el_encargado_ejecutan(self):
        actividad = self.crear()
        self.entrar('77777777-7')
        self.assertFalse(self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk])).context['puede_ejecutar'])
        self.ejecutar(actividad)
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'PROGRAMADA')
        # Con el compañero como encargado, sí puede
        actividad.encargado = self.companero
        actividad.save()
        self.ejecutar(actividad)
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'REGISTRADA')

    def test_asignar_fecha_en_el_tubo(self):
        actividad = self.crear('EN_TUBO')
        self.entrar('55555555-5')
        url = reverse('actividades:asignar_fecha', args=[actividad.pk])
        self.client.post(url, {'fecha_realizacion': (self.hoy - timedelta(days=1)).isoformat()})  # pasada: no
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'EN_TUBO')
        fecha = self.hoy + timedelta(days=4)
        self.client.post(url, {'fecha_realizacion': fecha.isoformat()})
        actividad.refresh_from_db()
        self.assertEqual((actividad.estado, actividad.fecha_realizacion), ('PROGRAMADA', fecha))
        self.assertEqual(self.folios_tubo(), [actividad.folio()])  # sigue pendiente en el Tubo
        self.assertEqual(self.folios_tubo(estado='SIN_FECHA'), [])
        self.assertEqual(self.folios_tubo(estado='CON_FECHA'), [actividad.folio()])

    def asignar(self, actividad, funcionario):
        self.client.post(reverse('actividades:asignar_encargado', args=[actividad.pk]), {'encargado': funcionario.pk})
        actividad.refresh_from_db()
        return actividad.encargado

    def test_delegado_asigna_encargado_de_su_delegacion(self):
        actividad = self.crear()
        self.entrar('33333333-3')
        self.assertIsNone(self.asignar(actividad, self.otro))        # Funcionario de otra delegación: no
        self.assertIsNone(self.asignar(actividad, self.delegado))    # el encargado debe ser Funcionario
        self.assertEqual(self.asignar(actividad, self.companero), self.companero)
        # No asigna en actividades de otra delegación
        ajena = self.crear(usuario=self.otro, territorio=self.territorio_rural)
        self.assertIsNone(self.asignar(ajena, self.otro))

    def test_coordinador_y_admin_asignan_en_todas_las_delegaciones(self):
        actividad = self.crear()
        self.entrar('22222222-2')
        self.assertEqual(self.asignar(actividad, self.otro), self.otro)
        self.entrar('11111111-1')
        self.assertEqual(self.asignar(actividad, self.companero), self.companero)

    def test_funcionario_no_asigna_encargado(self):
        actividad = self.crear()
        self.entrar('55555555-5')
        self.assertIsNone(self.asignar(actividad, self.companero))

    def test_no_se_asigna_encargado_a_una_actividad_ejecutada(self):
        actividad, evidencia = self.ejecutada()
        self.entrar('33333333-3')
        self.assertIsNone(self.asignar(actividad, self.companero))

    def test_la_meta_cuenta_para_el_encargado(self):
        actividad, evidencia = self.ejecutada(encargado=self.companero)
        self.entrar('33333333-3')
        self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]), {'decision': 'APROBAR'})
        avance = {u.username: indicadores_usuario(u, self.datos['periodo'], self.hoy)[0].avance_actual
                  for u in [self.func, self.companero]}
        self.assertEqual(avance, {'55555555-5': 0, '77777777-7': 1})

    def test_encargado_ve_la_actividad_en_mi_gestion(self):
        actividad = self.crear(encargado=self.companero)
        self.entrar('77777777-7')
        contexto = self.client.get(reverse('actividades:mi_gestion')).context
        self.assertEqual([a['folio'] for a in contexto['pendientes']], [actividad.folio()])


class BitacoraTest(BaseActividades):
    def comentar(self, actividad, texto='Se llamó a la directiva'):
        return self.client.post(reverse('actividades:comentar_actividad', args=[actividad.pk]), {'texto': texto})

    def test_responsable_y_delegado_comentan_con_fecha(self):
        actividad = self.crear()
        self.entrar('55555555-5')
        self.assertRedirects(self.comentar(actividad),
                             reverse('actividades:actividad_detalle', args=[actividad.pk]) + '#bitacora',
                             fetch_redirect_response=False)
        self.entrar('33333333-3')
        self.comentar(actividad, 'Revisado por el Delegado')
        comentarios = list(actividad.comentarios.all())
        self.assertEqual(len(comentarios), 2)
        self.assertEqual(comentarios[0].texto, 'Revisado por el Delegado')  # el más reciente primero
        self.assertIsNotNone(comentarios[0].fecha)
        self.assertContains(self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk])), 'Revisado por el Delegado')

    def test_coordinador_y_otros_no_comentan(self):
        actividad = self.crear()
        for rut in ['22222222-2', '77777777-7', '44444444-4']:
            self.entrar(rut)
            self.comentar(actividad)
        self.entrar('55555555-5')
        self.comentar(actividad, '   ')  # vacío
        self.assertEqual(ComentarioActividad.objects.count(), 0)


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class ValidacionTest(BaseActividades):
    def test_delegado_valida_y_suma_avance(self):
        actividad, evidencia = self.ejecutada()
        self.assertEqual(actividad.estado, 'REGISTRADA')
        self.entrar('33333333-3')
        pantalla = self.client.get(reverse('actividades:verificacion'), {'evidencia_id': evidencia.pk})
        self.assertContains(pantalla, actividad.folio())
        self.assertContains(pantalla, 'value="RECHAZAR"')
        self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]), {'decision': 'APROBAR'})
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'VALIDADA')
        self.entrar('55555555-5')
        contexto = self.client.get(reverse('actividades:mi_gestion')).context
        self.assertEqual(contexto['metas'][0]['avance_actual'], 1)
        self.assertEqual(contexto['resumen']['completadas'], 1)

    def test_rechazo_exige_motivo_y_se_vuelve_a_registrar(self):
        actividad, evidencia = self.ejecutada()
        url = reverse('actividades:validar_evidencia', args=[evidencia.pk])
        self.entrar('33333333-3')
        self.client.post(url, {'decision': 'RECHAZAR'})  # sin motivo
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.estado_revision, 'PENDIENTE')
        self.client.post(url, {'decision': 'RECHAZAR', 'observacion': 'Falta indicar con quién se reunió'})
        actividad.refresh_from_db()
        self.assertEqual(actividad.estado, 'RECHAZADA')
        self.entrar('55555555-5')
        detalle = self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk]))
        self.assertContains(detalle, 'Falta indicar con quién se reunió')
        self.assertTrue(detalle.context['puede_ejecutar'])
        self.ejecutar(actividad, comentario='Reunión con la directiva completa')
        actividad.refresh_from_db()
        nueva = actividad.ejecucion_vigente()
        self.assertEqual((actividad.estado, nueva.version, nueva.reemplaza_a_id), ('REGISTRADA', 2, evidencia.pk))

    def test_coordinador_no_valida(self):
        actividad, evidencia = self.ejecutada()
        self.entrar('22222222-2')
        self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]), {'decision': 'APROBAR'})
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.estado_revision, 'PENDIENTE')

    def test_compromiso_cuenta_en_el_trimestre_en_que_se_ejecuta(self):
        from IndicadoresApp.models import Periodo
        anterior = Periodo.objects.create(nombre='Anterior', fecha_inicio=self.hoy - timedelta(days=60),
                                          fecha_termino=self.hoy - timedelta(days=10), dias_computables=40)
        actividad = self.crear()
        actividad.periodo = anterior
        actividad.save()
        self.entrar('55555555-5')
        self.ejecutar(actividad)
        actividad.refresh_from_db()
        self.assertEqual(actividad.periodo, self.datos['periodo'])


class TuboYMiGestionTest(BaseActividades):
    def test_filtros_del_tubo(self):
        propio = self.crear('EN_TUBO')
        ajeno = self.crear('EN_TUBO', usuario=self.companero, territorio=self.territorio_bajo)
        con_fecha = self.crear(dias=-2)
        con_fecha.depende_externos = True  # vino del Tubo y ya tiene fecha (vencida)
        con_fecha.save()
        self.crear(dias=3)  # compromiso común: no es del Tubo
        self.entrar('55555555-5')
        self.assertEqual(sorted(self.folios_tubo()), sorted([propio.folio(), ajeno.folio(), con_fecha.folio()]))
        self.assertEqual(sorted(self.folios_tubo(estado='SIN_FECHA')), sorted([propio.folio(), ajeno.folio()]))
        self.assertEqual(self.folios_tubo(estado='VENCIDOS'), [con_fecha.folio()])
        self.assertEqual(self.folios_tubo(territorio=self.territorio_bajo.pk), [ajeno.folio()])
        self.assertEqual(sorted(self.folios_tubo(mios='1')), sorted([propio.folio(), con_fecha.folio()]))
        self.assertEqual(self.folios_tubo(responsable=self.companero.pk), [ajeno.folio()])
        self.assertEqual(len(self.folios_tubo(estado='TODOS')), 3)

    def test_otra_delegacion_no_ve_lo_ajeno(self):
        actividad = self.crear('EN_TUBO')
        self.entrar('88888888-8')
        self.assertEqual(self.folios_tubo(), [])
        self.assertRedirects(self.client.get(reverse('actividades:actividad_detalle', args=[actividad.pk])),
                             reverse('actividades:mi_gestion'))

    def test_dashboard_cuenta_pendientes(self):
        self.crear('EN_TUBO')
        self.crear()
        self.ejecutada()
        self.entrar('33333333-3')
        self.assertEqual(self.client.get(reverse('indicadores:dashboard')).context['compromisos_pendientes_count'], 2)

    def mi_gestion(self, rut, **parametros):
        self.entrar(rut)
        return self.client.get(reverse('actividades:mi_gestion'), parametros).context

    def test_mi_gestion_segun_rol(self):
        propia = self.crear()
        rural = self.crear(usuario=self.otro, territorio=self.territorio_rural)
        # Funcionario: sus actividades, sin pestaña de delegación
        contexto = self.mi_gestion('55555555-5')
        self.assertEqual([a['folio'] for a in contexto['mis_actividades']], [propia.folio()])
        self.assertFalse(contexto['ve_delegacion'])
        # Delegado: las de su delegación, aunque pida otra por la URL
        for parametros in [{}, {'delegacion': 'RURAL'}]:
            contexto = self.mi_gestion('33333333-3', **parametros)
            self.assertTrue(contexto['ve_delegacion'])
            self.assertEqual([a['folio'] for a in contexto['actividades_delegacion']], [propia.folio()])
        # Coordinador: todas, o la delegación que elija
        contexto = self.mi_gestion('22222222-2')
        self.assertEqual(len(contexto['actividades_delegacion']), 2)
        contexto = self.mi_gestion('22222222-2', delegacion='RURAL')
        self.assertEqual([a['folio'] for a in contexto['actividades_delegacion']], [rural.folio()])
        self.assertNotContains(self.client.get(reverse('actividades:mi_gestion')), 'Agregar Actividad')

    def test_delegado_filtra_por_funcionario(self):
        propia = self.crear()
        self.crear(usuario=self.companero)
        contexto = self.mi_gestion('33333333-3', funcionario=self.func.pk)
        self.assertEqual([a['folio'] for a in contexto['actividades_delegacion']], [propia.folio()])

    def test_admin_ve_solo_actividades_de_todas_las_delegaciones(self):
        propia = self.crear()
        rural = self.crear(usuario=self.otro, territorio=self.territorio_rural)
        contexto = self.mi_gestion('11111111-1')
        self.assertFalse(contexto['muestra_mis_actividades'])
        self.assertEqual(len(contexto['actividades_delegacion']), 2)  # por defecto, todas
        html = self.client.get(reverse('actividades:mi_gestion')).content.decode()
        self.assertNotIn('Mis metas', html)
        self.assertNotIn('Delegaciones', html)
        self.assertIn('name="delegacion" id="f_delegacion"', html)
        contexto = self.mi_gestion('11111111-1', delegacion='RURAL')
        self.assertEqual([a['folio'] for a in contexto['actividades_delegacion']], [rural.folio()])
        self.assertNotIn(propia.folio(), [a['folio'] for a in contexto['actividades_delegacion']])

    def test_coordinador_igual_que_admin_y_tarjetas_de_la_delegacion(self):
        self.crear()                                   # pendiente en Las Compañías
        self.ejecutada()                               # en revisión en Las Compañías
        self.crear(usuario=self.otro, territorio=self.territorio_rural)  # pendiente en Rural
        for rut in ['22222222-2', '11111111-1']:
            contexto = self.mi_gestion(rut)
            self.assertFalse(contexto['muestra_mis_actividades'])
            self.assertEqual(contexto['resumen'], {'total': 3, 'completadas': 0, 'pendientes': 2, 'en_revision': 1})
            contexto = self.mi_gestion(rut, delegacion='LAS_COMPANIAS')
            self.assertEqual(contexto['resumen'], {'total': 2, 'completadas': 0, 'pendientes': 1, 'en_revision': 1})
        html = self.client.get(reverse('actividades:mi_gestion')).content.decode()
        self.assertNotIn('Sin metas asignadas', html)



class SolicitudSocialTest(BaseActividades):
    """Registro de Atenciones: la solicitud se registra primero y las actividades se vinculan a ella."""

    def setUp(self):
        super().setUp()
        self.tipo = Catalogo.objects.create(tipo='TIPO_ATENCION', nombre='Ayuda social')

    def solicitud(self, usuario=None, nombre='María Ejemplo'):
        return AtencionSocial.objects.create(nombre_solicitante=nombre, rut_solicitante='12345678-5',
                                             tipo_atencion=self.tipo, usuario=usuario or self.func)

    def agregar_atencion(self, **extra):
        datos = {'nombre_solicitante': 'Juan Ficticio', 'rut_solicitante': '11.222.333-9', 'telefono_solicitante': '',
                 'tipo_atencion': self.tipo.pk, 'subtipo_atencion': ''}
        datos.update(extra)
        return self.client.post(reverse('actividades:atencion_crear'), datos)

    def test_funcionario_agrega_atencion_a_su_nombre(self):
        self.entrar('55555555-5')
        self.assertRedirects(self.agregar_atencion(), reverse('actividades:gestion_social'))
        atencion = AtencionSocial.objects.get()
        self.assertEqual((atencion.usuario, atencion.rut_solicitante, atencion.estado()), (self.func, '11222333-9', 'PENDIENTE'))
        html = self.client.get(reverse('actividades:gestion_social')).content.decode()
        self.assertIn('Registro de Atenciones', html)
        self.assertNotIn('Pestaña Personal', html)
        self.assertNotIn('1RA GESTIÓN', html)  # las acciones son las actividades vinculadas
        self.assertIn(self.func.get_full_name(), html)  # se ve quién la registró

    def test_delegado_y_coordinador_solo_visualizan(self):
        for rut in ['33333333-3', '22222222-2']:
            self.entrar(rut)
            self.assertRedirects(self.client.get(reverse('actividades:atencion_crear')), reverse('actividades:mi_gestion'))
            self.agregar_atencion()
            self.assertNotContains(self.client.get(reverse('actividades:gestion_social')),
                                   f'href="{reverse("actividades:atencion_crear")}"')
        self.assertEqual(AtencionSocial.objects.count(), 0)

    def test_delegado_ve_solo_las_de_su_delegacion(self):
        propia = self.solicitud()
        self.solicitud(usuario=self.otro, nombre='Rosa Prueba')  # Rural
        self.entrar('33333333-3')
        filas = self.client.get(reverse('actividades:gestion_social')).context['atenciones']
        self.assertEqual([f['id'] for f in filas], [propia.pk])

    def test_vincular_actividad_y_estados(self):
        solicitud = self.solicitud()
        self.entrar('77777777-7')  # un compañero de la misma delegación la puede vincular
        opciones = self.client.get(reverse('actividades:actividad_crear')).context['form'].fields['solicitud'].queryset
        self.assertEqual(list(opciones), [solicitud])
        self.registrar(solicitud=solicitud.pk)
        actividad = Actividad.objects.get()
        self.assertEqual(actividad.solicitud, solicitud)
        self.assertEqual(solicitud.estado(), 'EN_PROCESO')
        # Una solicitud puede necesitar varias actividades
        self.registrar(solicitud=solicitud.pk, accion='Visita domiciliaria',
                       fecha_realizacion=(self.hoy + timedelta(days=3)).isoformat())
        self.assertEqual(solicitud.actividades.count(), 2)
        # En la tabla de actividades dice "Ver solicitud" y lleva a la solicitud en Gestión Social
        self.assertContains(self.client.get(reverse('actividades:mi_gestion')), 'Ver solicitud')
        filas = self.client.get(reverse('actividades:gestion_social'), {'solicitud': solicitud.pk}).context['atenciones']
        self.assertEqual([(f['id'], f['estado_texto']) for f in filas], [(solicitud.pk, 'En proceso')])
        # Queda Atendida solo cuando todas sus actividades están validadas
        actividad.estado = 'VALIDADA'
        actividad.save()
        self.assertEqual(solicitud.estado(), 'EN_PROCESO')
        solicitud.actividades.update(estado='VALIDADA')
        self.assertEqual(solicitud.estado(), 'ATENDIDA')

    def test_no_se_vincula_una_solicitud_de_otra_delegacion(self):
        ajena = self.solicitud(usuario=self.otro)
        self.entrar('55555555-5')
        self.registrar(solicitud=ajena.pk)
        self.assertEqual(Actividad.objects.count(), 0)
