"""Rendimiento del Semáforo: DatosMedicion trae todo en pocas consultas y da los mismos resultados que el cálculo
de a un funcionario (calcular_avance, ausencias y ajustes)."""
from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse

from ActividadesApp.models import Actividad, Evidencia, Validacion
from ActividadesApp.tests import BaseActividades
from IndicadoresApp.calculos import DatosMedicion, seguimiento_usuario
from IndicadoresApp.models import IndicadorDesempeno, Ausencia, AjusteDesempeno, metas_para
from UsuarioApp.models import Catalogo


@override_settings(MEDIA_ROOT='/tmp/sgr_test_media')
class DatosMedicionTest(BaseActividades):
    def setUp(self):
        super().setUp()
        p = self.datos['periodo']
        comun = dict(item=self.datos['item'], periodo=p, territorio=self.territorio, solicitud_problema='x', accion='y',
                     fecha_realizacion=self.hoy)
        Actividad.objects.create(usuario=self.func, estado='VALIDADA', **comun)                      # suma al func
        Actividad.objects.create(usuario=self.companero, encargado=self.func, estado='VALIDADA', **comun)  # al func
        Actividad.objects.create(usuario=self.delegado, es_gestion=True, estado='VALIDADA', **comun)  # no suma
        sin_punto = Actividad.objects.create(usuario=self.func, estado='VALIDADA', **comun)           # coordinación
        evidencia = Evidencia.objects.create(actividad=sin_punto, comentario='x', version=1, estado_revision='APROBADA')
        Validacion.objects.create(evidencia=evidencia, decision='APROBAR', verificador=self.delegado, otorga_puntaje=False)
        Actividad.objects.create(usuario=self.func, estado='PROGRAMADA', **comun)                     # pendiente
        Ausencia.objects.create(usuario=self.func, tipo='VACACIONES', desde=self.hoy - timedelta(days=2), hasta=self.hoy,
                                registrado_por=self.admin)
        AjusteDesempeno.objects.create(usuario=self.func, valor=2, periodo=p, registrado_por=self.admin,
                                       tipo=Catalogo.objects.create(tipo='TIPO_AJUSTE', nombre='Prueba'), motivo='x')

    def test_mismos_resultados_que_el_calculo_individual(self):
        p = self.datos['periodo']
        datos = DatosMedicion(p)
        for usuario in [self.func, self.companero, self.otro]:
            for meta in metas_para(usuario.cargo_id, p, usuario.delegacion_id):
                antes = IndicadorDesempeno(usuario=usuario, meta=meta, fecha_calculo=self.hoy)
                ahora = datos.indicador(usuario, meta, self.hoy)
                self.assertEqual((antes.calcular_avance(), antes.dias_ausencia(), antes.calcular_ajuste()),
                                 (ahora._avance, ahora._dias_ausencia, ahora.calcular_ajuste()), usuario)
        self.assertEqual(datos.avances.get((self.func.pk, self.datos['item'].pk)), 2)

    def test_el_semaforo_no_crece_en_consultas_con_mas_funcionarios(self):
        self.entrar('22222222-2')
        with CaptureQueriesContext(connection) as antes:
            self.client.get(reverse('indicadores:semaforo'))
        from UsuarioApp.tests import crear_usuario
        for i in range(10):
            crear_usuario(f'9{i}00000{i}-{i}', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        with CaptureQueriesContext(connection) as despues:
            self.client.get(reverse('indicadores:semaforo'))
        escrituras = [q for q in despues.captured_queries if q['sql'].startswith(('UPDATE', 'INSERT'))]
        self.assertEqual(escrituras, [])  # leer el Semáforo ya no escribe en la base
        self.assertLess(len(despues.captured_queries) - len(antes.captured_queries), 15)

    def test_seguimiento_igual_con_y_sin_datos_compartidos(self):
        p = self.datos['periodo']
        self.assertEqual(seguimiento_usuario(self.func, p, self.hoy), seguimiento_usuario(self.func, p, self.hoy, DatosMedicion(p)))
