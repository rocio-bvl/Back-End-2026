from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from IndicadoresApp.choices import semaforos, estados_periodo, estados_reclamo


class Periodo(models.Model):
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre")
    fecha_inicio = models.DateField(verbose_name="Fecha de inicio")
    fecha_termino = models.DateField(verbose_name="Fecha de término")
    # RF-005: si se deja vacío, el sistema lo calcula con las fechas (días corridos entre inicio y término)
    dias_computables = models.PositiveIntegerField(blank=True, verbose_name="Días computables",
                                                   help_text="Vacío: se calcula con las fechas de inicio y término.")
    estado = models.CharField(max_length=10, choices=estados_periodo, default='ACTIVO', verbose_name="Estado")
    umbral_verde = models.DecimalField(max_digits=5, decimal_places=2, default=100, verbose_name="Umbral verde (%)")
    umbral_ambar = models.DecimalField(max_digits=5, decimal_places=2, default=60, verbose_name="Umbral ámbar (%)")
    umbral_colectivo = models.DecimalField(max_digits=5, decimal_places=2, default=80, verbose_name="Umbral colectivo (%)")
    # Una vez cumplido el 120% de un ítem, más actividades ya no suben el puntaje
    tope_cumplimiento = models.DecimalField(max_digits=5, decimal_places=2, default=120, verbose_name="Tope de cumplimiento (%)")
    # Lo que suma cada felicitación al cumplimiento total del funcionario (puntos porcentuales). Lo fija el Admin
    puntos_felicitacion = models.DecimalField(max_digits=5, decimal_places=2, default=1,
                                              verbose_name="Puntos por felicitación (pp)")

    def __str__(self):
        return self.nombre_completo()

    def dias_del_periodo(self):
        """Días corridos del periodo, contando el día de inicio y el de término."""
        return (self.fecha_termino - self.fecha_inicio).days + 1

    def clean(self):
        """RF-005: la fecha de término no puede ser anterior a la de inicio y los días computables no pueden
        superar los días del periodo. Sin días computables, se calculan solos. Django Admin llama a este método
        antes de guardar."""
        if self.fecha_inicio and self.fecha_termino:
            if self.fecha_termino < self.fecha_inicio:
                raise ValidationError({'fecha_termino': "La fecha de término no puede ser anterior a la fecha de inicio."})
            if self.dias_computables is None:
                self.dias_computables = self.dias_del_periodo()
            elif self.dias_computables > self.dias_del_periodo():
                raise ValidationError({'dias_computables': f"El periodo tiene {self.dias_del_periodo()} días: los días "
                                                           f"computables no pueden ser más."})

    def save(self, *args, **kwargs):
        if self.dias_computables is None and self.fecha_inicio and self.fecha_termino:
            self.dias_computables = self.dias_del_periodo()
        super().save(*args, **kwargs)

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
    """Metas que se le miden a un cargo en una delegación: por cada ítem ponderado, la meta propia de la delegación
    si la tiene; si no, la general. Si el cargo no es medible (ponderación bajo 100% o falta una meta), ninguna."""
    if periodo is None or estado_medicion(cargo_id, periodo, delegacion_id):
        return MetaDesempeno.objects.none()
    # La ponderación es una sola para toda la municipalidad (Ponderacion); la delegación solo cambia el valor objetivo
    ids = [meta.pk for meta in metas_aplicables(cargo_id, periodo, delegacion_id).values()]
    metas = MetaDesempeno.objects.filter(pk__in=ids).select_related('item', 'periodo')
    return metas.order_by('item__id')


def periodo_vigente(fecha=None):
    if fecha is None:
        fecha = timezone.localdate()
    return Periodo.objects.filter(fecha_inicio__lte=fecha, fecha_termino__gte=fecha).first()


class MetaDesempeno(models.Model):
    valor_objetivo = models.PositiveIntegerField(verbose_name="Meta del trimestre")
    unidad = models.CharField(max_length=50, default="actividades", verbose_name="Unidad")
    ponderador = property(lambda self: ponderador_de(self))  # sale de Ponderacion (al final de este archivo)
    cargo = models.ForeignKey('UsuarioApp.Cargo', on_delete=models.PROTECT, related_name='metas', verbose_name="Cargo")
    item = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, related_name='metas', limit_choices_to={'tipo': 'ITEM_GESTION'}, verbose_name="Ítem de gestión")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name='metas', verbose_name="Periodo")
    # Vacío = meta general de la municipalidad. Con delegación = meta propia de esa delegación para ese ítem: cambia
    # el valor objetivo de la general solo en esa delegación. Ambas las definen el Coordinador y el Administrador.
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
        total = getattr(self, '_ajustes', None)  # ya cargado por DatosMedicion (calculos.py)
        if total is None:
            total = sum((a.valor for a in self.usuario.ajustes_recibidos.filter(periodo=self.meta.periodo)), Decimal('0'))
        return round(total * self.meta.ponderador / 100, 2)

    def calcular_cumplimiento_ponderado(self):
        return round(self.cumplimiento * self.meta.ponderador / 100 + self.ajuste, 2)

    def calcular(self):
        self.avance_actual = self._avance if hasattr(self, '_avance') else self.calcular_avance()
        self.meta_esperada = self.calcular_meta_esperada()
        self.cumplimiento = self.calcular_cumplimiento()
        self.ajuste = self.calcular_ajuste()
        self.cumplimiento_ponderado = self.calcular_cumplimiento_ponderado()
        if self.meta_esperada > 0:
            logrado = Decimal(self.avance_actual) * 100 / self.meta_esperada
        else:
            logrado = Decimal('100')
        self.semaforo = self.meta.periodo.calcular_semaforo(logrado)
        # No se guarda: se calcula al vuelo en cada pantalla (guardar eran ~76 UPDATE por cada visita al Semáforo)

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


def dias_ausencia(usuario, periodo, registradas_antes=None):
    """Días distintos de ausencia del usuario dentro del periodo (si dos ausencias se cruzan, no se cuentan dos veces).
    registradas_antes (fecha y hora): solo las ausencias ya registradas en ese momento. La tendencia semanal lo usa
    para medir cada semana con lo que el sistema sabía ese día, igual que lo mostró el semáforo."""
    from datetime import timedelta
    dias = set()
    ausencias = Ausencia.objects.filter(usuario=usuario, desde__lte=periodo.fecha_termino, hasta__gte=periodo.fecha_inicio)
    if registradas_antes is not None:
        ausencias = ausencias.filter(fecha_registro__lt=registradas_antes)
    for ausencia in ausencias:
        dia = max(ausencia.desde, periodo.fecha_inicio)
        fin = min(ausencia.hasta, periodo.fecha_termino)
        while dia <= fin:
            dias.add(dia)
            dia = dia + timedelta(days=1)
    return len(dias)


# ---------------------------------------------------------------------------
# Felicitaciones y reclamos: los registran el Delegado (funcionarios de su delegación) y el Administrador
# ---------------------------------------------------------------------------
class Felicitacion(models.Model):
    """Felicitación de un usuario (vecino) a un funcionario. Suma al cumplimiento total del funcionario los puntos
    del periodo (puntos_felicitacion), aunque su cargo no tenga meta para felicitaciones: para eso crea un ajuste
    de desempeño. Al eliminarla, el ajuste se borra con ella."""
    funcionario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='felicitaciones_recibidas', verbose_name="Funcionario felicitado")
    fecha = models.DateField(default=timezone.localdate, verbose_name="Fecha de la felicitación")
    motivo = models.TextField(verbose_name="Motivo")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name='felicitaciones', verbose_name="Periodo")
    ajuste = models.OneToOneField(AjusteDesempeno, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='felicitacion', verbose_name="Ajuste de desempeño")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       related_name='felicitaciones_registradas', verbose_name="Registrada por")

    def __str__(self):
        return f"Felicitación a {self.funcionario} ({self.fecha:%d/%m/%Y})"

    def delete(self, *args, **kwargs):
        ajuste = self.ajuste
        super().delete(*args, **kwargs)
        if ajuste is not None:
            ajuste.delete()  # sin felicitación, sus puntos dejan de sumar

    class Meta:
        db_table = "felicitacion"
        verbose_name = "Felicitación"
        verbose_name_plural = "Felicitaciones"
        ordering = ["-fecha", "-pk"]


class Reclamo(models.Model):
    """Reclamo de un usuario (vecino) sobre la atención de un funcionario. No afecta el puntaje: queda Pendiente
    hasta que el Delegado o el Administrador registra la respuesta o la acción tomada."""
    funcionario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='reclamos_recibidos', verbose_name="Funcionario")
    fecha = models.DateField(default=timezone.localdate, verbose_name="Fecha del reclamo")
    motivo = models.TextField(verbose_name="Motivo")
    estado = models.CharField(max_length=10, choices=estados_reclamo, default='PENDIENTE', verbose_name="Estado")
    respuesta = models.TextField(blank=True, default="", verbose_name="Respuesta o acción tomada")
    fecha_respuesta = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de la respuesta")
    respondido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                       related_name='reclamos_respondidos', verbose_name="Respondido por")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       related_name='reclamos_registrados', verbose_name="Registrado por")

    def __str__(self):
        return f"Reclamo sobre {self.funcionario} ({self.fecha:%d/%m/%Y})"

    class Meta:
        db_table = "reclamo"
        verbose_name = "Reclamo"
        verbose_name_plural = "Reclamos"
        ordering = ["estado", "-fecha", "-pk"]


# ---------------------------------------------------------------------------
# Ponderación: el peso de cada ítem en la nota de un cargo (RF-006, RN-001)
# ---------------------------------------------------------------------------
class Ponderacion(models.Model):
    """Peso de un ítem dentro de la nota de un cargo en un periodo. Es uno solo para toda la municipalidad y lo
    definen el Coordinador y el Administrador. Los de un cargo deben sumar 100% para que ese cargo se mida."""
    cargo = models.ForeignKey('UsuarioApp.Cargo', on_delete=models.PROTECT, related_name='ponderaciones', verbose_name="Cargo")
    item = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, related_name='ponderaciones',
                             limit_choices_to={'tipo': 'ITEM_GESTION'}, verbose_name="Ítem de gestión")
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT, related_name='ponderaciones', verbose_name="Periodo")
    ponderador = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Ponderador (%)")

    def __str__(self):
        return f"{self.cargo} - {self.item} ({self.periodo}): {self.ponderador}%"

    class Meta:
        db_table = "ponderacion"
        verbose_name = "Ponderación"
        verbose_name_plural = "Ponderaciones"
        unique_together = [("cargo", "item", "periodo")]
        ordering = ["cargo__nombre", "item__id"]


def ponderador_de(meta):
    """Ponderador de la meta: el de su cargo e ítem en el periodo (0 si todavía no se definió)."""
    if '_ponderador' not in meta.__dict__:
        valor = Ponderacion.objects.filter(cargo_id=meta.cargo_id, item_id=meta.item_id,
                                           periodo_id=meta.periodo_id).values_list('ponderador', flat=True).first()
        meta.__dict__['_ponderador'] = valor if valor is not None else Decimal('0')
    return meta.__dict__['_ponderador']


def total_ponderacion(cargo_id, periodo, excluir_item=None):
    """Suma de los ponderadores del cargo en el periodo. excluir_item: el ítem que se está modificando."""
    ponderaciones = Ponderacion.objects.filter(cargo_id=cargo_id, periodo=periodo)
    if excluir_item is not None:
        ponderaciones = ponderaciones.exclude(item_id=excluir_item)
    return sum((p.ponderador for p in ponderaciones), Decimal('0'))


def metas_aplicables(cargo_id, periodo, delegacion_id):
    """{ítem: meta} para cada ítem ponderado del cargo: la meta de la delegación si existe; si no, la general."""
    metas = MetaDesempeno.objects.filter(cargo_id=cargo_id, periodo=periodo)
    aplicables = {}
    for item_id in Ponderacion.objects.filter(cargo_id=cargo_id, periodo=periodo).values_list('item_id', flat=True):
        propia = metas.filter(item_id=item_id, delegacion_id=delegacion_id).first() if delegacion_id else None
        meta = propia or metas.filter(item_id=item_id, delegacion__isnull=True).first()
        if meta is not None:
            aplicables[item_id] = meta
    return aplicables


def estado_medicion(cargo_id, periodo, delegacion_id=None):
    """'' si el cargo se puede medir; si no, el motivo. Se mide solo con la ponderación completa (100%) y con una
    meta (general o de la delegación) para cada ítem ponderado."""
    total = total_ponderacion(cargo_id, periodo)
    if total != 100:
        return f"La ponderación de este cargo suma {total}% y debe sumar 100%: todavía no se mide."
    faltan = Ponderacion.objects.filter(cargo_id=cargo_id, periodo=periodo).exclude(
        item_id__in=metas_aplicables(cargo_id, periodo, delegacion_id).keys())
    if faltan.exists():
        nombres = ', '.join(p.item.nombre for p in faltan.select_related('item'))
        return f"Falta la meta de: {nombres}. Este cargo todavía no se mide."
    return ''

