"""Plan de Pruebas Unitarias: casos de autenticación (CP-LOGIN) y acceso sin sesión (CP-SEG-003).
Cada método lleva en su nombre el ID del caso del plan para mantener la trazabilidad."""
from django.test import TestCase
from django.urls import reverse

from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE


class PlanLoginTest(TestCase):
    def setUp(self):
        datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', datos['delegacion'], datos['cargo'])

    def intentar(self, rut, clave):
        return self.client.post(reverse('users:login'), {'username': rut, 'password': clave})

    def assert_sin_sesion(self, respuesta):
        self.assertEqual(respuesta.status_code, 200)  # se queda en el login
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_cp_login_001_credenciales_validas(self):
        respuesta = self.intentar('55555555-5', CLAVE)
        self.assertRedirects(respuesta, reverse('indicadores:dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.func.pk)

    def test_cp_login_002_contrasena_incorrecta(self):
        respuesta = self.intentar('55555555-5', 'ClaveIncorrecta1')
        self.assert_sin_sesion(respuesta)
        self.assertContains(respuesta, 'Rut o contraseña incorrectos')

    def test_cp_login_003_usuario_inexistente(self):
        respuesta = self.intentar('99999999-9', CLAVE)
        self.assert_sin_sesion(respuesta)
        self.assertContains(respuesta, 'Rut o contraseña incorrectos')

    def test_cp_login_004_usuario_vacio(self):
        respuesta = self.intentar('', CLAVE)
        self.assert_sin_sesion(respuesta)
        self.assertIn('username', respuesta.context['form'].errors)

    def test_cp_login_005_contrasena_vacia(self):
        respuesta = self.intentar('55555555-5', '')
        self.assert_sin_sesion(respuesta)
        self.assertIn('password', respuesta.context['form'].errors)

    def test_cp_login_006_campos_vacios(self):
        respuesta = self.intentar('', '')
        self.assert_sin_sesion(respuesta)
        errores = respuesta.context['form'].errors
        self.assertIn('username', errores)
        self.assertIn('password', errores)

    def test_cp_login_007_usuario_inactivo(self):
        self.func.is_active = False
        self.func.save()
        respuesta = self.intentar('55555555-5', CLAVE)
        self.assert_sin_sesion(respuesta)

    def test_cp_login_008_formato_invalido(self):
        respuesta = self.intentar('abc@@', CLAVE)
        self.assert_sin_sesion(respuesta)


class PlanSinAutenticacionTest(TestCase):
    def test_cp_seg_003_usuario_sin_autenticacion(self):
        for nombre in ['indicadores:dashboard', 'actividades:mi_gestion', 'actividades:actividad_crear',
                       'actividades:tubo_trabajo', 'actividades:verificacion', 'users:administracion', 'auditoria:logs']:
            respuesta = self.client.get(reverse(nombre))
            self.assertRedirects(respuesta, reverse('users:login'), msg_prefix=nombre)
