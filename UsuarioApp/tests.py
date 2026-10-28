from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from IndicadoresApp.models import Periodo, MetaDesempeno
from UsuarioApp.funciones import limpiar_rut, validar_rut
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo

CLAVE = 'Serena2026!'


def crear_datos_base():
    from ActividadesApp.models import Territorio
    for codigo in ['Admin', 'Coordinador', 'Delegado', 'Funcionario']:
        Rol.objects.create(codigo=codigo, nombre=codigo)
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
        self.assertRedirects(respuesta, reverse('users:login'))

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
        for nombre in ['actividades:mi_gestion', 'actividades:tubo_trabajo', 'actividades:gestion_social', 'actividades:verificacion', 'indicadores:semaforo', 'indicadores:resumen_delegacion','users:administracion', 'auditoria:logs']:
            html = self.client.get(reverse(nombre)).content.decode()
            for texto in ['Agregar', 'Buscar']:
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
        self.assertEqual(respuesta['Location'], reverse('users:administracion') + '#goals')
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
                              ('33333333-3', 'actividades:tubo_trabajo'), ('33333333-3', 'indicadores:semaforo'),
                              ('33333333-3', 'indicadores:resumen_delegacion')]:
            html = self.html(rut, pantalla)
            for texto in ['Agregar', 'Modificar', 'Eliminar', 'Buscar']:
                self.assertNotIn(texto, html, f"{pantalla}: {texto}")

    def test_admin_ve_todo_y_actividades_registradas_no_duplica_agregar(self):
        html = self.html('11111111-1', 'actividades:mi_gestion')
        self.assertEqual(html.count('Agregar Actividad'), 1)
        self.assertIn('Modificar', html)

    def test_auditoria_botones_solo_para_admin(self):
        html = self.html('22222222-2', 'auditoria:logs')
        for texto in ['Buscar', 'Agregar', 'Modificar', 'Eliminar']:
            self.assertNotIn(texto, html)
        html = self.html('11111111-1', 'auditoria:logs')
        for texto in ['Agregar', 'Modificar', 'Eliminar', 'Buscar']:
            self.assertIn(texto, html)


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
        Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'],
                                 periodo=self.datos['periodo'], usuario=self.func)
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
