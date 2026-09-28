from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from IndicadoresApp.models import Periodo, MetaDesempeno
from UsuarioApp.funciones import limpiar_rut, validar_rut
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo

CLAVE = 'Serena2026!'


def crear_datos_base():
    for codigo in ['Admin', 'Coordinador', 'Delegado', 'Verificador', 'Funcionario', 'Consulta']:
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
        for nombre in ['indicadores:dashboard', 'indicadores:semaforo', 'indicadores:resumen_delegacion','actividades:mi_gestion', 'actividades:tubo_trabajo', 'actividades:compromiso_crear','actividades:actividad_crear', 'actividades:gestion_social', 'actividades:verificacion','users:administracion', 'auditoria:logs']:
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
