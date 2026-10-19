from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from IndicadoresApp.models import Periodo, MetaDesempeno
from UsuarioApp.funciones import limpiar_rut, validar_rut
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo

CLAVE = 'Serena2026!'


def crear_datos_base():
    for codigo in ['Admin', 'Coordinador', 'Delegado', 'Funcionario', 'Consulta']:
        Rol.objects.create(codigo=codigo, nombre=codigo)
    compania = Delegacion.objects.create(nombre='LAS_COMPANIAS', ambito='Urbano')
    Delegacion.objects.create(nombre='RURAL', ambito='Rural')
    item1 = Catalogo.objects.create(id=1, tipo='ITEM_GESTION', nombre='Atención de Usuario')
    Catalogo.objects.create(id=2, tipo='ITEM_GESTION', nombre='Visitas')
    Catalogo.objects.create(id=3, tipo='ITEM_GESTION', nombre='Fiscalizaciones')
    area = Catalogo.objects.create(tipo='AREA', nombre='ORG COM')
    cargo = Cargo.objects.create(codigo='TERR', nombre='Territorial', area=area)
    hoy = timezone.localdate()
    periodo = Periodo.objects.create(nombre='Prueba', fecha_inicio=hoy - timedelta(days=9), fecha_termino=hoy + timedelta(days=10), dias_computables=20)
    MetaDesempeno.objects.create(valor_objetivo=10, ponderador=100, cargo=cargo, item=item1, periodo=periodo)
    return {'delegacion': compania, 'cargo': cargo, 'periodo': periodo, 'item': item1}


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
        self.assertRedirects(respuesta, reverse('indicadores:dashboard'))

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
    """Coordinador = Admin sin crear Coordinadores/Admin ni modificar fechas. Delegado = verifica (ex Verificador).
    Funcionario = registra sin modificar. Consulta = solo visualiza."""

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
        self.consulta = crear_usuario('66666666-6', 'Consulta')
        # Compromiso = actividad sin evidencia en el Tubo de Trabajo
        self.compromiso = Actividad.objects.create(
            solicitud_problema='Luminarias', accion='Gestión con alumbrado', item=self.datos['item'],
            periodo=self.datos['periodo'], usuario=self.func, estado='EN_TUBO', ingreso_agenda_colectiva=True,
            fecha_comprometida=timezone.localdate() + timedelta(days=5))
        actividad = Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'],
                                             periodo=self.datos['periodo'], usuario=self.func)
        self.evidencia = Evidencia.objects.create(actividad=actividad, imagen='evidencias/x.png')

    def entrar(self, rut):
        self.client.login(username=rut, password=CLAVE)

    def crear_usuario_web(self, rut, rol, delegacion='LAS_COMPANIAS'):
        self.client.post(reverse('users:usuario_crear'), {
            'rut': rut, 'email': f'{rut}@laserena.cl', 'first_name': 'A', 'last_name': 'B', 'rol': rol,
            'cargo': 'TERR', 'delegacion': delegacion, 'password1': 'ClaveSegura#2026', 'password2': 'ClaveSegura#2026'})
        return Usuario.objects.filter(username=limpiar_rut(rut)).first()

    # ----- Coordinador -----
    def test_coordinador_es_staff_pero_no_superusuario(self):
        self.coord.refresh_from_db()
        self.assertTrue(self.coord.is_staff)
        self.assertFalse(self.coord.is_superuser)

    def test_coordinador_crea_funcionario_con_delegacion(self):
        self.entrar('22222222-2')
        self.assertEqual(self.client.get(reverse('users:administracion')).status_code, 200)
        nuevo = self.crear_usuario_web('12.345.678-5', 'Funcionario')
        self.assertEqual(nuevo.rol(), 'Funcionario')
        self.assertEqual(nuevo.delegacion, self.datos['delegacion'])

    def test_coordinador_no_crea_coordinador_ni_admin(self):
        self.entrar('22222222-2')
        self.assertIsNone(self.crear_usuario_web('12.345.678-5', 'Coordinador'))
        self.assertIsNone(self.crear_usuario_web('12.345.678-5', 'Admin'))
        self.assertNotIn('value="Coordinador"', self.client.get(reverse('users:administracion')).content.decode())

    def test_admin_si_crea_coordinador(self):
        self.entrar('11111111-1')
        nuevo = self.crear_usuario_web('12.345.678-5', 'Coordinador', 'GENERAL')
        self.assertEqual(nuevo.rol(), 'Coordinador')
        self.assertTrue(nuevo.is_staff)
        self.assertIsNone(nuevo.delegacion)

    def test_coordinador_no_edita_admin_ni_lo_asciende(self):
        self.entrar('22222222-2')
        self.assertRedirects(self.client.get(reverse('users:usuario_editar', args=[self.admin.pk])),
                             reverse('users:administracion'))
        self.client.post(reverse('users:usuario_editar', args=[self.func.pk]), {
            'email': self.func.email, 'first_name': 'X', 'last_name': 'Y', 'is_active': 'on',
            'rol': 'Coordinador', 'delegacion': 'LAS_COMPANIAS'})
        self.func.refresh_from_db()
        self.assertEqual(self.func.rol(), 'Funcionario')

    def test_coordinador_en_django_admin_sin_tocar_fechas(self):
        from django.contrib import admin
        from django.test import RequestFactory
        from ActividadesApp.models import Actividad
        solicitud = RequestFactory().get('/')
        solicitud.user = Usuario.objects.get(pk=self.coord.pk)
        admin_compromiso = admin.site._registry[Actividad]
        al_modificar = admin_compromiso.get_readonly_fields(solicitud, self.compromiso)
        for campo in ['fecha', 'fecha_comprometida']:
            self.assertIn(campo, al_modificar)
        al_agregar = admin_compromiso.get_readonly_fields(solicitud, None)
        self.assertIn('fecha', al_agregar)
        self.assertNotIn('fecha_comprometida', al_agregar)  # se elige al registrar, no se cambia después
        # El Admin (superusuario) sí puede modificar las fechas
        solicitud.user = self.admin
        self.assertEqual(list(admin_compromiso.get_readonly_fields(solicitud, self.compromiso)), [])

    def test_coordinador_en_django_admin_permisos(self):
        self.entrar('22222222-2')
        self.assertEqual(self.client.get(reverse('admin:ActividadesApp_actividad_change', args=[self.compromiso.pk])).status_code, 200)
        # Puede ver al Admin, pero no modificarlo: la página queda de solo lectura
        respuesta = self.client.get(reverse('admin:UsuarioApp_usuario_change', args=[self.admin.pk]))
        self.assertFalse(respuesta.context['has_change_permission'])
        # No puede asignar el rol Admin desde Rol de usuario
        self.client.post(reverse('admin:UsuarioApp_usuariorol_add'), {
            'usuario': self.func.pk, 'rol': Rol.objects.get(codigo='Admin').pk,
            'fecha_asignacion_0': '2026-10-01', 'fecha_asignacion_1': '10:00:00'})
        self.assertFalse(self.func.roles_asignados.filter(rol__codigo='Admin').exists())
        # Edita a un Funcionario, pero sin ver superusuario, staff ni permisos
        html = self.client.get(reverse('admin:UsuarioApp_usuario_change', args=[self.func.pk])).content.decode()
        self.assertNotIn('name="is_superuser"', html)
        self.assertIn('name="is_active"', html)
        # La auditoría es de solo lectura
        self.assertEqual(self.client.get(reverse('admin:AuditoriaApp_auditoria_add')).status_code, 403)

    def test_funcionario_no_entra_a_django_admin(self):
        self.entrar('55555555-5')
        respuesta = self.client.get(reverse('admin:index'))
        self.assertEqual(respuesta.status_code, 302)

    # ----- Delegado (ex Verificador) -----
    def test_delegado_no_registra_actividades_ni_compromisos(self):
        from ActividadesApp.models import Actividad
        self.entrar('33333333-3')
        self.client.post(reverse('actividades:actividad_crear'), {'solicitud_problema': 'x', 'accion': 'y', 'item_comision': '1'})
        self.client.post(reverse('actividades:actividad_crear'), {
            'solicitud_problema': 'x', 'accion': 'y', 'item_comision': '1', 'ingreso_agenda_colectiva': 'on',
            'fecha_comprometida': (timezone.localdate() + timedelta(days=3)).isoformat()})
        self.assertEqual(Actividad.objects.count(), 2)  # las dos del setUp

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

    # ----- Funcionario y Consulta -----
    def test_funcionario_registra_pero_no_modifica_ni_verifica(self):
        self.entrar('55555555-5')
        html = self.client.get(reverse('actividades:mi_gestion')).content.decode()
        self.assertNotIn(reverse('admin:ActividadesApp_actividad_changelist') + '1/change/', html)
        self.assertIn(reverse('actividades:actividad_crear'), html)
        self.assertRedirects(self.client.get(reverse('actividades:verificacion')), reverse('actividades:mi_gestion'))

    def test_consulta_solo_visualiza(self):
        from ActividadesApp.models import Actividad
        self.entrar('66666666-6')
        self.client.post(reverse('actividades:actividad_crear'), {'solicitud_problema': 'x', 'accion': 'y', 'item_comision': '1'})
        self.assertEqual(Actividad.objects.count(), 2)  # las dos del setUp
        html = self.client.get(reverse('indicadores:dashboard')).content.decode()
        self.assertIn(reverse('indicadores:semaforo'), html)
        self.assertIn(reverse('indicadores:resumen_delegacion'), html)
        self.assertNotIn(reverse('users:administracion'), html)

    # ----- Metas (Admin y Coordinador) -----
    def guardar_meta(self, item_id, ponderador):
        return self.client.post(reverse('indicadores:guardar_metas'), {
            'cargo': self.datos['cargo'].pk, 'item': item_id, 'valor_objetivo': '10', 'ponderador': ponderador})

    def test_ponderadores_validados(self):
        self.entrar('22222222-2')
        self.assertEqual(self.guardar_meta(2, 'abc').status_code, 302)  # no es número: no rompe
        self.guardar_meta(2, '10')  # 100 + 10 supera 100%
        self.assertEqual(MetaDesempeno.objects.count(), 1)
        self.guardar_meta(1, '60')
        self.guardar_meta(2, '40')
        self.assertTrue(self.datos['cargo'].validar_ponderadores(self.datos['periodo']))


class MetasYFechasInlineTest(TestCase):
    """Formulario de metas del panel y fechas de gestiones sociales en Django Admin."""

    def setUp(self):
        self.datos = crear_datos_base()
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.admin.sincronizar_acceso_admin()
        self.coord = crear_usuario('22222222-2', 'Coordinador')
        self.coord.sincronizar_acceso_admin()

    def test_formulario_de_metas_completo(self):
        self.client.login(username='22222222-2', password=CLAVE)
        html = self.client.get(reverse('users:administracion')).content.decode()
        for campo in ['name="cargo"', 'name="item"', 'name="valor_objetivo"', 'name="ponderador"', 'Guardar meta']:
            self.assertIn(campo, html)
        self.assertIn('Total 100', html)  # la meta de crear_datos_base aparece con su total

    def test_guardar_meta_vuelve_a_la_pestana(self):
        self.client.login(username='22222222-2', password=CLAVE)
        MetaDesempeno.objects.all().delete()
        respuesta = self.client.post(reverse('indicadores:guardar_metas'), {
            'cargo': self.datos['cargo'].pk, 'item': 2, 'valor_objetivo': '30', 'ponderador': '40'})
        self.assertEqual(respuesta['Location'], reverse('users:administracion') + '#goals')
        meta = MetaDesempeno.objects.get()
        self.assertEqual((meta.valor_objetivo, meta.ponderador), (30, 40))
        # Valores que no son número no provocan error 500
        respuesta = self.client.post(reverse('indicadores:guardar_metas'), {'cargo': 'x', 'item': 'y', 'valor_objetivo': '1', 'ponderador': '1'})
        self.assertEqual(respuesta.status_code, 302)

    def test_fecha_de_gestion_existente_solo_la_cambia_el_admin(self):
        from django.contrib import admin
        from django.test import RequestFactory
        from ActividadesApp.models import Actividad, AtencionSocial, GestionSocial
        func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        tipo = Catalogo.objects.create(tipo='TIPO_ATENCION', nombre='Ayuda social')
        actividad = Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'],
                                             periodo=self.datos['periodo'], usuario=func)
        atencion = AtencionSocial.objects.create(nombre_solicitante='María', rut_solicitante='12345678-5',
                                                 actividad=actividad, tipo_atencion=tipo)
        GestionSocial.objects.create(numero_gestion=1, tipo='VISITA', accion='Visita', fecha=timezone.localdate(), atencion=atencion)

        modelo_admin = admin.site._registry[AtencionSocial]
        solicitud = RequestFactory().get('/')
        solicitud.user = Usuario.objects.get(pk=self.coord.pk)
        inline = modelo_admin.get_inline_instances(solicitud, atencion)[0]
        formset = inline.get_formset(solicitud, atencion)(instance=atencion)
        self.assertTrue(formset.forms[0].fields['fecha'].disabled)       # gestión existente: bloqueada
        self.assertFalse(formset.empty_form.fields['fecha'].disabled)    # gestión nueva: se elige la fecha

        solicitud.user = Usuario.objects.get(pk=self.admin.pk)
        formset = inline.get_formset(solicitud, atencion)(instance=atencion)
        self.assertFalse(formset.forms[0].fields['fecha'].disabled)


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
        crear_usuario('66666666-6', 'Consulta')
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

    def test_delegado_y_consulta_no_ven_botones_crud(self):
        for rut, pantalla in [('33333333-3', 'actividades:mi_gestion'), ('33333333-3', 'actividades:verificacion'),
                              ('33333333-3', 'actividades:tubo_trabajo'), ('66666666-6', 'indicadores:semaforo'),
                              ('66666666-6', 'indicadores:resumen_delegacion')]:
            html = self.html(rut, pantalla)
            for texto in ['Agregar', 'Modificar', 'Eliminar', 'Buscar']:
                self.assertNotIn(texto, html, f"{pantalla}: {texto}")

    def test_admin_ve_todo_y_actividades_registradas_no_duplica_agregar(self):
        html = self.html('11111111-1', 'actividades:mi_gestion')
        self.assertEqual(html.count('Agregar Actividad'), 1)
        self.assertIn('Modificar', html)

    def test_auditoria_botones_solo_para_admin(self):
        html = self.html('22222222-2', 'auditoria:logs')
        self.assertIn('Buscar', html)
        for texto in ['Agregar', 'Modificar', 'Eliminar']:
            self.assertNotIn(texto, html)
        html = self.html('11111111-1', 'auditoria:logs')
        for texto in ['Agregar', 'Modificar', 'Eliminar', 'Buscar']:
            self.assertIn(texto, html)
