"""Periodos de medición desde Administración > Periodos (RF-005, RF-007): Coordinador y Administrador."""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from AuditoriaApp.models import Auditoria
from IndicadoresApp.models import Periodo
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE

NUEVO = {'nombre': 'T1 - 2030', 'fecha_inicio': '2030-01-01', 'fecha_termino': '2030-03-31', 'dias_computables': '',
         'umbral_verde': '100', 'umbral_ambar': '60', 'umbral_colectivo': '80', 'tope_cumplimiento': '120',
         'puntos_felicitacion': '1'}


class PeriodosTest(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()
        crear_usuario('11111111-1', 'Admin')
        self.coord = crear_usuario('22222222-2', 'Coordinador')
        crear_usuario('33333333-3', 'Delegado', self.datos['delegacion'])

    def entrar(self, rut):
        self.client.login(username=rut, password=CLAVE)

    def crear(self, **cambios):
        return self.client.post(reverse('indicadores:periodo_crear'), dict(NUEVO, **cambios))

    def test_coordinador_crea_periodo_y_calcula_los_dias(self):
        self.entrar('22222222-2')
        self.crear()
        periodo = Periodo.objects.get(nombre='T1 - 2030')
        self.assertEqual(periodo.dias_computables, 90)
        self.assertTrue(Auditoria.objects.filter(entidad='Periodo', evento='CREACION', usuario=self.coord).exists())
        self.assertContains(self.client.get(reverse('users:administracion'), {'pestana': 'periodos'}), '1° trimestre 2030')

    def test_reglas_del_periodo(self):
        self.entrar('11111111-1')
        self.crear(fecha_termino='2029-12-01')                    # término antes del inicio
        self.crear(nombre='B', umbral_ambar='120')                  # ámbar sobre el verde
        self.crear(nombre='C', tope_cumplimiento='90')              # tope bajo 100%
        self.crear(nombre='D', fecha_inicio=str(self.datos['periodo'].fecha_inicio),
                   fecha_termino=str(self.datos['periodo'].fecha_termino))  # se cruza con el vigente
        self.assertEqual(Periodo.objects.count(), 1)

    def test_modificar_y_cerrar_periodo(self):
        self.entrar('22222222-2')
        periodo = self.datos['periodo']
        datos = dict(NUEVO, nombre=periodo.nombre, fecha_inicio=str(periodo.fecha_inicio),
                     fecha_termino=str(periodo.fecha_termino), tope_cumplimiento='130')
        self.client.post(reverse('indicadores:periodo_editar', args=[periodo.pk]), datos)
        periodo.refresh_from_db()
        self.assertEqual(periodo.tope_cumplimiento, 130)
        self.client.post(reverse('indicadores:periodo_estado', args=[periodo.pk]))
        periodo.refresh_from_db()
        self.assertTrue(periodo.periodo_cerrado())
        self.client.post(reverse('indicadores:periodo_estado', args=[periodo.pk]))
        periodo.refresh_from_db()
        self.assertFalse(periodo.periodo_cerrado())

    def test_delegado_no_gestiona_periodos(self):
        self.entrar('33333333-3')
        self.crear()
        self.assertFalse(Periodo.objects.filter(nombre='T1 - 2030').exists())
        self.client.post(reverse('indicadores:periodo_estado', args=[self.datos['periodo'].pk]))
        self.datos['periodo'].refresh_from_db()
        self.assertFalse(self.datos['periodo'].periodo_cerrado())
        self.assertNotContains(self.client.get(reverse('users:administracion')), 'id="periods-tab"')
