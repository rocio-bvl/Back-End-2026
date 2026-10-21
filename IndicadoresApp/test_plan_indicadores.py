"""Plan de Pruebas Unitarias: cálculo de indicadores (CP-CAL)."""
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from ActividadesApp.models import Actividad
from IndicadoresApp.calculos import indicadores_usuario, total_ponderado, seguimiento_usuario
from UsuarioApp.models import Cargo
from UsuarioApp.tests import crear_datos_base, crear_usuario


class PlanIndicadoresTest(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()  # meta: 10 actividades del ítem 1, ponderador 100 %
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        self.hoy = timezone.localdate()

    def validada(self):
        return Actividad.objects.create(solicitud_problema='x', accion='y', item=self.datos['item'],
                                        periodo=self.datos['periodo'], usuario=self.func, estado='VALIDADA')

    def test_cp_cal_001_indicadores_por_usuario(self):
        for _ in range(2):
            self.validada()
        indicadores = indicadores_usuario(self.func, self.datos['periodo'], self.hoy)
        self.assertEqual(len(indicadores), 1)
        indicador = indicadores[0]
        self.assertEqual(indicador.usuario, self.func)
        self.assertEqual(indicador.avance_actual, 2)
        self.assertEqual(indicador.cumplimiento, Decimal('20.00'))          # 2 / 10
        self.assertEqual(indicador.cumplimiento_ponderado, Decimal('20.00'))  # 20 % x 100 %

    def test_cp_cal_002_total_ponderado(self):
        indicadores = [SimpleNamespace(cumplimiento_ponderado=Decimal(v)) for v in ('25', '30', '20')]
        self.assertEqual(total_ponderado(indicadores), Decimal('75'))

    def test_cp_cal_003_usuario_sin_cargo(self):
        sin_cargo = crear_usuario('77777777-7', 'Funcionario', self.datos['delegacion'])
        self.assertEqual(indicadores_usuario(sin_cargo, self.datos['periodo'], self.hoy), [])

    def test_cp_cal_004_usuario_sin_metas(self):
        cargo_sin_metas = Cargo.objects.create(codigo='SINMETA', nombre='Cargo sin metas')
        usuario = crear_usuario('77777777-7', 'Funcionario', self.datos['delegacion'], cargo_sin_metas)
        self.assertEqual(indicadores_usuario(usuario, self.datos['periodo'], self.hoy), [])

    def test_cp_cal_005_periodo_inexistente(self):
        self.assertEqual(indicadores_usuario(self.func, None, self.hoy), [])

    def test_cp_cal_006_avance_cero(self):
        indicador = indicadores_usuario(self.func, self.datos['periodo'], self.hoy)[0]
        self.assertEqual(indicador.avance_actual, 0)
        self.assertEqual(indicador.cumplimiento, Decimal('0'))
        self.assertEqual(indicador.cumplimiento_ponderado, Decimal('0'))

    def test_cp_cal_007_seguimiento_con_semaforo(self):
        # Período de 20 días, 10 transcurridos (50 % esperado). Sin avance: rojo.
        fila = seguimiento_usuario(self.func, self.datos['periodo'], self.hoy)
        self.assertEqual(fila['objetivo_hoy'], Decimal('50.0'))
        self.assertEqual(fila['color'], 'ROJO')
        # 5 actividades validadas de una meta de 10 = 50 % de avance, igual al esperado: verde.
        for _ in range(5):
            self.validada()
        fila = seguimiento_usuario(self.func, self.datos['periodo'], self.hoy)
        self.assertEqual(fila['avance_logrado'], Decimal('50.0'))
        self.assertEqual(fila['color'], 'VERDE')
