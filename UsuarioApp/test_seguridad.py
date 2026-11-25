"""Pruebas de las brechas OWASP y limitaciones corregidas el 18-11-2026:
límite de intentos, segundo factor por correo, archivos protegidos, auditoría de Django Admin,
transacciones, páginas de error, aviso de rechazo y alerta semanal del Semáforo."""
import os
import time
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from ActividadesApp.models import Evidencia
from ActividadesApp.tests import BaseActividades, foto
from AuditoriaApp.models import Auditoria
from UsuarioApp import seguridad
from UsuarioApp.models import Delegacion
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE, codigo_enviado

MEDIA_PRUEBA = '/tmp/sgr_test_media'


@override_settings(MFA_ACTIVO=True)
class LimiteIntentosTest(TestCase):
    def setUp(self):
        datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', datos['delegacion'], datos['cargo'])

    def intentar(self, clave):
        return self.client.post(reverse('users:login'), {'username': '55555555-5', 'password': clave})

    def test_cada_fallo_queda_en_la_auditoria(self):
        self.intentar('mala')
        fallo = Auditoria.objects.get(evento='LOGIN_FALLIDO')
        self.assertEqual(fallo.id_entidad, '55555555-5')
        self.assertEqual((fallo.ip, fallo.canal), ('127.0.0.1', 'SGR'))

    def test_cinco_fallos_bloquean_aunque_luego_la_clave_sea_correcta(self):
        for _ in range(settings.LOGIN_MAX_INTENTOS):
            respuesta = self.intentar('mala')
        self.assertContains(respuesta, 'Demasiados intentos fallidos')
        respuesta = self.intentar(CLAVE)
        self.assertContains(respuesta, 'Demasiados intentos fallidos')
        self.assertEqual(len(mail.outbox), 0)  # bloqueado: ni siquiera se envía el código
        self.assertTrue(Auditoria.objects.filter(evento='LOGIN_BLOQUEADO').exists())

    def test_cuatro_fallos_no_bloquean(self):
        for _ in range(settings.LOGIN_MAX_INTENTOS - 1):
            self.intentar('mala')
        self.assertRedirects(self.intentar(CLAVE), reverse('users:verificar_codigo'))

    def test_el_bloqueo_vence(self):
        for _ in range(settings.LOGIN_MAX_INTENTOS):
            self.intentar('mala')
        # La auditoría no se puede modificar: en vez de retroceder las fechas, se adelanta el reloj
        despues = seguridad.timezone.now() + seguridad.timedelta(minutes=settings.LOGIN_MINUTOS_BLOQUEO + 1)
        with mock.patch('UsuarioApp.seguridad.timezone.now', return_value=despues):
            self.assertRedirects(self.intentar(CLAVE), reverse('users:verificar_codigo'))


@override_settings(MFA_ACTIVO=True)
class SegundoFactorTest(TestCase):
    def setUp(self):
        datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', datos['delegacion'], datos['cargo'])
        self.client.post(reverse('users:login'), {'username': '55555555-5', 'password': CLAVE})
        self.url = reverse('users:verificar_codigo')

    def test_el_codigo_llega_al_correo_del_usuario_y_no_se_guarda_en_la_sesion(self):
        self.assertEqual(mail.outbox[0].to, [self.func.email])
        codigo = codigo_enviado()
        self.assertNotIn(codigo, str(dict(self.client.session)))
        self.assertContains(self.client.get(self.url), '5***@laserena.cl')

    def test_codigo_incorrecto_no_abre_sesion(self):
        respuesta = self.client.post(self.url, {'codigo': '000000' if codigo_enviado() != '000000' else '111111'})
        self.assertContains(respuesta, 'Código incorrecto')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertTrue(Auditoria.objects.filter(evento='LOGIN_FALLIDO', id_entidad='55555555-5').exists())

    def test_cinco_codigos_malos_obligan_a_partir_de_nuevo(self):
        malo = '000000' if codigo_enviado() != '000000' else '111111'
        for _ in range(settings.MFA_MAX_INTENTOS):
            respuesta = self.client.post(self.url, {'codigo': malo})
        self.assertRedirects(respuesta, reverse('users:login'))
        self.assertRedirects(self.client.post(self.url, {'codigo': codigo_enviado()}), reverse('users:login'))

    def test_codigo_vencido(self):
        datos = self.client.session[seguridad.CLAVE_SESION]
        datos['vence'] = time.time() - 1
        sesion = self.client.session
        sesion[seguridad.CLAVE_SESION] = datos
        sesion.save()
        self.assertRedirects(self.client.post(self.url, {'codigo': codigo_enviado()}), reverse('users:login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_sin_contrasena_previa_no_se_entra_a_la_pantalla_del_codigo(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), reverse('users:login'))

    @override_settings(MFA_ACTIVO=False)
    def test_sin_segundo_factor_entra_directo(self):
        self.client.logout()
        respuesta = self.client.post(reverse('users:login'), {'username': '55555555-5', 'password': CLAVE})
        self.assertRedirects(respuesta, reverse('actividades:mi_gestion'))

    @override_settings(MFA_ACTIVO=False)
    def test_bloqueo_tambien_sin_segundo_factor(self):
        self.client.logout()
        for _ in range(settings.LOGIN_MAX_INTENTOS):
            self.client.post(reverse('users:login'), {'username': '55555555-5', 'password': 'mala'})
        respuesta = self.client.post(reverse('users:login'), {'username': '55555555-5', 'password': CLAVE})
        self.assertContains(respuesta, 'Demasiados intentos fallidos')
        self.assertNotIn('_auth_user_id', self.client.session)


@override_settings(MEDIA_ROOT=MEDIA_PRUEBA)
class ArchivosProtegidosTest(BaseActividades):
    def setUp(self):
        super().setUp()
        actividad = self.crear()
        self.evidencia = Evidencia.objects.create(actividad=actividad, comentario='Hecho', version=1, imagen=foto())
        self.url = self.evidencia.imagen.url

    def test_sin_sesion_no_se_ve_la_foto(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta['Location'].startswith(reverse('users:login')))

    def test_la_ve_su_delegacion_y_no_otra(self):
        self.entrar('33333333-3')  # Delegado de Las Compañías
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.entrar('88888888-8')  # Funcionario de Rural
        self.assertRedirects(self.client.get(self.url), reverse('actividades:mi_gestion'))
        self.assertTrue(Auditoria.objects.filter(evento='ACCESO_DENEGADO').exists())

    def test_no_se_sale_de_la_carpeta_media(self):
        self.entrar('11111111-1')
        for ruta in ['/media/../config/settings.py', '/media/evidencias/no_existe.png', '/media/otra/x.png']:
            self.assertEqual(self.client.get(ruta).status_code, 404, ruta)


class AuditoriaAdminTest(TestCase):
    def setUp(self):
        crear_datos_base()
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.admin.refresh_from_db()
        self.client.force_login(self.admin)

    def test_cambios_en_django_admin_quedan_en_la_auditoria(self):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory
        modelo_admin = site._registry[Delegacion]
        peticion = RequestFactory().post('/admin/')
        peticion.user = self.admin
        nueva = Delegacion(nombre='TEMPORAL', nombre_visible='Temporal', ambito='Urbano')
        modelo_admin.save_model(peticion, nueva, None, change=False)
        pk = nueva.pk
        modelo_admin.delete_model(peticion, nueva)
        eventos = list(Auditoria.objects.filter(id_entidad=str(pk), usuario=self.admin).values_list('evento', flat=True))
        self.assertEqual(sorted(eventos), ['CREACION', 'ELIMINACION'])


class ConfiguracionTest(TestCase):
    def test_cada_peticion_es_una_transaccion(self):
        self.assertTrue(settings.DATABASES['default']['ATOMIC_REQUESTS'])

    @override_settings(DEBUG=False)
    def test_pagina_404_propia(self):
        respuesta = self.client.get('/no-existe/')
        self.assertContains(respuesta, 'La página que busca no existe', status_code=404)

    def test_sesion_de_una_jornada(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 8 * 60 * 60)


@override_settings(MEDIA_ROOT=MEDIA_PRUEBA)
class AvisosPorCorreoTest(BaseActividades):
    def test_rechazo_avisa_al_funcionario_con_el_motivo(self):
        actividad, evidencia = self.con_evidencia()
        self.entrar('33333333-3')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]),
                             {'decision': 'RECHAZAR', 'observacion': 'Falta la lista de asistencia'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.func.email])
        self.assertIn('Falta la lista de asistencia', mail.outbox[0].body)
        self.assertIn(actividad.folio(), mail.outbox[0].subject)

    def test_aprobar_no_envia_correo(self):
        actividad, evidencia = self.con_evidencia()
        self.entrar('33333333-3')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('actividades:validar_evidencia', args=[evidencia.pk]),
                             {'decision': 'APROBAR', 'otorga_puntaje': 'SI'})
        self.assertEqual(len(mail.outbox), 0)

    def test_alerta_semanal_de_semaforo_en_rojo(self):
        call_command('alerta_semaforo', stdout=StringIO())
        para_compania = [m for m in mail.outbox if self.delegado.email in m.to]
        self.assertEqual(len(para_compania), 1)
        self.assertIn(self.func.get_full_name(), para_compania[0].body)
        self.assertEqual(para_compania[0].body.count('\n- '), 2)  # sus 2 funcionarios; el de Rural va a su Delegado


class SesionCerradaTest(TestCase):
    """Al cerrar sesión se pasa por una página intermedia con el logo animado antes de volver al inicio."""
    def setUp(self):
        datos = crear_datos_base()
        self.func = crear_usuario('55555555-5', 'Funcionario', datos['delegacion'], datos['cargo'])
        self.client.force_login(self.func)

    def test_cerrar_sesion_pasa_por_la_pagina_intermedia(self):
        respuesta = self.client.post(reverse('users:logout'))
        self.assertRedirects(respuesta, reverse('users:sesion_cerrada'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_pagina_intermedia_despide_y_vuelve_al_inicio(self):
        self.client.post(reverse('users:logout'))
        respuesta = self.client.get(reverse('users:sesion_cerrada'))
        self.assertContains(respuesta, 'Sesión cerrada')
        self.assertContains(respuesta, 'Hasta pronto, Nombre.')
        self.assertContains(respuesta, 'img/marca/vertical-blanco.svg')
        self.assertContains(respuesta, f'url={reverse("users:login")}')
        # El nombre se usa una sola vez
        self.assertNotContains(self.client.get(reverse('users:sesion_cerrada')), ', Nombre')

    def test_con_sesion_iniciada_no_muestra_la_despedida(self):
        self.assertRedirects(self.client.get(reverse('users:sesion_cerrada')), reverse('actividades:mi_gestion'), fetch_redirect_response=False)
