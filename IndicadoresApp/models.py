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
    # Una vez cumplido el 120% de un ítem, más actividades ya no suben el puntaje
    tope_cumplimiento = models.DecimalField(max_digits=5, decimal_places=2, default=120, verbose_name="Tope de cumplimiento (%)")

    def __str__(self):
        return self.nombre_completo()

    def nombre_completo(self):
        """El nombre corto (ej. 'T4 - 2026') escrito completo: '4° trimestre 2026'. Se calcula con las fechas;
        si el periodo no calza con un trimestre del calendario, se muestra el nombre tal como se guardó."""
        inicio, termino = self.fecha_inicio, self.fecha_termino
        if inicio and termino and inicio.day == 1 and inicio.month % 3 == 1 and inicio.year == termino.year \
                and termino.month == inicio.month + 2:
            return f"{(inicio.month - 1) // 3 + 1}° trimestre {inicio.year}"
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


def metas_para(cargo_id, periodo, delegacion_id):
    """Metas que se le miden a un cargo en una delegación: las propias de la delegación si definió alguna
    para ese cargo; si no, las generales de la municipalidad."""
    metas = MetaDesempeno.objects.filter(cargo_id=cargo_id, periodo=periodo).select_related('item', 'periodo')
    if delegacion_id is not None:
        propias = metas.filter(delegacion_id=delegacion_id)
        if propias.exists():
            return propias
    return metas.filter(delegacion__isnull=True)


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
    # Vacío = meta general de la municipalidad (la define el Administrador). Con delegación = meta propia de esa
    # delegación (la definen el Administrador o su Delegado) y reemplaza a la general para los cargos que defina.
    delegacion = models.ForeignKey('UsuarioApp.Delegacion', on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='metas', verbose_name="Delegación (vacío = general)")

    def __str__(self):
        alcance = self.delegacion or "General"
        return f"{self.cargo} - {self.item} ({self.periodo}, {alcance})"

    def calcular_meta_esperada(self, fecha):
        return round(Decimal(self.valor_objetivo) * self.periodo.porcentaje_transcurrido(fecha) / 100, 2)

    class Meta:
        db_table = "meta_desempeno"
        verbose_name = "Meta de desempeño"
        verbose_name_plural = "Metas de desempeño"
        ordering = ["delegacion__nombre", "cargo__nombre", "item__id"]


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
        """Actividades del ítem en el periodo que suman puntaje: validadas, que no son gestiones del Delegado y
        cuya validación marcó que llevan punto. Cuentan para quien la realizó: el encargado, si se asignó uno;
        si no, quien la registró."""
        from django.db.models import Q
        from ActividadesApp.models import Actividad
        responsable = Q(encargado=self.usuario) | Q(encargado__isnull=True, usuario=self.usuario)
        actividades = Actividad.objects.filter(responsable, item=self.meta.item, periodo=self.meta.periodo,
                                               estado='VALIDADA', es_gestion=False)
        # Se descuentan las que el validador aprobó marcando que no llevan punto (la misma validación debe
        # cumplir ambas condiciones: una evidencia rechazada antes no cuenta aquí)
        actividades = actividades.exclude(evidencias__validacion__decision='APROBAR',
                                          evidencias__validacion__otorga_puntaje=False)
        return actividades.distinct().count()

    def dias_ausencia(self):
        if not hasattr(self, '_dias_ausencia'):
            self._dias_ausencia = dias_ausencia(self.usuario, self.meta.periodo)
        return self._dias_ausencia

    def objetivo_ajustado(self):
        """Meta del trimestre ajustada a los días que el usuario trabaja: vacaciones, días administrativos y
        licencias descuentan días (por ejemplo, 90 días con 14 de vacaciones: la meta se mide sobre 76)."""
        dias = self.meta.periodo.dias_computables
        if dias == 0:
            return Decimal(self.meta.valor_objetivo)
        trabajados = max(dias - self.dias_ausencia(), 0)
        return round(Decimal(self.meta.valor_objetivo) * trabajados / dias, 2)

    def calcular_meta_esperada(self):
        return round(self.objetivo_ajustado() * self.meta.periodo.porcentaje_transcurrido(self.fecha_calculo) / 100, 2)

    def en_tope(self):
        """El ítem llegó al tope (120%): más actividades de este ítem ya no suben el puntaje."""
        return self.cumplimiento >= self.meta.periodo.tope_cumplimiento

    def calcular_cumplimiento(self):
        objetivo = self.objetivo_ajustado()
        if objetivo == 0:
            return Decimal('0')
        porcentaje = round(Decimal(self.avance_actual) * 100 / objetivo, 2)
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


# «enumeration» TipoAusencia
tipos_ausencia = (
    ('VACACIONES', 'Vacaciones'),
    ('ADMINISTRATIVO', 'Día administrativo'),
    ('LICENCIA', 'Licencia médica'),
)


class Ausencia(models.Model):
    """Vacaciones, días administrativos y licencias de un funcionario o delegado. Los registra el Delegado (para
    los funcionarios de su delegación), el Coordinador o el Administrador. Los días de ausencia dentro del periodo
    se descuentan de los días computables, y la meta del usuario se ajusta sola."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ausencias',
                                verbose_name="Usuario")
    tipo = models.CharField(max_length=15, choices=tipos_ausencia, verbose_name="Tipo")
    desde = models.DateField(verbose_name="Desde")
    hasta = models.DateField(verbose_name="Hasta")
    observacion = models.CharField(max_length=255, blank=True, default="", verbose_name="Observación")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='ausencias_registradas', verbose_name="Registrado por")
    fecha_registro = models.DateTimeField(default=timezone.now, verbose_name="Fecha de registro")

    def __str__(self):
        return f"{self.usuario} - {self.get_tipo_display()} ({self.desde:%d/%m/%Y} al {self.hasta:%d/%m/%Y})"

    def dias(self):
        return (self.hasta - self.desde).days + 1

    class Meta:
        db_table = "ausencia"
        verbose_name = "Ausencia"
        verbose_name_plural = "Ausencias"
        ordering = ["-desde"]


def dias_ausencia(usuario, periodo):
    """Días distintos de ausencia del usuario dentro del periodo (si dos ausencias se cruzan, no se cuentan dos veces)."""
    from datetime import timedelta
    dias = set()
    for ausencia in Ausencia.objects.filter(usuario=usuario, desde__lte=periodo.fecha_termino, hasta__gte=periodo.fecha_inicio):
        dia = max(ausencia.desde, periodo.fecha_inicio)
        fin = min(ausencia.hasta, periodo.fecha_termino)
        while dia <= fin:
            dias.add(dia)
            dia = dia + timedelta(days=1)
    return len(dias)
