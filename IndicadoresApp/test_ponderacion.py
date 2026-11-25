"""Ponderación por cargo (RF-006, RN-001): una sola para toda la municipalidad, la definen el Coordinador y el
Administrador, y un cargo cuya ponderación no suma 100% no se mide."""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from IndicadoresApp.calculos import indicadores_usuario, seguimiento_usuario, ranking_cargo
from IndicadoresApp.models import MetaDesempeno, Ponderacion, estado_medicion
from UsuarioApp.models import Catalogo
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE


class PonderacionTest(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()  # ítem 1: ponderación 100% y meta general de 10
        self.cargo, self.periodo = self.datos['cargo'], self.datos['periodo']
        self.admin = crear_usuario('11111111-1', 'Admin')
        self.coord = crear_usuario('22222222-2', 'Coordinador')
        self.delegado = crear_usuario('33333333-3', 'Delegado', self.datos['delegacion'])
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.cargo)
        self.hoy = timezone.localdate()

    def entrar(self, rut):
        self.client.login(username=rut, password=CLAVE)

    def dejar_incompleta(self):
        Ponderacion.objects.filter(item=self.datos['item']).update(ponderador=70)

    def test_con_100_por_ciento_el_cargo_se_mide(self):
        self.assertEqual(estado_medicion(self.cargo.pk, self.periodo, self.datos['delegacion'].pk), '')
        self.assertEqual(len(indicadores_usuario(self.func, self.periodo, self.hoy)), 1)
        self.assertEqual(seguimiento_usuario(self.func, self.periodo, self.hoy)['sin_medir'], '')

    def test_bajo_100_el_cargo_no_se_mide(self):
        self.dejar_incompleta()
        self.assertIn('suma 70', estado_medicion(self.cargo.pk, self.periodo))
        self.assertEqual(indicadores_usuario(self.func, self.periodo, self.hoy), [])
        fila = seguimiento_usuario(self.func, self.periodo, self.hoy)
        self.assertEqual(fila['color'], '')  # sin color: no aparece en rojo por algo que no depende de él
        self.assertTrue(fila['sin_medir'])
        self.assertEqual(ranking_cargo(self.func, self.periodo, self.hoy), [])
        self.entrar('33333333-3')
        self.assertContains(self.client.get(reverse('indicadores:semaforo')), 'SIN MEDIR')
        self.entrar('55555555-5')
        self.assertContains(self.client.get(reverse('actividades:mi_gestion')), 'todavía no se mide')

    def test_falta_una_meta_tambien_impide_medir(self):
        Ponderacion.objects.filter(item=self.datos['item']).update(ponderador=60)
        Ponderacion.objects.create(ponderador=40, cargo=self.cargo, item=Catalogo.objects.get(id=2), periodo=self.periodo)
        self.assertIn('Falta la meta de: Visitas', estado_medicion(self.cargo.pk, self.periodo))

    def test_incompleta_se_guarda_con_aviso(self):
        self.entrar('22222222-2')
        Ponderacion.objects.all().delete()
        respuesta = self.client.post(reverse('indicadores:guardar_ponderacion'),
                                     {'cargo': self.cargo.pk, 'item': 1, 'ponderador': '60'}, follow=True)
        self.assertEqual(Ponderacion.objects.get().ponderador, 60)
        self.assertContains(respuesta, 'Faltan 40')

    def test_no_se_crea_meta_sin_ponderacion(self):
        self.entrar('11111111-1')
        self.client.post(reverse('indicadores:guardar_metas'), {'cargo': self.cargo.pk, 'item': 3, 'valor_objetivo': '5'})
        self.assertFalse(MetaDesempeno.objects.filter(item_id=3).exists())

    def test_no_se_elimina_ponderacion_con_metas(self):
        self.entrar('11111111-1')
        ponderacion = Ponderacion.objects.get()
        self.client.post(reverse('indicadores:ponderacion_eliminar', args=[ponderacion.pk]))
        self.assertTrue(Ponderacion.objects.filter(pk=ponderacion.pk).exists())
        MetaDesempeno.objects.all().delete()
        self.client.post(reverse('indicadores:ponderacion_eliminar', args=[ponderacion.pk]))
        self.assertFalse(Ponderacion.objects.exists())

    def test_permisos_de_los_grupos(self):
        self.assertTrue(self.coord.has_perm('IndicadoresApp.add_ponderacion'))
        self.assertTrue(self.coord.has_perm('IndicadoresApp.add_metadesempeno'))
        self.assertFalse(self.delegado.has_perm('IndicadoresApp.add_ponderacion'))
        self.assertFalse(self.delegado.has_perm('IndicadoresApp.add_metadesempeno'))
        self.assertTrue(self.delegado.has_perm('IndicadoresApp.view_metadesempeno'))

    def test_cambios_de_ponderacion_quedan_en_la_auditoria(self):
        from AuditoriaApp.models import Auditoria
        self.entrar('22222222-2')
        self.client.post(reverse('indicadores:guardar_ponderacion'), {'cargo': self.cargo.pk, 'item': 1, 'ponderador': '90'})
        self.assertTrue(Auditoria.objects.filter(entidad='Ponderacion', evento='MODIFICACION', usuario=self.coord).exists())


class ModificarPonderacionYResumenTest(TestCase):
    def setUp(self):
        from ActividadesApp.models import Actividad
        self.Actividad = Actividad
        self.datos = crear_datos_base()
        self.cargo, self.periodo = self.datos['cargo'], self.datos['periodo']
        crear_usuario('22222222-2', 'Coordinador')
        self.delegado = crear_usuario('33333333-3', 'Delegado', self.datos['delegacion'])
        self.func = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.cargo)

    def test_modificar_ponderacion(self):
        ponderacion = Ponderacion.objects.get()
        self.client.login(username='22222222-2', password=CLAVE)
        url = reverse('indicadores:ponderacion_editar', args=[ponderacion.pk])
        self.assertContains(self.client.get(url), 'Modificar ponderación')
        self.client.post(url, {'ponderador': '150'})  # más de 100: no se guarda
        ponderacion.refresh_from_db()
        self.assertEqual(ponderacion.ponderador, 100)
        self.client.post(url, {'ponderador': '80'})
        ponderacion.refresh_from_db()
        self.assertEqual(ponderacion.ponderador, 80)
        self.assertContains(self.client.get(reverse('users:administracion'), {'pestana': 'metas'}), url)

    def test_delegado_no_modifica_ponderacion(self):
        ponderacion = Ponderacion.objects.get()
        self.client.login(username='33333333-3', password=CLAVE)
        self.client.post(reverse('indicadores:ponderacion_editar', args=[ponderacion.pk]), {'ponderador': '80'})
        ponderacion.refresh_from_db()
        self.assertEqual(ponderacion.ponderador, 100)

    def test_resumen_no_suma_las_gestiones_del_delegado(self):
        from IndicadoresApp.views import avance_equipo
        from UsuarioApp.models import Usuario
        comun = dict(item=self.datos['item'], periodo=self.periodo, estado='VALIDADA', territorio=self.datos['territorio'],
                     solicitud_problema='x', accion='y', fecha_realizacion=timezone.localdate())
        self.Actividad.objects.create(usuario=self.func, **comun)
        self.Actividad.objects.create(usuario=self.delegado, es_gestion=True, encargado=self.func, **comun)
        equipo = Usuario.objects.filter(pk=self.func.pk)
        self.assertEqual(avance_equipo(equipo, self.datos['item'], self.periodo), 1)
