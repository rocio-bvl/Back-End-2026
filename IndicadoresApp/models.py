from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from IndicadoresApp.choices import semaforos, estados_periodo


class Periodo(models.Model):
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre")
    fecha_inicio = models.DateField(verbose_name="Fecha de inicio")
    fecha_termino = models.DateField(verbose_name="Fecha de término")
    dias_computables = models.PositiveIntegerField(verbose_name="Días computables")
    estado = models.CharField(max_length=10, choices=estados_periodo, default='ACTIVO', verbose_name="Estado")
    umbral_verde = models.DecimalField(max_digits=5, decimal_places=2, default=100, verbose_name="Umbral verde (%)")
    umbral_ambar = models.DecimalField(max_digits=5, decimal_places=2, default=60, verbose_name="Umbral ámbar (%)")
    umbral_colectivo = models.DecimalField(max_digits=5, decimal_places=2, default=80, verbose_name="Umbral colectivo (%)")
    tope_cumplimiento = models.DecimalField(max_digits=5, decimal_places=2, default=150, verbose_name="Tope de cumplimiento (%)")

    def __str__(self):
        return self.nombre

    def calcular_dias_transcurridos(self, fecha):
        if fecha < self.fecha_inicio:
            return 0
        if fecha > self.fecha_termino:
            fecha = self.fecha_termino
        dias = (fecha - self.fecha_inicio).days + 1
        if dias > self.dias_computables:
            dias = self.dias_computables
        return dias

    def porcentaje_transcurrido(self, fecha):
        if self.dias_computables == 0:
            return Decimal('0')
        dias = self.calcular_dias_transcurridos(fecha)
        return round(Decimal(dias) * 100 / Decimal(self.dias_computables), 1)

    def periodo_cerrado(self):
        return self.estado == 'CERRADO'

    def cerrar(self):
        self.estado = 'CERRADO'
        self.save()

    def reabrir(self):
        self.estado = 'ACTIVO'
        self.save()

    def calcular_semaforo(self, cumplimiento):
        if cumplimiento >= self.umbral_verde:
            return 'VERDE'
        if cumplimiento >= self.umbral_ambar:
            return 'AMBAR'
        return 'ROJO'

    class Meta:
        db_table = "periodo"
        verbose_name = "Periodo"
        verbose_name_plural = "Periodos"
        ordering = ["-fecha_inicio"]


def periodo_vigente(fecha=None):
    if fecha is None:
        fecha = timezone.localdate()
    return Periodo.objects.filter(fecha_inicio__lte=fecha, fecha_termino__gte=fecha).first()


class MetaDesempeno(models.Model):
    valor_objetivo = models.PositiveIntegerField(verbose_name="Meta del trimestre")
    unidad = models.CharField(max_length=50, default="actividades", verbose_name="Unidad")
    ponderador = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Ponderador (%)")
    cargo = models.ForeignKey('UsuarioApp.Cargo', on_delete=models.PROTECT, related_name='metas', verbose_name="Cargo")
    item = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, related_name='metas', limit_choices_to={'tipo': 'ITEM_GESTION'}, verbose_name="Ítem de gestión")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name='metas', verbose_name="Periodo")

    def __str__(self):
        return f"{self.cargo} - {self.item} ({self.periodo})"

    def calcular_meta_esperada(self, fecha):
        return round(Decimal(self.valor_objetivo) * self.periodo.porcentaje_transcurrido(fecha) / 100, 2)

    class Meta:
        db_table = "meta_desempeno"
        verbose_name = "Meta de desempeño"
        verbose_name_plural = "Metas de desempeño"
        ordering = ["cargo__nombre", "item__id"]


class IndicadorDesempeno(models.Model):
    fecha_calculo = models.DateField(default=timezone.localdate, verbose_name="Fecha de cálculo")
    avance_actual = models.PositiveIntegerField(default=0, verbose_name="Avance actual")
    meta_esperada = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Meta esperada")
    cumplimiento = models.DecimalField(max_digits=7, decimal_places=2, default=0, verbose_name="Cumplimiento (%)")
    cumplimiento_ponderado = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Cumplimiento ponderado (%)")
    ajuste = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name="Ajuste (pp)")
    semaforo = models.CharField(max_length=5, choices=semaforos, default='ROJO', verbose_name="Semáforo")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='indicadores', verbose_name="Usuario")
    meta = models.ForeignKey(MetaDesempeno, on_delete=models.CASCADE, related_name='indicadores', verbose_name="Meta")

    def __str__(self):
        return f"{self.usuario} - {self.meta.item} ({self.fecha_calculo})"

    def calcular_avance(self):
        from ActividadesApp.models import Actividad
        return Actividad.objects.filter(usuario=self.usuario, item=self.meta.item,
                                        periodo=self.meta.periodo, estado='VALIDADA').count()

    def calcular_meta_esperada(self):
        return self.meta.calcular_meta_esperada(self.fecha_calculo)

    def calcular_cumplimiento(self):
        if self.meta.valor_objetivo == 0:
            return Decimal('0')
        porcentaje = round(Decimal(self.avance_actual) * 100 / Decimal(self.meta.valor_objetivo), 2)
        if porcentaje > self.meta.periodo.tope_cumplimiento:
            porcentaje = self.meta.periodo.tope_cumplimiento
        return porcentaje

    def calcular_ajuste(self):
        total = Decimal('0')
        for ajuste in self.usuario.ajustes_recibidos.filter(periodo=self.meta.periodo):
            total = total + ajuste.valor
        return round(total * self.meta.ponderador / 100, 2)

    def calcular_cumplimiento_ponderado(self):
        return round(self.cumplimiento * self.meta.ponderador / 100 + self.ajuste, 2)

    def calcular(self):
        self.avance_actual = self.calcular_avance()
        self.meta_esperada = self.calcular_meta_esperada()
        self.cumplimiento = self.calcular_cumplimiento()
        self.ajuste = self.calcular_ajuste()
        self.cumplimiento_ponderado = self.calcular_cumplimiento_ponderado()
        if self.meta_esperada > 0:
            logrado = Decimal(self.avance_actual) * 100 / self.meta_esperada
        else:
            logrado = Decimal('100')
        self.semaforo = self.meta.periodo.calcular_semaforo(logrado)
        self.save()

    class Meta:
        db_table = "indicador_desempeno"
        verbose_name = "Indicador de desempeño"
        verbose_name_plural = "Indicadores de desempeño"
        ordering = ["-fecha_calculo"]


class AjusteDesempeno(models.Model):
    valor = models.DecimalField(max_digits=6, decimal_places=2, verbose_name="Valor (pp)")
    motivo = models.TextField(verbose_name="Motivo")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ajustes_registrados', verbose_name="Registrado por")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name='ajustes_recibidos', verbose_name="Usuario evaluado")
    tipo = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, related_name='ajustes', limit_choices_to={'tipo': 'TIPO_AJUSTE'}, verbose_name="Tipo de ajuste")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name='ajustes', verbose_name="Periodo")

    def __str__(self):
        return f"{self.valor} pp a {self.usuario}"

    class Meta:
        db_table = "ajuste_desempeno"
        verbose_name = "Ajuste de desempeño"
        verbose_name_plural = "Ajustes de desempeño"
        ordering = ["-fecha"]
