from django.conf import settings
from django.db import models
from django.utils import timezone

from ActividadesApp.choices import estados_actividad, estados_evidencia, decisiones, tipos_gestion_social

# Días antes de la fecha límite en que una actividad del Tubo se marca "por vencer"
DIAS_POR_VENCER = 3

class Actividad(models.Model):
    """Actividad territorial de un funcionario.
    - Con evidencia: queda REGISTRADA y el Delegado la valida (VALIDADA: completada) o rechaza la evidencia
      (RECHAZADA: la actividad sigue vigente y el funcionario resube la evidencia).
    - Sin evidencia: es un compromiso, pasa al Tubo de Trabajo (EN_TUBO) con una fecha límite hasta que
      el mismo funcionario la ejecute y suba la evidencia."""
    # Se registra sola al crear. Solo el Administrador puede corregirla (Django Admin)
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    solicitud_problema = models.TextField(verbose_name="Actividad / solicitud / problema")
    accion = models.CharField(max_length=255, verbose_name="Acción realizada")
    contacto = models.CharField(max_length=255, blank=True, default="", verbose_name="Contacto")
    telefono = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono")
    territorio = models.CharField(max_length=150, blank=True, default="", verbose_name="Territorio / sector")
    ingreso_agenda_colectiva = models.BooleanField(default=False, verbose_name="¿Pasó por el Tubo de Trabajo?")
    fecha_comprometida = models.DateField(null=True, blank=True, verbose_name="Fecha límite (compromiso)")
    estado = models.CharField(max_length=15, choices=estados_actividad, default='REGISTRADA', verbose_name="Estado")
    item = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, related_name='actividades_item', limit_choices_to={'tipo': 'ITEM_GESTION'}, verbose_name="Ítem de gestión")
    periodo = models.ForeignKey('IndicadoresApp.Periodo', on_delete=models.PROTECT, related_name='actividades', verbose_name="Periodo")
    servicio = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, null=True, blank=True, related_name='actividades_servicio', limit_choices_to={'tipo': 'SERVICIO'}, verbose_name="Servicio")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='actividades', verbose_name="Funcionario")

    def __str__(self):
        return f"{self.folio()} - {self.accion}"

    # ----- atributos derivados (/) del diagrama -----
    def folio(self):
        return f"ACT{self.pk}"

    def es_compromiso(self):
        """Una actividad es compromiso mientras está en el Tubo (sin evidencia)."""
        return self.estado == 'EN_TUBO'

    def vencido(self):
        return self.es_compromiso() and self.fecha_comprometida is not None and timezone.localdate() > self.fecha_comprometida

    def proximo_a_vencer(self):
        if not self.es_compromiso() or self.fecha_comprometida is None:
            return False
        dias = (self.fecha_comprometida - timezone.localdate()).days
        return 0 <= dias <= DIAS_POR_VENCER

    def completada(self):
        """La validación del Delegado completa la actividad (también la que vino del Tubo)."""
        return self.estado == 'VALIDADA'

    def evidencia_vigente(self):
        """La última versión de evidencia subida."""
        return self.evidencias.order_by('-version').first()

    # ----- operaciones -----
    def puede_subir_evidencia(self, usuario=None):
        """Sube evidencia el mismo funcionario: cuando la actividad está en el Tubo o su evidencia fue rechazada."""
        if usuario is not None and usuario.pk != self.usuario_id:
            return False
        return self.estado in ('EN_TUBO', 'RECHAZADA')

    def sincronizar_estado(self):
        """El estado sigue a la evidencia vigente. Sin evidencia, la actividad está en el Tubo."""
        evidencia = self.evidencia_vigente()
        if evidencia is None:
            self.estado = 'EN_TUBO'
        elif evidencia.estado_revision == 'APROBADA':
            self.estado = 'VALIDADA'
        elif evidencia.estado_revision == 'RECHAZADA':
            self.estado = 'RECHAZADA'
        else:
            self.estado = 'REGISTRADA'
        self.save()

    class Meta:
        db_table = "actividad"
        verbose_name = "Actividad"
        verbose_name_plural = "Actividades"
        ordering = ["-fecha"]


class Evidencia(models.Model):
    """Fotografía que respalda una actividad. Si se corrige, la nueva versión reemplaza a la anterior."""
    version = models.PositiveSmallIntegerField(default=1, verbose_name="Versión")
    imagen = models.ImageField(upload_to='evidencias/', verbose_name="Imagen (JPG/PNG, máx. 5 MB)")
    comentario = models.TextField(blank=True, default="", verbose_name="Comentario")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    estado_revision = models.CharField(max_length=10, choices=estados_evidencia, default='PENDIENTE', verbose_name="Estado de revisión")
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name='evidencias', verbose_name="Actividad")
    reemplaza_a = models.OneToOneField('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reemplazada_por', verbose_name="Reemplaza a")

    def __str__(self):
        return f"{self.codigo()} v{self.version}"

    def codigo(self):
        return f"ORC{self.pk}"

    class Meta:
        db_table = "evidencia"
        verbose_name = "Evidencia"
        verbose_name_plural = "Evidencias"
        ordering = ["-fecha"]


class Validacion(models.Model):
    """Decisión del Delegado (o Coordinador/Admin) sobre una evidencia: aprobar (completa la actividad) o rechazar
    (la evidencia no es válida y se debe resubir; la actividad no se anula). Una por evidencia."""
    decision = models.CharField(max_length=10, choices=decisiones, verbose_name="Decisión")
    observacion = models.TextField(blank=True, default="", verbose_name="Observación")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    evidencia = models.OneToOneField(Evidencia, on_delete=models.CASCADE, related_name='validacion', verbose_name="Evidencia")
    verificador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='validaciones', verbose_name="Verificado por")

    def __str__(self):
        return f"{self.evidencia.codigo()}: {self.decision}"

    class Meta:
        db_table = "validacion"
        verbose_name = "Validación"
        verbose_name_plural = "Validaciones"
        ordering = ["-fecha"]


class AtencionSocial(models.Model):
    """Atención del área social asociada a una actividad (hasta 3 gestiones)."""
    nombre_solicitante = models.CharField(max_length=200, verbose_name="Nombre del solicitante")
    rut_solicitante = models.CharField(max_length=12, verbose_name="RUT del solicitante")
    telefono_solicitante = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono del solicitante")
    requiere_visita = models.BooleanField(default=False, verbose_name="¿Requiere visita?")
    actividad = models.OneToOneField(Actividad, on_delete=models.CASCADE, related_name='atencion_social', verbose_name="Actividad")
    tipo_atencion = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, related_name='atenciones_tipo', limit_choices_to={'tipo': 'TIPO_ATENCION'}, verbose_name="Tipo de atención")
    subtipo_atencion = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, null=True, blank=True, related_name='atenciones_subtipo', limit_choices_to={'tipo': 'SUBTIPO_ATENCION'}, verbose_name="Subtipo de atención")

    def __str__(self):
        return f"{self.codigo()} - {self.nombre_solicitante}"

    def codigo(self):
        return f"SOC{self.pk}"

    def verificado(self):
        return self.actividad.estado == 'VALIDADA'

    def siguiente_numero_gestion(self):
        """Número de la próxima gestión (1, 2 o 3). Devuelve 0 si ya tiene las 3."""
        cantidad = self.gestiones.count()
        if cantidad >= 3:
            return 0
        return cantidad + 1

    class Meta:
        db_table = "atencion_social"
        verbose_name = "Atención social"
        verbose_name_plural = "Atenciones sociales"


class GestionSocial(models.Model):
    numero_gestion = models.PositiveSmallIntegerField(verbose_name="N° de gestión (1 a 3)")
    tipo = models.CharField(max_length=10, choices=tipos_gestion_social, verbose_name="Tipo")
    accion = models.CharField(max_length=255, verbose_name="Acción")
    fecha = models.DateField(verbose_name="Fecha")
    atencion = models.ForeignKey(AtencionSocial, on_delete=models.CASCADE, related_name='gestiones', verbose_name="Atención")

    def __str__(self):
        return f"Gestión {self.numero_gestion} de {self.atencion.codigo()}"

    class Meta:
        db_table = "gestion_social"
        verbose_name = "Gestión social"
        verbose_name_plural = "Gestiones sociales"
        ordering = ["numero_gestion"]
