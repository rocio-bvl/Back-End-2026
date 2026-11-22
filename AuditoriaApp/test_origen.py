"""RNF-008: origen de cada evento (IP y canal) y registros de auditoría de solo lectura."""
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse

from AuditoriaApp.models import Auditoria, AuditoriaInmutable
from AuditoriaApp.origen import ip_de, canal_de
from AuditoriaApp.registro import registrar_auditoria
from UsuarioApp.models import Usuario
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE


class OrigenTest(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        self.factory = RequestFactory()

    def test_evento_desde_las_pantallas_guarda_ip_y_canal_sgr(self):
        self.client.post(reverse('users:login'), {'username': '55555555-5', 'password': 'mala'},
                         REMOTE_ADDR='10.20.30.40')
        fallo = Auditoria.objects.get(evento='LOGIN_FALLIDO')
        self.assertEqual((fallo.ip, fallo.canal), ('10.20.30.40', 'SGR'))

    def test_sin_peticion_es_externo_y_sin_ip(self):
        registro = registrar_auditoria(self.func, 'CREACION', 'Actividad', 1, '', 'desde un comando')
        self.assertEqual((registro.canal, registro.ip), ('EXTERNO', None))
        self.assertEqual(registro.usuario_texto, f"{self.func.get_full_name()} (55555555-5)")

    def test_canal_django_admin(self):
        self.assertEqual(canal_de(self.factory.get('/admin/AuditoriaApp/auditoria/')), 'ADMIN')
        self.assertEqual(canal_de(self.factory.get('/actividades/')), 'SGR')

    def test_x_forwarded_for_se_ignora_sin_proxy(self):
        peticion = self.factory.get('/', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR='1.2.3.4')
        self.assertEqual(ip_de(peticion), '10.0.0.1')  # nadie puede falsear su IP escribiendo el encabezado

    @override_settings(AUDITORIA_CONFIAR_PROXY=True)
    def test_detras_de_proxy_usa_la_ip_que_agrego_el_proxy(self):
        peticion = self.factory.get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_FOR='9.9.9.9, 200.1.2.3')
        self.assertEqual(ip_de(peticion), '200.1.2.3')

    def test_ip_invalida_no_se_guarda(self):
        self.assertIsNone(ip_de(self.factory.get('/', REMOTE_ADDR='no-es-ip')))


class SoloLecturaTest(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        self.registro = registrar_auditoria(self.func, 'CREACION', 'Actividad', 1, '', 'original')

    def test_no_se_modifica_ni_se_borra_desde_el_codigo(self):
        self.registro.valor_nuevo = 'alterado'
        with self.assertRaises(AuditoriaInmutable):
            self.registro.save()
        with self.assertRaises(AuditoriaInmutable):
            self.registro.delete()
        with self.assertRaises(AuditoriaInmutable):
            Auditoria.objects.filter(pk=self.registro.pk).update(valor_nuevo='alterado')
        with self.assertRaises(AuditoriaInmutable):
            Auditoria.objects.all().delete()
        self.assertEqual(Auditoria.objects.get(pk=self.registro.pk).valor_nuevo, 'original')

    def test_el_administrador_solo_puede_verla_en_django_admin(self):
        admin = Usuario.objects.create_superuser('11111111-1', 'admin@laserena.cl', CLAVE)
        self.client.force_login(admin)
        url = reverse('admin:AuditoriaApp_auditoria_change', args=[self.registro.pk])
        self.assertEqual(self.client.get(reverse('admin:AuditoriaApp_auditoria_changelist')).status_code, 200)
        self.client.post(url, {'valor_nuevo': 'alterado'})
        self.assertEqual(self.client.post(reverse('admin:AuditoriaApp_auditoria_delete',
                                                  args=[self.registro.pk]), {'post': 'yes'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:AuditoriaApp_auditoria_add')).status_code, 403)
        self.assertEqual(Auditoria.objects.get(pk=self.registro.pk).valor_nuevo, 'original')

    def test_eliminar_un_usuario_conserva_quien_hizo_el_cambio(self):
        texto = self.registro.usuario_texto
        self.func.delete()
        registro = Auditoria.objects.get(pk=self.registro.pk)
        self.assertIsNone(registro.usuario)
        self.assertEqual(registro.usuario_texto, texto)
