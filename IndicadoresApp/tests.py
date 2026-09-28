from datetime import date
from decimal import Decimal

from django.test import TestCase

from IndicadoresApp.models import Periodo


class PeriodoTest(TestCase):
    def setUp(self):
        self.periodo = Periodo.objects.create(nombre='T3', fecha_inicio=date(2026, 7, 1), fecha_termino=date(2026, 9, 30), dias_computables=92)

    def test_dias_y_porcentaje(self):
        self.assertEqual(self.periodo.calcular_dias_transcurridos(date(2026, 7, 10)), 10)
        self.assertEqual(self.periodo.calcular_dias_transcurridos(date(2026, 12, 1)), 92)
        self.assertEqual(self.periodo.porcentaje_transcurrido(date(2026, 9, 30)), Decimal('100.0'))

    def test_semaforo(self):
        self.assertEqual(self.periodo.calcular_semaforo(Decimal('100')), 'VERDE')
        self.assertEqual(self.periodo.calcular_semaforo(Decimal('60')), 'AMBAR')
        self.assertEqual(self.periodo.calcular_semaforo(Decimal('59.9')), 'ROJO')
