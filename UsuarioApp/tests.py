from datetime import timedelta
from urllib.parse import quote

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from IndicadoresApp.models import Periodo, MetaDesempeno
from UsuarioApp.funciones import limpiar_rut, validar_rut
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo

from io import StringIO
from django.core.management import call_command

CLAVE = 'Serena2026!'


def crear_datos_base():
    from ActividadesApp.models import Territorio
    for codigo in ['Admin', 'Coordinador', 'Delegado', 'Funcionario']:
        Rol.objects.create(codigo=codigo, nombre=codigo)
    call_command('crear_grupos', stdout=StringIO())
    compania = Delegacion.objects.create(nombre='LAS_COMPANIAS', nombre_visible='Las Compañías', ambito='Urbano')
    rural = Delegacion.objects.create(nombre='RURAL', nombre_visible='Rural', ambito='Rural')
    territorio = Territorio.objects.create(nombre='Sector Alto', delegacion=compania)
    Territorio.objects.create(nombre='Sector Bajo', delegacion=compania)
    Territorio.objects.create(nombre='Localidad Norte', delegacion=rural)
    item1 = Catalogo.objects.create(id=1, tipo='ITEM_GESTION', nombre='Atención de Usuario')
    Catalogo.objects.create(id=2, tipo='ITEM_GESTION', nombre='Visitas')
    Catalogo.objects.create(id=3, tipo='ITEM_GESTION', nombre='Fiscalizaciones')
    area = Catalogo.objects.create(tipo='AREA', nombre='ORG COM')
    cargo = Cargo.objects.create(codigo='TERR', nombre='Territorial', area=area)
    hoy = timezone.localdate()
    periodo = Periodo.objects.create(nombre='Prueba', fecha_inicio=hoy - timedelta(days=9), fecha_termino=hoy + timedelta(days=10), dias_computables=20)
    MetaDesempeno.objects.create(valor_objetivo=10, ponderador=100, cargo=cargo, item=item1, periodo=periodo)
    return {'delegacion': compania, 'cargo': cargo, 'periodo': periodo, 'item': item1, 'territorio': territorio}


def crear_usuario(rut, rol, delegacion=None, cargo=None):
    usuario = Usuario.objects.create_user(username=rut, password=CLAVE, email=f"{rut}@laserena.cl", first_name='Nombre', last_name=rol, delegacion=delegacion, cargo=cargo)
    UsuarioRol.objects.create(usuario=usuario, rol=Rol.objects.get(codigo=rol))
    usuario.sincronizar_grupo()
    return usuario


class RutTest(TestCase):
    def test_limpiar_rut(self):
        self.assertEqual(limpiar_rut('12.345.678-k'), '12345678-K')

    def test_validar_rut(self):
        self.assertTrue(validar_rut('11.111.111-1'))
        self.assertFalse(validar_rut('11111111-2'))


class LoginYPermisosTest(TestCase):
    def setUp(self):
        datos = crear_datos_base()
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.func = crear_usuario('55555555-5', 'Funcionario', datos['delegacion'], datos['cargo'])

    def test_login_con_rut_con_puntos(self):
        respuesta = self.client.post(reverse('users:login'), {'username': '55.555.555-5', 'password': CLAVE})
        self.assertRedirects(respuesta, reverse('actividades:mi_gestion'))

    def test_login_incorrecto_muestra_error(self):
        respuesta = self.client.post(reverse('users:login'), {'username': '55555555-5', 'password': 'mala'})
        self.assertContains(respuesta, 'Rut o contraseña incorrectos')

    def test_sin_sesion_redirige_al_login(self):
        respuesta = self.client.get(reverse('actividades:mi_gestion'))
        # @permiso_requerido agrega ?next= para volver a la pantalla después de iniciar sesión
        self.assertRedirects(respuesta, reverse('users:login') + '?next=' + quote(reverse('actividades:mi_gestion'), safe=''))

    def test_funcionario_no_entra_a_administracion(self):
        self.client.login(username='55555555-5', password=CLAVE)
        respuesta = self.client.get(reverse('users:administracion'))
        self.assertRedirects(respuesta, reverse('actividades:mi_gestion'))

    def test_admin_ve_todas_las_pantallas(self):
        self.client.login(username='11111111-1', password=CLAVE)
        for nombre in ['indicadores:dashboard', 'indicadores:semaforo', 'indicadores:resumen_delegacion','actividades:mi_gestion', 'actividades:tubo_trabajo', 'actividades:actividad_crear', 'actividades:gestion_social', 'actividades:verificacion','users:administracion', 'auditoria:logs']:
            respuesta = self.client.get(reverse(nombre))
            self.assertEqual(respuesta.status_code, 200, nombre)
        self.assertEqual(self.client.get(reverse('users:usuario_editar', args=[self.func.pk])).status_code, 200)

    def test_admin_crea_usuario_desde_modal(self):
        self.client.login(username='11111111-1', password=CLAVE)
        self.client.post(reverse('users:usuario_crear'), {
            'rut': '12.345.678-5', 'email': 'nuevo@laserena.cl', 'first_name': 'Nuevo', 'last_name': 'Usuario',
            'rol': 'Delegado', 'cargo': 'Territorial', 'password1': 'ClaveSegura#2026', 'password2': 'ClaveSegura#2026'})
        nuevo = Usuario.objects.get(username='12345678-5')
        self.assertEqual(nuevo.rol(), 'Delegado')
        self.assertEqual(nuevo.cargo.codigo, 'TERR')

    def test_styles_css_en_base(self):
        self.client.login(username='11111111-1', password=CLAVE)
        self.assertContains(self.client.get(reverse('indicadores:dashboard')), '/static/css/styles.css')


class RequisitosEvaluacionTest(TestCase):

    def test_todas_las_entidades_en_admin_con_busqueda(self):
        from django.apps import apps
        from django.contrib import admin
        propias = ['UsuarioApp', 'IndicadoresApp', 'ActividadesApp', 'AuditoriaApp']
        for modelo in apps.get_models():
            if modelo._meta.app_label in propias:
                self.assertIn(modelo, admin.site._registry, modelo.__name__)
                self.assertTrue(admin.site._registry[modelo].search_fields, modelo.__name__)

    def test_listados_tienen_botones_crud(self):
        crear_datos_base()
        crear_usuario('11111111-1', 'Admin')
        self.client.login(username='11111111-1', password=CLAVE)
        # Auditoría (solo lectura) y Verificación (solo se valida) no tienen Agregar ni Buscar
        esperados = {
            'actividades:mi_gestion': ['Agregar', 'Buscar'],
            'actividades:tubo_trabajo': ['Agregar'],      # sus filtros reemplazan a Buscar
            'actividades:gestion_social': ['Agregar', 'Buscar'],
            'indicadores:semaforo': ['Buscar'],           # sus indicadores se calculan solos (J4)
            'indicadores:resumen_delegacion': ['Agregar', 'Buscar'],
            'users:administracion': ['Agregar', 'Buscar'],
        }
        for nombre, textos in esperados.items():
            html = self.client.get(reverse(nombre)).content.decode()
            for texto in textos:
                self.assertIn(texto, html, f"{nombre}: falta {texto}")


class RolesYPermisosTest(TestCase):
    """Coordinador = administra usuarios y metas, pero solo visualiza actividades. Delegado = gestiona los
    Funcionarios de su delegación y valida sus actividades. Funcionario = registra actividades."""

    def setUp(self):
        from ActividadesApp.models import Actividad, Evidencia
        self.datos = crear_datos_base()
        compania = self.datos['delegacion']
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.admin.is_superuser = self.admin.is_staff = True
        self.admin.save()
        self.coord = crear_usuario('22222222-2', 'Coordinador')
        self.coord.sincronizar_acceso_admin()
        self.delegado = crear_usuario('33333333-3', 'Delegado', compania)
        self.delegado_rural = crear_usuario('44444444-4', 'Delegado', Delegacion.objects.get(nombre='RURAL'))
        self.func = crear_usuario('55555555-5', 'Funcionario', compania, self.datos['cargo'])
        self.func_rural = crear_usuario('88888888-8', 'Funcionario', Delegacion.objects.get(nombre='RURAL'), self.datos['cargo'])
        # Compromiso = actividad pendiente con fecha futura
        self.compromiso = Actividad.objects.create(
            solicitud_problema='Luminarias', accion='Gestión con alumbrado', item=self.datos['item'],
            periodo=self.datos['periodo'], usuario=self.func, estado='PROGRAMADA',
            fecha_realizacion=timezone.localdate() + timedelta(days=5), territorio=self.datos['territorio'])
        actividad = Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'],
                                             periodo=self.datos['periodo'], usuario=self.func)
        self.evidencia = Evidencia.objects.create(actividad=actividad, comentario='Hecho', imagen='evidencias/x.png')

    def entrar(self, rut):
        self.client.login(username=rut, password=CLAVE)

    def crear_usuario_web(self, rut, rol, delegacion='LAS_COMPANIAS', territorio=''):
        self.client.post(reverse('users:usuario_crear'), {
            'rut': rut, 'email': f'{rut}@laserena.cl', 'first_name': 'A', 'last_name': 'B', 'rol': rol,
            'cargo': 'TERR', 'delegacion': delegacion, 'territorio': territorio,
            'password1': 'ClaveSegura#2026', 'password2': 'ClaveSegura#2026'})
        return Usuario.objects.filter(username=limpiar_rut(rut)).first()

    # ----- Coordinador -----
    def test_coordinador_no_es_staff_ni_superusuario(self):
        self.coord.refresh_from_db()
        self.assertFalse(self.coord.is_staff)
        self.assertFalse(self.coord.is_superuser)

    def test_admin_crea_funcionario_con_delegacion_y_territorio(self):
        self.entrar('11111111-1')
        nuevo = self.crear_usuario_web('12.345.678-5', 'Funcionario', territorio=self.datos['territorio'].pk)
        self.assertEqual((nuevo.rol(), nuevo.delegacion, nuevo.territorio),
                         ('Funcionario', self.datos['delegacion'], self.datos['territorio']))
        # Un territorio de otra delegación no se acepta
        self.assertIsNone(self.crear_usuario_web('11.222.333-9', 'Funcionario', 'RURAL', territorio=self.datos['territorio'].pk))

    def test_coordinador_solo_visualiza_usuarios(self):
        self.entrar('22222222-2')
        respuesta = self.client.get(reverse('users:administracion'))
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.content.decode()
        self.assertEqual(respuesta.context['vista'], 'coordinador')  # su pestaña se llama Usuarios, no Gestión
        self.assertNotIn('Agregar Usuario', html)
        self.assertNotIn('Agregar delegación', html)
        self.assertIsNone(self.crear_usuario_web('12.345.678-5', 'Funcionario'))

    def test_coordinador_no_crea_coordinador_ni_admin(self):
        self.entrar('22222222-2')
        self.assertIsNone(self.crear_usuario_web('12.345.678-5', 'Coordinador'))
        self.assertIsNone(self.crear_usuario_web('12.345.678-5', 'Admin'))
        self.assertNotIn('value="Coordinador"', self.client.get(reverse('users:administracion')).content.decode())

    def test_admin_si_crea_coordinador(self):
        self.entrar('11111111-1')
        nuevo = self.crear_usuario_web('12.345.678-5', 'Coordinador', 'GENERAL')
        self.assertEqual(nuevo.rol(), 'Coordinador')
        self.assertFalse(nuevo.is_staff)  # solo visualiza: no entra a Django Admin
        self.assertIsNone(nuevo.delegacion)

    def test_coordinador_no_edita_usuarios(self):
        self.entrar('22222222-2')
        self.assertRedirects(self.client.get(reverse('users:usuario_editar', args=[self.func.pk])),
                             reverse('actividades:mi_gestion'))
        self.client.post(reverse('users:usuario_editar', args=[self.func.pk]), {
            'email': self.func.email, 'first_name': 'X', 'last_name': 'Y', 'is_active': 'on',
            'rol': 'Coordinador', 'delegacion': 'LAS_COMPANIAS'})
        self.func.refresh_from_db()
        self.assertEqual(self.func.rol(), 'Funcionario')

    def test_coordinador_no_entra_a_django_admin(self):
        self.entrar('22222222-2')
        for url in [reverse('admin:index'), reverse('admin:ActividadesApp_actividad_change', args=[self.compromiso.pk]),
                    reverse('admin:UsuarioApp_usuario_change', args=[self.func.pk])]:
            self.assertEqual(self.client.get(url).status_code, 302, url)  # manda al login de Django Admin
        # Tampoco ve botones que lleven a Django Admin
        for pantalla in ['actividades:mi_gestion', 'actividades:tubo_trabajo', 'indicadores:semaforo',
                         'indicadores:resumen_delegacion', 'auditoria:logs']:
            self.assertNotIn('/admin/', self.client.get(reverse(pantalla)).content.decode(), pantalla)

    def test_admin_si_entra_a_django_admin(self):
        self.entrar('11111111-1')
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)

    def test_funcionario_no_entra_a_django_admin(self):
        self.entrar('55555555-5')
        respuesta = self.client.get(reverse('admin:index'))
        self.assertEqual(respuesta.status_code, 302)

    # ----- Delegado: controla su delegación -----
    def datos_actividad(self, **extra):
        datos = {'solicitud_problema': 'x', 'accion': 'y', 'item': '1', 'territorio': self.datos['territorio'].pk,
                 'fecha_realizacion': timezone.localdate().isoformat(), 'comentario': 'Hecho'}
        datos.update(extra)
        return datos

    def test_delegado_y_coordinador_no_registran_actividades(self):
        from ActividadesApp.models import Actividad
        for rut in ['33333333-3', '22222222-2']:
            self.entrar(rut)
            self.assertRedirects(self.client.get(reverse('actividades:actividad_crear')), reverse('actividades:mi_gestion'))
            self.client.post(reverse('actividades:actividad_crear'), self.datos_actividad())
            self.client.post(reverse('actividades:actividad_crear'), self.datos_actividad(depende_externos='on'))
        self.assertEqual(Actividad.objects.count(), 2)  # las dos del setUp

    def test_delegado_crea_funcionarios_solo_en_su_delegacion(self):
        self.entrar('33333333-3')
        self.assertEqual(self.client.get(reverse('users:administracion')).status_code, 200)
        nuevo = self.crear_usuario_web('12.345.678-5', 'Funcionario', 'RURAL')  # pide otra delegación
        self.assertEqual((nuevo.rol(), nuevo.delegacion), ('Funcionario', self.datos['delegacion']))
        self.assertIsNone(self.crear_usuario_web('11.222.333-9', 'Delegado'))

    def test_delegado_lista_y_edita_solo_su_delegacion(self):
        self.entrar('33333333-3')
        lista = self.client.get(reverse('users:administracion')).context['lista_usuarios']
        self.assertEqual([u.pk for u in lista], [self.func.pk])
        self.assertRedirects(self.client.get(reverse('users:usuario_editar', args=[self.func_rural.pk])),
                             reverse('users:administracion'))
        self.assertRedirects(self.client.get(reverse('users:usuario_editar', args=[self.delegado_rural.pk])),
                             reverse('users:administracion'))
        self.assertEqual(self.client.get(reverse('users:usuario_editar', args=[self.func.pk])).status_code, 200)
        # Un POST directo sobre un Funcionario de otra delegación tampoco lo cambia
        self.client.post(reverse('users:usuario_editar', args=[self.func_rural.pk]), {
            'email': self.func_rural.email, 'first_name': 'Cambiado', 'last_name': 'Y', 'is_active': 'on',
            'rol': 'Funcionario', 'delegacion': 'LAS_COMPANIAS'})
        self.func_rural.refresh_from_db()
        self.assertNotEqual(self.func_rural.first_name, 'Cambiado')
        self.assertEqual(self.func_rural.delegacion.nombre, 'RURAL')

    def test_delegado_desactiva_funcionario_de_su_delegacion(self):
        self.entrar('33333333-3')
        self.client.post(reverse('users:usuario_desactivar', args=[self.func.pk]))
        self.client.post(reverse('users:usuario_desactivar', args=[self.func_rural.pk]))
        self.client.post(reverse('users:usuario_desactivar', args=[self.delegado.pk]))  # a sí mismo no
        self.func.refresh_from_db()
        self.func_rural.refresh_from_db()
        self.delegado.refresh_from_db()
        self.assertEqual((self.func.is_active, self.func_rural.is_active, self.delegado.is_active), (False, True, True))
        self.client.post(reverse('users:usuario_desactivar', args=[self.func.pk]))  # vuelve a activarlo
        self.func.refresh_from_db()
        self.assertTrue(self.func.is_active)

    def test_delegado_ve_usuarios_y_metas_sin_logs(self):
        self.entrar('33333333-3')
        html = self.client.get(reverse('users:administracion')).content.decode()
        self.assertIn('id="goals"', html)
        self.assertNotIn('id="audit"', html)
        self.assertNotIn('Logs de Trazabilidad', html)
        self.assertNotIn('apartado-delegaciones', html)  # el Delegado no ve el apartado de delegaciones
        self.assertIn('Mi Delegación', html)

    def test_delegado_verifica_solo_su_delegacion(self):
        url = reverse('actividades:validar_evidencia', args=[self.evidencia.pk])
        self.entrar('44444444-4')  # Delegado Rural
        self.assertEqual(self.client.get(reverse('actividades:verificacion')).context['evidencias_pendientes'], [])
        self.client.post(url, {'decision': 'APROBAR'})
        self.evidencia.refresh_from_db()
        self.assertEqual(self.evidencia.estado_revision, 'PENDIENTE')
        self.entrar('33333333-3')  # Delegado Las Compañías
        self.assertEqual(len(self.client.get(reverse('actividades:verificacion')).context['evidencias_pendientes']), 1)
        self.client.post(url, {'decision': 'APROBAR'})
        self.evidencia.refresh_from_db()
        self.assertEqual(self.evidencia.estado_revision, 'APROBADA')

    def test_delegado_ve_semaforo_y_verificacion(self):
        self.entrar('33333333-3')
        html = self.client.get(reverse('indicadores:dashboard')).content.decode()
        self.assertIn(reverse('actividades:verificacion'), html)
        self.assertIn(reverse('indicadores:semaforo'), html)
        self.assertEqual(self.client.get(reverse('indicadores:semaforo')).status_code, 200)

    # ----- Funcionario -----
    def test_funcionario_registra_pero_no_modifica_ni_verifica(self):
        self.entrar('55555555-5')
        html = self.client.get(reverse('actividades:mi_gestion')).content.decode()
        self.assertNotIn(reverse('admin:ActividadesApp_actividad_changelist') + '1/change/', html)
        self.assertIn(reverse('actividades:actividad_crear'), html)
        self.assertRedirects(self.client.get(reverse('actividades:verificacion')), reverse('actividades:mi_gestion'))

    def test_rol_consulta_ya_no_existe(self):
        self.assertFalse(Rol.objects.filter(codigo='Consulta').exists())
        self.entrar('11111111-1')
        self.assertNotIn('value="Consulta"', self.client.get(reverse('users:administracion')).content.decode())

    def test_coordinador_solo_visualiza_actividades(self):
        self.entrar('22222222-2')
        detalle = self.client.get(reverse('actividades:actividad_detalle', args=[self.compromiso.pk]))
        self.assertEqual(detalle.status_code, 200)
        self.assertFalse(detalle.context['puede_ejecutar'])
        self.assertFalse(detalle.context['puede_comentar'])
        self.assertFalse(detalle.context['puede_programar'])
        self.assertTrue(detalle.context['puede_asignar'])  # sí asigna encargado
        self.assertRedirects(self.client.get(reverse('actividades:verificacion')), reverse('actividades:mi_gestion'))

    # ----- Metas (Admin y Coordinador) -----
    def guardar_meta(self, item_id, ponderador):
        return self.client.post(reverse('indicadores:guardar_metas'), {
            'cargo': self.datos['cargo'].pk, 'item': item_id, 'valor_objetivo': '10', 'ponderador': ponderador})

    def test_ponderadores_validados(self):
        self.entrar('11111111-1')
        self.assertEqual(self.guardar_meta(2, 'abc').status_code, 302)  # no es número: no rompe
        self.guardar_meta(2, '10')  # 100 + 10 supera 100%
        self.assertEqual(MetaDesempeno.objects.count(), 1)
        self.guardar_meta(1, '60')
        self.assertFalse(self.datos['cargo'].validar_ponderadores(self.datos['periodo']))
        self.guardar_meta(2, '40')
        self.assertTrue(self.datos['cargo'].validar_ponderadores(self.datos['periodo']))


class MetasYFechasInlineTest(TestCase):
    """Formulario de metas del panel de administración."""

    def setUp(self):
        self.datos = crear_datos_base()
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.admin.sincronizar_acceso_admin()
        self.coord = crear_usuario('22222222-2', 'Coordinador')
        self.coord.sincronizar_acceso_admin()

    def test_formulario_de_metas_completo(self):
        self.client.login(username='11111111-1', password=CLAVE)
        html = self.client.get(reverse('users:administracion')).content.decode()
        for campo in ['name="cargo"', 'name="item"', 'name="valor_objetivo"', 'name="ponderador"', 'Guardar meta']:
            self.assertIn(campo, html)
        self.assertIn('Total 100', html)  # la meta de crear_datos_base aparece con su total

    def test_guardar_meta_vuelve_a_la_pestana(self):
        self.client.login(username='11111111-1', password=CLAVE)
        MetaDesempeno.objects.all().delete()
        respuesta = self.client.post(reverse('indicadores:guardar_metas'), {
            'cargo': self.datos['cargo'].pk, 'item': 2, 'valor_objetivo': '30', 'ponderador': '40'})
        # Meta general: vuelve a Metas con el selector en GENERAL, para que se vea lo que se guardó
        self.assertEqual(respuesta['Location'], reverse('users:administracion') + '?pestana=metas&delegacion=GENERAL#goals')
        meta = MetaDesempeno.objects.get()
        self.assertEqual((meta.valor_objetivo, meta.ponderador), (30, 40))
        # Valores que no son número no provocan error 500
        respuesta = self.client.post(reverse('indicadores:guardar_metas'), {'cargo': 'x', 'item': 'y', 'valor_objetivo': '1', 'ponderador': '1'})
        self.assertEqual(respuesta.status_code, 302)


class BotonesSegunRolTest(TestCase):
    """Los botones solo se muestran a quien puede usarlos."""

    def setUp(self):
        from ActividadesApp.models import Actividad
        from AuditoriaApp.registro import registrar_auditoria
        self.datos = crear_datos_base()
        compania = self.datos['delegacion']
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.coord = crear_usuario('22222222-2', 'Coordinador')
        crear_usuario('33333333-3', 'Delegado', compania)
        self.func = crear_usuario('55555555-5', 'Funcionario', compania, self.datos['cargo'])
        Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'],
                                 periodo=self.datos['periodo'], usuario=self.func)
        registrar_auditoria(self.func, 'CREACION', 'Actividad', 1, '', 'x')

    def html(self, rut, nombre):
        self.client.login(username=rut, password=CLAVE)
        return self.client.get(reverse(nombre)).content.decode()

    def test_funcionario_solo_ve_agregar_actividad(self):
        html = self.html('55555555-5', 'actividades:mi_gestion')
        self.assertEqual(html.count('Agregar Actividad'), 1)   # solo en "Ingreso Diario"
        for texto in ['Modificar', 'Eliminar', 'Buscar', 'Agregar Meta']:
            self.assertNotIn(texto, html)

    def test_delegado_no_ve_botones_crud(self):
        for rut, pantalla in [('33333333-3', 'actividades:mi_gestion'), ('33333333-3', 'actividades:verificacion'),
                              ('33333333-3', 'actividades:tubo_trabajo')]:
            html = self.html(rut, pantalla)
            for texto in ['Agregar', 'Modificar', 'Eliminar', 'Buscar']:
                self.assertNotIn(texto, html, f"{pantalla}: {texto}")
        # Semáforo y Resumen (J4): el Delegado gestiona su equipo y sus metas desde pantallas propias, nunca /admin/
        for pantalla in ['indicadores:semaforo', 'indicadores:resumen_delegacion']:
            self.assertNotIn('/admin/', self.html('33333333-3', pantalla), pantalla)

    def test_admin_ve_todo_y_actividades_registradas_no_duplica_agregar(self):
        html = self.html('11111111-1', 'actividades:mi_gestion')
        self.assertEqual(html.count('Agregar Actividad'), 1)
        self.assertIn('Modificar', html)

    def test_auditoria_es_solo_lectura(self):
        # Ningún rol, ni el Administrador, agrega, modifica o elimina registros de auditoría
        for rut in ['22222222-2', '11111111-1']:
            html = self.html(rut, 'auditoria:logs')
            for texto in ['Agregar', 'Modificar', 'Eliminar']:
                self.assertNotIn(texto, html, rut)


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class PerfilTest(TestCase):
    """Cada usuario edita su foto, teléfono y correo desde su perfil (Mi Gestión)."""

    def setUp(self):
        datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', datos['delegacion'], datos['cargo'])
        crear_usuario('77777777-7', 'Funcionario', datos['delegacion'], datos['cargo'])
        self.client.login(username='55555555-5', password=CLAVE)

    def guardar(self, **extra):
        datos = {'email': self.func.email, 'telefono': '912345678'}
        datos.update(extra)
        return self.client.post(reverse('users:perfil_editar'), datos)

    def test_edita_telefono_y_foto(self):
        from ActividadesApp.tests import foto
        self.assertRedirects(self.guardar(foto=foto()), reverse('actividades:mi_gestion'))
        self.func.refresh_from_db()
        self.assertEqual(self.func.telefono, '912345678')
        self.assertTrue(self.func.foto.name.startswith('perfiles/'))
        html = self.client.get(reverse('actividades:mi_gestion')).content.decode()
        self.assertIn(self.func.foto.url, html)
        self.assertIn('912345678', html)
        # Quitar la foto
        self.guardar(quitar_foto='on')
        self.func.refresh_from_db()
        self.assertFalse(self.func.foto)

    def test_rechaza_correo_repetido_y_foto_no_imagen(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.assertEqual(self.guardar(email='77777777-7@laserena.cl').status_code, 200)
        self.assertEqual(self.guardar(foto=SimpleUploadedFile('foto.gif', b'GIF89a')).status_code, 200)
        self.func.refresh_from_db()
        self.assertEqual((self.func.email, self.func.foto.name), ('55555555-5@laserena.cl', ''))


class MetasPorDelegacionTest(TestCase):
    """Metas generales (solo el Admin) y metas propias de cada delegación (Admin o su Delegado).
    El Coordinador solo las visualiza."""

    def setUp(self):
        self.datos = crear_datos_base()  # meta general: ítem 1, 10 actividades, 100 %
        self.compania = self.datos['delegacion']
        self.rural = Delegacion.objects.get(nombre='RURAL')
        crear_usuario('11111111-1', 'Admin')
        crear_usuario('22222222-2', 'Coordinador')
        crear_usuario('33333333-3', 'Delegado', self.compania)
        self.func = crear_usuario('55555555-5', 'Funcionario', self.compania, self.datos['cargo'])
        self.func_rural = crear_usuario('88888888-8', 'Funcionario', self.rural, self.datos['cargo'])

    def guardar(self, rut, alcance, item=2, valor='20', ponderador='100'):
        self.client.login(username=rut, password=CLAVE)
        return self.client.post(reverse('indicadores:guardar_metas'), {
            'alcance': alcance, 'cargo': self.datos['cargo'].pk, 'item': item,
            'valor_objetivo': valor, 'ponderador': ponderador})

    def test_coordinador_filtra_metas_con_el_selector_de_delegacion(self):
        self.guardar('11111111-1', 'LAS_COMPANIAS')  # meta propia de Las Compañías (ítem 2)
        self.client.login(username='22222222-2', password=CLAVE)
        url = reverse('users:administracion')

        def alcances(respuesta):
            return [grupo['nombre'] for grupo in respuesta.context['metas_agrupadas']]

        general = self.client.get(url, {'pestana': 'metas'})  # sin selector = GENERAL
        self.assertEqual(alcances(general), ['General (toda la municipalidad)'])
        self.assertEqual(general.context['aviso_metas'], '')
        compania = self.client.get(url, {'pestana': 'metas', 'delegacion': 'LAS_COMPANIAS'})
        self.assertEqual(alcances(compania), ['Las Compañías'])
        self.assertEqual(compania.context['pestana'], 'metas')  # vuelve a la pestaña Metas
        # Rural no tiene metas propias: aviso y las generales, que son las que se le aplican
        rural = self.client.get(url, {'pestana': 'metas', 'delegacion': 'RURAL'})
        self.assertEqual(alcances(rural), ['General (toda la municipalidad)'])
        self.assertIn('Rural no tiene metas propias', rural.context['aviso_metas'])

    def test_admin_filtra_metas_con_el_selector_de_delegacion(self):
        self.guardar('11111111-1', 'LAS_COMPANIAS')
        url = reverse('users:administracion')
        nombres = lambda r: [grupo['nombre'] for grupo in r.context['metas_agrupadas']]
        self.assertEqual(nombres(self.client.get(url)), ['General (toda la municipalidad)'])
        self.assertEqual(nombres(self.client.get(url, {'delegacion': 'LAS_COMPANIAS'})), ['Las Compañías'])

    def test_delegado_elige_entre_general_y_su_delegacion(self):
        self.guardar('11111111-1', 'LAS_COMPANIAS')
        self.client.login(username='33333333-3', password=CLAVE)
        url = reverse('users:administracion')
        nombres = lambda r: [grupo['nombre'] for grupo in r.context['metas_agrupadas']]
        propia = self.client.get(url)  # por defecto, su delegación
        self.assertEqual(nombres(propia), ['Las Compañías'])
        self.assertEqual([valor for valor, texto in propia.context['delegaciones_navbar']], ['GENERAL', 'LAS_COMPANIAS'])
        self.assertEqual(nombres(self.client.get(url, {'delegacion': 'GENERAL'})), ['General (toda la municipalidad)'])
        # Otra delegación no se puede ver: se queda en la suya
        self.assertEqual(nombres(self.client.get(url, {'delegacion': 'RURAL'})), ['Las Compañías'])
        # Fuera de Administración no tiene selector
        self.assertNotIn('delegaciones_navbar', self.client.get(reverse('actividades:mi_gestion')).context)

    def test_buscador_de_metas_por_cargo_o_item(self):
        MetaDesempeno.objects.create(valor_objetivo=5, ponderador=0, cargo=self.datos['cargo'],
                                     item=Catalogo.objects.get(id=2), periodo=self.datos['periodo'])  # general: Visitas
        self.client.login(username='11111111-1', password=CLAVE)
        url = reverse('users:administracion')
        items = lambda r: [m.item.nombre for g in r.context['metas_agrupadas'] for b in g['cargos'] for m in b['metas']]
        self.assertEqual(sorted(items(self.client.get(url, {'pestana': 'metas'}))), ['Atención de Usuario', 'Visitas'])
        self.assertEqual(items(self.client.get(url, {'pestana': 'metas', 'q_meta': 'visit'})), ['Visitas'])
        self.assertEqual(len(items(self.client.get(url, {'pestana': 'metas', 'q_meta': 'territorial'}))), 2)  # por cargo
        vacio = self.client.get(url, {'pestana': 'metas', 'q_meta': 'zzz'})
        self.assertEqual(vacio.context['metas_agrupadas'], [])
        self.assertContains(vacio, 'Ninguna meta coincide con')
        # Con una delegación sin coincidencias no aparece el aviso de "no tiene metas propias"
        self.guardar('11111111-1', 'LAS_COMPANIAS')
        compania = self.client.get(url, {'pestana': 'metas', 'delegacion': 'LAS_COMPANIAS', 'q_meta': 'zzz'})
        self.assertEqual(compania.context['aviso_metas'], '')

    def test_buscador_de_delegaciones(self):
        self.client.login(username='11111111-1', password=CLAVE)
        url = reverse('users:administracion')
        nombres = lambda r: [str(item['delegacion']) for item in r.context['delegaciones']]
        self.assertEqual(nombres(self.client.get(url)), ['Las Compañías', 'Rural'])
        self.assertEqual(nombres(self.client.get(url, {'q_delegacion': 'compa'})), ['Las Compañías'])
        self.assertEqual(nombres(self.client.get(url, {'q_delegacion': 'norte'})), ['Rural'])  # por territorio
        self.assertEqual(nombres(self.client.get(url, {'q_delegacion': 'rural'})), ['Rural'])  # por ámbito o nombre
        self.assertContains(self.client.get(url, {'q_delegacion': 'zzz'}), 'Ninguna delegación coincide con')

    def test_al_guardar_meta_vuelve_filtrado_en_su_delegacion(self):
        respuesta = self.guardar('11111111-1', 'LAS_COMPANIAS')
        self.assertEqual(respuesta.url, reverse('users:administracion') + '?pestana=metas&delegacion=LAS_COMPANIAS#goals')

    def test_delegado_define_metas_solo_de_su_delegacion(self):
        from IndicadoresApp.calculos import indicadores_usuario
        self.guardar('33333333-3', 'GENERAL')  # pide general: se le impone su delegación (la elección no es válida)
        self.guardar('33333333-3', 'LAS_COMPANIAS')
        propias = MetaDesempeno.objects.filter(delegacion=self.compania)
        self.assertEqual(propias.count(), 1)
        self.assertEqual(MetaDesempeno.objects.filter(delegacion__isnull=True).count(), 1)  # la general sigue igual
        # La meta propia reemplaza a la general en Las Compañías; Rural sigue con la general
        hoy = timezone.localdate()
        self.assertEqual([i.meta.item_id for i in indicadores_usuario(self.func, self.datos['periodo'], hoy)], [2])
        self.assertEqual([i.meta.item_id for i in indicadores_usuario(self.func_rural, self.datos['periodo'], hoy)], [1])

    def test_delegado_no_edita_metas_generales_y_admin_si(self):
        general = MetaDesempeno.objects.get()
        self.client.login(username='33333333-3', password=CLAVE)
        self.client.post(reverse('indicadores:meta_editar', args=[general.pk]), {'valor_objetivo': '99', 'ponderador': '100'})
        general.refresh_from_db()
        self.assertEqual(general.valor_objetivo, 10)
        self.client.login(username='11111111-1', password=CLAVE)
        self.assertEqual(self.client.get(reverse('indicadores:meta_editar', args=[general.pk])).status_code, 200)
        self.client.post(reverse('indicadores:meta_editar', args=[general.pk]), {'valor_objetivo': '15', 'ponderador': '100'})
        general.refresh_from_db()
        self.assertEqual(general.valor_objetivo, 15)
        self.client.post(reverse('indicadores:meta_eliminar', args=[general.pk]))
        self.assertFalse(MetaDesempeno.objects.exists())

    def test_coordinador_solo_visualiza_metas(self):
        self.guardar('22222222-2', 'GENERAL')
        self.assertEqual(MetaDesempeno.objects.count(), 1)
        html = self.client.get(reverse('users:administracion')).content.decode()
        self.assertIn('Vista de consulta', html)
        self.assertNotIn('Guardar meta', html)

    def test_admin_define_meta_para_una_delegacion(self):
        self.guardar('11111111-1', 'RURAL')
        self.assertTrue(MetaDesempeno.objects.filter(delegacion=self.rural).exists())


class GestionDelegacionesYUsuariosTest(TestCase):
    """Administración > Gestión: delegaciones con sus territorios y usuarios con filtros (solo el Admin modifica)."""

    def setUp(self):
        from ActividadesApp.models import Territorio
        self.datos = crear_datos_base()
        self.compania = self.datos['delegacion']
        self.alto = self.datos['territorio']
        self.bajo = Territorio.objects.get(nombre='Sector Bajo')
        self.admin = crear_usuario('11111111-1', 'Admin')
        crear_usuario('22222222-2', 'Coordinador')
        self.delegado = crear_usuario('33333333-3', 'Delegado', self.compania)
        self.func = crear_usuario('55555555-5', 'Funcionario', self.compania, self.datos['cargo'])
        self.func.territorio = self.alto
        self.func.save()
        self.otro = crear_usuario('77777777-7', 'Funcionario', self.compania, self.datos['cargo'])
        self.otro.territorio = self.bajo
        self.otro.save()

    def entrar(self, rut):
        self.client.login(username=rut, password=CLAVE)

    def test_admin_agrega_delegacion_con_territorios(self):
        self.entrar('11111111-1')
        self.client.post(reverse('users:delegacion_crear'), {
            'nombre_visible': 'La Florida', 'ambito': 'Urbano', 'estado': 'ACTIVO',
            'territorios-TOTAL_FORMS': '2', 'territorios-INITIAL_FORMS': '0',
            'territorios-MIN_NUM_FORMS': '0', 'territorios-MAX_NUM_FORMS': '1000',
            'territorios-0-nombre': 'Villa Nueva', 'territorios-0-estado': 'ACTIVO',
            'territorios-1-nombre': '', 'territorios-1-estado': 'ACTIVO'})
        nueva = Delegacion.objects.get(nombre='LA_FLORIDA')
        self.assertEqual((str(nueva), list(nueva.territorios.values_list('nombre', flat=True))), ('La Florida', ['Villa Nueva']))
        # Aparece en el selector de delegación de la barra superior
        self.assertIn('LA_FLORIDA', self.client.get(reverse('actividades:mi_gestion')).content.decode())

    def test_delegacion_con_usuarios_no_se_elimina(self):
        self.entrar('11111111-1')
        self.client.post(reverse('users:delegacion_eliminar', args=[self.compania.pk]))
        self.assertTrue(Delegacion.objects.filter(pk=self.compania.pk).exists())

    def test_coordinador_y_delegado_no_modifican_delegaciones(self):
        for rut in ['22222222-2', '33333333-3']:
            self.entrar(rut)
            self.assertRedirects(self.client.get(reverse('users:delegacion_crear')), reverse('actividades:mi_gestion'))

    def test_apartado_delegaciones_muestra_delegado_territorios_y_funcionarios(self):
        self.entrar('11111111-1')
        delegaciones = self.client.get(reverse('users:administracion')).context['delegaciones']
        compania = [d for d in delegaciones if d['delegacion'] == self.compania][0]
        self.assertEqual(compania['delegados'], [self.delegado])
        por_territorio = {b['territorio'].nombre: b['funcionarios'] for b in compania['territorios']}
        self.assertEqual(por_territorio['Sector Alto'], [self.func])
        self.assertEqual(por_territorio['Sector Bajo'], [self.otro])

    def test_filtros_de_usuarios(self):
        self.entrar('11111111-1')
        lista = self.client.get(reverse('users:administracion'), {'territorio': self.alto.pk}).context['lista_usuarios']
        self.assertEqual(lista, [self.func])
        lista = self.client.get(reverse('users:administracion'), {'f_delegacion': 'RURAL'}).context['lista_usuarios']
        self.assertEqual(lista, [])
        # El Delegado solo filtra por territorio (los otros filtros se ignoran) y solo ve sus Funcionarios
        self.entrar('33333333-3')
        lista = self.client.get(reverse('users:administracion'), {'territorio': self.bajo.pk, 'f_delegacion': 'RURAL'}).context['lista_usuarios']
        self.assertEqual(lista, [self.otro])

    def test_admin_elimina_usuario_sin_registros_y_no_uno_con_actividades(self):
        from ActividadesApp.models import Actividad
        Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'], periodo=self.datos['periodo'], usuario=self.func)
        self.entrar('11111111-1')
        self.client.post(reverse('users:usuario_eliminar', args=[self.otro.pk]))
        self.client.post(reverse('users:usuario_eliminar', args=[self.func.pk]))
        self.assertFalse(Usuario.objects.filter(pk=self.otro.pk).exists())
        self.assertTrue(Usuario.objects.filter(pk=self.func.pk).exists())  # tiene actividades: se desactiva, no se borra
        html = self.client.get(reverse('users:administracion'), {'pestana': 'usuarios'}).content.decode()
        self.assertIn('data-confirmar=', html)  # el botón Eliminar pide confirmación (SweetAlert)

    def test_solo_el_admin_elimina(self):
        self.entrar('33333333-3')
        self.client.post(reverse('users:usuario_eliminar', args=[self.otro.pk]))
        self.assertTrue(Usuario.objects.filter(pk=self.otro.pk).exists())


class PantallasVariasTest(TestCase):
    def setUp(self):
        datos = crear_datos_base()
        crear_usuario('11111111-1', 'Admin')
        self.client.login(username='11111111-1', password=CLAVE)

    def test_auditoria_tiene_un_solo_titulo(self):
        html = self.client.get(reverse('auditoria:logs')).content.decode()
        self.assertEqual(html.count('Auditoría de Registros'), 2)  # <title> y el encabezado
        self.assertNotIn('Registros de Auditoría y Cambios', html)

    def test_semaforo_tiene_icono_en_la_barra(self):
        self.assertIn('bi-stoplights', self.client.get(reverse('actividades:mi_gestion')).content.decode())

class GruposYPermisosTest(TestCase):
    """J1: cada rol queda en su grupo de Django y hereda sus permisos."""

    def setUp(self):
        self.datos = crear_datos_base()
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.coord = crear_usuario('22222222-2', 'Coordinador')
        self.delegado = crear_usuario('33333333-3', 'Delegado', self.datos['delegacion'])
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])

    def test_cuatro_grupos_y_cada_usuario_en_el_suyo(self):
        from django.contrib.auth.models import Group
        self.assertEqual(sorted(Group.objects.values_list('name', flat=True)), ['Administrador', 'Administrativo', 'Delegado', 'Supervisor'])
        for usuario, grupo in [(self.admin, 'Administrador'), (self.coord, 'Supervisor'), (self.delegado, 'Delegado'), (self.func, 'Administrativo')]:
            self.assertEqual(list(usuario.groups.values_list('name', flat=True)), [grupo])

    def test_permisos_heredados_del_grupo(self):
        coord = Usuario.objects.get(pk=self.coord.pk)  # se recarga: Django guarda en caché los permisos
        func = Usuario.objects.get(pk=self.func.pk)
        delegado = Usuario.objects.get(pk=self.delegado.pk)
        self.assertTrue(coord.has_perm('UsuarioApp.view_usuario'))
        self.assertFalse(coord.has_perm('UsuarioApp.change_usuario'))  # el Supervisor solo visualiza
        self.assertTrue(func.has_perm('ActividadesApp.add_actividad'))
        self.assertFalse(func.has_perm('UsuarioApp.view_usuario'))
        self.assertTrue(delegado.has_perm('IndicadoresApp.change_metadesempeno'))
        self.assertFalse(delegado.has_perm('UsuarioApp.delete_usuario'))

    def test_crear_usuario_desde_la_pantalla_le_asigna_grupo(self):
        self.client.login(username='11111111-1', password=CLAVE)
        self.client.post(reverse('users:usuario_crear'), {
            'rut': '12.345.678-5', 'email': 'nuevo@laserena.cl', 'first_name': 'A', 'last_name': 'B',
            'rol': 'Coordinador', 'cargo': 'TERR', 'delegacion': 'GENERAL', 'territorio': '',
            'password1': 'ClaveSegura#2026', 'password2': 'ClaveSegura#2026'})
        nuevo = Usuario.objects.get(username='12345678-5')
        self.assertEqual(list(nuevo.groups.values_list('name', flat=True)), ['Supervisor'])

    def test_comando_es_repetible(self):
        from django.contrib.auth.models import Group
        salida = StringIO()
        call_command('crear_grupos', stdout=salida)
        call_command('crear_grupos', stdout=salida)
        self.assertIn('Grupos listos', salida.getvalue())
        self.assertEqual(Group.objects.count(), 4)
        self.assertEqual(self.func.groups.count(), 1)

    def test_decorador_permiso_requerido(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.auth.models import AnonymousUser
        from UsuarioApp.funciones import permiso_requerido

        @permiso_requerido('UsuarioApp.view_usuario', 'Usuarios')
        def vista(request):
            return HttpResponse('ok')

        def pedir(usuario):
            request = RequestFactory().get('/usuarios/')
            request.user = usuario
            request.session = {}
            request._messages = FallbackStorage(request)
            return vista(request)

        self.assertEqual(pedir(Usuario.objects.get(pk=self.coord.pk)).content, b'ok')
        negado = pedir(Usuario.objects.get(pk=self.func.pk))
        self.assertEqual(negado['Location'], reverse('actividades:mi_gestion'))
        self.assertIn('/login', pedir(AnonymousUser())['Location'].lower())


class ProteccionVistasTest(TestCase):
    """J2: toda vista de UsuarioApp e IndicadoresApp pide sesión y, si corresponde, el permiso del grupo."""

    def setUp(self):
        self.datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        self.coord = crear_usuario('22222222-2', 'Coordinador')

    def test_sin_sesion_todas_mandan_al_login(self):
        meta = MetaDesempeno.objects.first()
        urls = [reverse('users:administracion'), reverse('users:usuario_crear'),
                reverse('users:usuario_editar', args=[self.func.pk]),
                reverse('users:usuario_desactivar', args=[self.func.pk]),
                reverse('users:usuario_eliminar', args=[self.func.pk]),
                reverse('users:delegacion_crear'),
                reverse('users:delegacion_editar', args=[self.datos['delegacion'].pk]),
                reverse('users:delegacion_eliminar', args=[self.datos['delegacion'].pk]),
                reverse('users:perfil_editar'), reverse('indicadores:dashboard'), reverse('indicadores:semaforo'),
                reverse('indicadores:resumen_delegacion'), reverse('indicadores:guardar_metas'),
                reverse('indicadores:meta_editar', args=[meta.pk]), reverse('indicadores:meta_eliminar', args=[meta.pk])]
        for url in urls:
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 302, url)
            self.assertTrue(respuesta['Location'].startswith(reverse('users:login')), url)

    def test_sin_permiso_vuelve_a_mi_gestion(self):
        self.client.login(username='55555555-5', password=CLAVE)  # Administrativo: no ve usuarios ni metas
        for nombre in ['users:administracion', 'indicadores:semaforo', 'indicadores:resumen_delegacion']:
            self.assertRedirects(self.client.get(reverse(nombre)), reverse('actividades:mi_gestion'), msg_prefix=nombre)
        self.client.login(username='22222222-2', password=CLAVE)  # Supervisor: ve, pero no crea
        self.assertEqual(self.client.get(reverse('users:administracion')).status_code, 200)
        self.assertRedirects(self.client.get(reverse('users:usuario_crear')), reverse('actividades:mi_gestion'))


class RecuperacionContrasenaTest(TestCase):
    """J3: recuperar la contraseña por correo con las vistas de Django."""

    def setUp(self):
        crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario')

    def test_flujo_completo(self):
        from django.core import mail
        self.assertContains(self.client.get(reverse('users:login')), reverse('users:recuperar'))
        respuesta = self.client.post(reverse('users:recuperar'), {'email': self.func.email})
        self.assertRedirects(respuesta, reverse('users:recuperar_enviado'))
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, [self.func.email])
        # El enlace del correo lleva uid y token; Django lo cambia por una dirección sin el token y pide la clave nueva
        enlace = [linea for linea in correo.body.splitlines() if '/usuarios/recuperar/' in linea][0].strip()
        ruta = enlace.split('testserver', 1)[1]
        formulario = self.client.get(ruta, follow=True)
        self.assertTrue(formulario.context['validlink'])
        url_formulario = formulario.redirect_chain[-1][0]
        respuesta = self.client.post(url_formulario, {'new_password1': 'NuevaClave#2026', 'new_password2': 'NuevaClave#2026'})
        self.assertRedirects(respuesta, reverse('users:recuperar_listo'))
        self.assertTrue(self.client.login(username='55555555-5', password='NuevaClave#2026'))
        # El enlace es de un solo uso
        self.client.logout()
        self.assertFalse(self.client.get(ruta, follow=True).context['validlink'])

    def test_correo_inexistente_no_revela_nada(self):
        from django.core import mail
        respuesta = self.client.post(reverse('users:recuperar'), {'email': 'nadie@laserena.cl'})
        self.assertRedirects(respuesta, reverse('users:recuperar_enviado'))
        self.assertEqual(len(mail.outbox), 0)


class ResumenSinDjangoAdminTest(TestCase):
    """J4: Resumen y Semáforo usan pantallas propias."""

    def setUp(self):
        self.datos = crear_datos_base()
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        self.client.login(username='11111111-1', password=CLAVE)

    def test_resumen_apunta_a_pantallas_propias(self):
        meta = MetaDesempeno.objects.first()
        html = self.client.get(reverse('indicadores:resumen_delegacion')).content.decode()
        self.assertNotIn('/admin/', html)
        for url in [reverse('users:administracion') + '?pestana=metas', reverse('indicadores:meta_editar', args=[meta.pk]),
                    reverse('indicadores:meta_eliminar', args=[meta.pk]), reverse('users:usuario_editar', args=[self.func.pk]),
                    reverse('users:usuario_eliminar', args=[self.func.pk])]:
            self.assertIn(url, html)
        self.assertIn('data-confirmar', html)

    def test_semaforo_sin_admin_y_con_buscador(self):
        html = self.client.get(reverse('indicadores:semaforo')).content.decode()
        self.assertNotIn('/admin/', html)
        self.assertNotIn('Agregar', html)
        filas = self.client.get(reverse('indicadores:semaforo'), {'q': 'zzz'}).context['seguimiento']
        self.assertEqual(filas, [])
        filas = self.client.get(reverse('indicadores:semaforo'), {'q': '55555555'}).context['seguimiento']
        self.assertEqual(len(filas), 1)


class TableroPorPerfilTest(TestCase):
    """J5: cada grupo ve un tablero distinto."""

    def setUp(self):
        self.datos = crear_datos_base()
        crear_usuario('11111111-1', 'Admin')
        crear_usuario('22222222-2', 'Coordinador')
        crear_usuario('33333333-3', 'Delegado', self.datos['delegacion'])
        crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])

    def tablero(self, rut):
        self.client.login(username=rut, password=CLAVE)
        return self.client.get(reverse('indicadores:dashboard'))

    def test_plantilla_segun_grupo(self):
        for rut, plantilla in [('11111111-1', 'indicadores/dashboard_admin.html'), ('22222222-2', 'indicadores/dashboard_coordinador.html'), ('33333333-3', 'indicadores/dashboard_delegado.html'), ('55555555-5', 'indicadores/dashboard_administrativo.html')]:
            self.assertTemplateUsed(self.tablero(rut), plantilla)

    def test_coordinador_compara_delegaciones(self):
        respuesta = self.tablero('22222222-2')
        filas = respuesta.context['delegaciones']
        self.assertEqual([str(fila['delegacion']) for fila in filas], ['Las Compañías', 'Rural'])
        self.assertEqual(filas[0]['responsables'], 1)  # el Funcionario con cargo de Las Compañías
        html = respuesta.content.decode()
        self.assertIn(reverse('indicadores:semaforo') + '?delegacion=RURAL', html)
        self.assertNotIn('/admin/', html)
        # El selector de la barra filtra las tarjetas de arriba; la tabla sigue mostrando todas
        rural = self.client.get(reverse('indicadores:dashboard'), {'delegacion': 'RURAL'})
        self.assertEqual(rural.context['delegacion_actual'], 'Delegación Rural')
        self.assertEqual(len(rural.context['delegaciones']), 2)
        self.assertEqual(respuesta.context['delegacion_actual'], 'Toda la municipalidad')

    def test_accesos_segun_permisos(self):
        html = self.tablero('11111111-1').content.decode()
        for url in [reverse('users:administracion') + '?pestana=usuarios', reverse('users:administracion') + '?pestana=metas',
                    reverse('actividades:gestion_social'), reverse('auditoria:logs')]:
            self.assertIn(url, html)
        html = self.tablero('22222222-2').content.decode()  # Supervisor: semáforo y resumen, pero no verifica
        self.assertIn(reverse('indicadores:semaforo'), html)
        self.assertNotIn(reverse('actividades:verificacion') + '"', html.split('<main role="main">')[1])
        html = self.tablero('55555555-5').content.decode()  # Administrativo: lo suyo
        self.assertIn(reverse('actividades:actividad_crear'), html)
        self.assertNotIn(reverse('indicadores:semaforo'), html.split('<main role="main">')[1])


class ValidadorContrasenaTest(TestCase):
    """La contraseña debe combinar mayúscula, minúscula, número y símbolo (UsuarioApp/validators.py)."""

    def test_reglas_de_complejidad(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        validate_password('Serena2026!')  # la de los datos de prueba cumple todo
        with self.assertRaises(ValidationError) as error:
            validate_password('serenacasa')
        self.assertIn('una letra mayúscula, un número y un símbolo especial', ' '.join(error.exception.messages))
        for clave in ['SERENA2026!', 'serena2026!', 'Serena!casa', 'Serena2026x']:
            with self.assertRaises(ValidationError, msg=clave):
                validate_password(clave)

    def test_crear_usuario_con_clave_debil_no_se_guarda(self):
        crear_datos_base()
        crear_usuario('11111111-1', 'Admin')
        self.client.login(username='11111111-1', password=CLAVE)
        self.client.post(reverse('users:usuario_crear'), {
            'rut': '12.345.678-5', 'email': 'nuevo@laserena.cl', 'first_name': 'A', 'last_name': 'B',
            'rol': 'Funcionario', 'cargo': 'TERR', 'delegacion': 'LAS_COMPANIAS', 'territorio': '',
            'password1': 'serenacasa', 'password2': 'serenacasa'})
        self.assertFalse(Usuario.objects.filter(username='12345678-5').exists())

    def test_recuperacion_rechaza_clave_debil(self):
        from django.core import mail
        crear_datos_base()
        func = crear_usuario('55555555-5', 'Funcionario')
        self.client.post(reverse('users:recuperar'), {'email': func.email})
        enlace = [l for l in mail.outbox[0].body.splitlines() if '/usuarios/recuperar/' in l][0].strip()
        formulario = self.client.get(enlace.split('testserver', 1)[1], follow=True)
        url = formulario.redirect_chain[-1][0]
        respuesta = self.client.post(url, {'new_password1': 'serenacasa', 'new_password2': 'serenacasa'})
        self.assertEqual(respuesta.status_code, 200)  # vuelve al formulario con el error
        self.assertContains(respuesta, 'una letra mayúscula')
        self.assertTrue(self.client.login(username='55555555-5', password=CLAVE))  # la clave anterior sigue vigente
