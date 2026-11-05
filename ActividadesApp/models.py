from django.conf import settings
from django.db import models
from django.utils import timezone

from ActividadesApp.choices import (estados_actividad, estados_evidencia, decisiones,
                                    ESTADOS_PENDIENTES)
from UsuarioApp.choices import estados_registro

# Días antes de la fecha de realización en que un compromiso se marca "por vencer"
DIAS_POR_VENCER = 3


class Territorio(models.Model):
    """Sector o territorio de una delegación. El formulario de actividades lo ofrece como lista."""
    nombre = models.CharField(max_length=150, verbose_name="Nombre")
    delegacion = models.ForeignKey('UsuarioApp.Delegacion', on_delete=models.PROTECT, null=True, blank=True, related_name='territorios', verbose_name="Delegación")
    estado = models.CharField(max_length=10, choices=estados_registro, default='ACTIVO', verbose_name="Estado")

    def __str__(self):
        return self.nombre

    class Meta:
        db_table = "territorio"
        verbose_name = "Territorio"
        verbose_name_plural = "Territorios"
        ordering = ["delegacion__nombre", "nombre"]
        constraints = [models.UniqueConstraint(fields=['nombre', 'delegacion'], name='territorio_unico_por_delegacion')]


class Actividad(models.Model):
    """Actividad territorial de un funcionario. Se registra con la fecha en que se realiza:
    - Hoy o antes: se agrega su evidencia (comentario obligatorio, foto opcional) y queda EVIDENCIA_INGRESADA para validar.
    - Fecha futura: es un compromiso (PROGRAMADA), pendiente hasta que se realice.
    - Depende de factores externos: va al Tubo de Trabajo (EN_TUBO) sin fecha, hasta que se le asigne una.
    Una actividad pendiente puede tener un encargado (un Funcionario) que la realiza, y puede vincularse a una
    solicitud social (AtencionSocial) registrada antes por un funcionario."""
    # Fecha y hora de ingreso: se guarda sola. Solo el Administrador puede corregirla
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha de ingreso")
    solicitud_problema = models.TextField(verbose_name="Actividad / solicitud / problema")
    accion = models.CharField(max_length=255, verbose_name="Acción")
    territorio = models.ForeignKey(Territorio, on_delete=models.PROTECT, null=True, blank=True, related_name='actividades', verbose_name="Territorio / sector")
    depende_externos = models.BooleanField(default=False, verbose_name="¿Depende de factores externos? (Tubo de Trabajo)")
    # Fecha de realización: la elige quien registra. En el Tubo puede quedar vacía y agregarse después
    fecha_realizacion = models.DateField(null=True, blank=True, verbose_name="Fecha de realización")
    estado = models.CharField(max_length=20, choices=estados_actividad, default='EVIDENCIA_INGRESADA', verbose_name="Estado")
    item = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, related_name='actividades_item', limit_choices_to={'tipo': 'ITEM_GESTION'}, verbose_name="Ítem de gestión")
    periodo = models.ForeignKey('IndicadoresApp.Periodo', on_delete=models.PROTECT, related_name='actividades', verbose_name="Periodo")
    servicio = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, null=True, blank=True, related_name='actividades_servicio', limit_choices_to={'tipo': 'SERVICIO'}, verbose_name="Servicio")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='actividades', verbose_name="Registrada por")
    encargado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='actividades_a_cargo', verbose_name="Encargado")
    # Persona atendida: sin nombre y teléfono la actividad no tiene puntaje (requerimiento de la municipalidad)
    nombre_usuario = models.CharField(max_length=150, blank=True, default="", verbose_name="Nombre de la persona atendida")
    telefono_usuario = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono de la persona atendida")
    # Gestión: actividad que ingresa el Delegado. Queda registrada, pero nunca suma puntaje
    es_gestion = models.BooleanField(default=False, verbose_name="Gestión del Delegado (sin puntaje)")
    solicitud = models.ForeignKey('AtencionSocial', on_delete=models.SET_NULL, null=True, blank=True, related_name='actividades', verbose_name="Solicitud social vinculada")

    def __str__(self):
        return f"{self.folio()} - {self.accion}"

    # ----- atributos derivados (/) del diagrama -----
    def folio(self):
        return f"ACT{self.pk}"

    def pendiente(self):
        """Todavía no se realiza: compromiso con fecha (PROGRAMADA) o en el Tubo sin fecha (EN_TUBO)."""
        return self.estado in ESTADOS_PENDIENTES

    def es_compromiso(self):
        """Compromiso = actividad pendiente con una fecha de realización."""
        return self.estado == 'PROGRAMADA'

    def en_tubo(self):
        return self.estado == 'EN_TUBO'

    def vencido(self):
        return self.es_compromiso() and self.fecha_realizacion is not None and timezone.localdate() > self.fecha_realizacion

    def proximo_a_vencer(self):
        if not self.es_compromiso() or self.fecha_realizacion is None:
            return False
        dias = (self.fecha_realizacion - timezone.localdate()).days
        return 0 <= dias <= DIAS_POR_VENCER

    def completada(self):
        """La validación completa la actividad."""
        return self.estado == 'VALIDADA'

    def validacion_vigente(self):
        """Validación de la última evidencia (None si todavía no se revisa)."""
        evidencia = self.evidencia_vigente()
        if evidencia is None:
            return None
        return Validacion.objects.filter(evidencia=evidencia).first()

    def otorga_puntaje(self):
        """Suma puntaje solo si está validada, no es una gestión del Delegado y quien validó marcó que lleva punto."""
        if not self.completada() or self.es_gestion:
            return False
        validacion = self.validacion_vigente()
        return validacion is None or validacion.otorga_puntaje

    def responsable(self):
        """Quien debe realizarla: el encargado si se asignó, si no quien la registró."""
        return self.encargado or self.usuario

    def evidencia_vigente(self):
        """La última evidencia (comentario + foto opcional)."""
        return self.evidencias.order_by('-version').first()

    # Nombre anterior, lo siguen usando algunas plantillas y pruebas
    
    # ----- operaciones -----
    def es_responsable(self, usuario):
        return usuario.pk in (self.usuario_id, self.encargado_id)

    def puede_registrar_evidencia(self, usuario=None):
        """Agrega la evidencia quien la registró o su encargado: si está pendiente o fue rechazada."""
        if usuario is not None and not self.es_responsable(usuario):
            return False
        return self.estado in ESTADOS_PENDIENTES + ['RECHAZADA']

    # Nombre anterior
    
    def sincronizar_estado(self):
        """El estado sigue al la última evidencia. Sin evidencia, la actividad está pendiente:
        en el Tubo si espera factores externos y aún no tiene fecha; si no, programada."""
        evidencia = self.evidencia_vigente()
        if evidencia is None:
            self.estado = 'EN_TUBO' if (self.depende_externos and self.fecha_realizacion is None) else 'PROGRAMADA'
        elif evidencia.estado_revision == 'APROBADA':
            self.estado = 'VALIDADA'
        elif evidencia.estado_revision == 'RECHAZADA':
            self.estado = 'RECHAZADA'
        else:
            self.estado = 'EVIDENCIA_INGRESADA'
        self.save()

    class Meta:
        db_table = "actividad"
        verbose_name = "Actividad"
        verbose_name_plural = "Actividades"
        ordering = ["-fecha"]
        permissions = [
            ("asignar_encargado", "Puede asignar encargado")
        ]


class ComentarioActividad(models.Model):
    """Bitácora de la actividad: actualizaciones de lo que está pasando, con su fecha de ingreso."""
    texto = models.TextField(verbose_name="Comentario")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha de ingreso")
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name='comentarios', verbose_name="Actividad")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='comentarios_actividad', verbose_name="Escrito por")

    def __str__(self):
        return f"{self.actividad.folio()} {self.fecha:%d/%m/%Y %H:%M}"

    class Meta:
        db_table = "comentario_actividad"
        verbose_name = "Comentario de actividad"
        verbose_name_plural = "Comentarios de actividad"
        ordering = ["-fecha"]


class Evidencia(models.Model):
    """Evidencia de una actividad: el comentario de lo que se hizo (obligatorio) y una fotografía
    (opcional). Si se rechaza, el nuevo registro es una nueva versión que reemplaza a la anterior."""
    version = models.PositiveSmallIntegerField(default=1, verbose_name="Versión")
    imagen = models.ImageField(upload_to='evidencias/', blank=True, default="", verbose_name="Fotografía (opcional, JPG/PNG, máx. 5 MB)")
    comentario = models.TextField(verbose_name="Comentario de la evidencia")
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
        permissions = [
            ("validar_evidencia", "Puede validar la evidencia")
        ]


class Validacion(models.Model):
    """Decisión del Delegado (o Coordinador/Admin) sobre una evidencia: aprobar (completa la actividad) o rechazar
    (la evidencia no es válida y se debe resubir; la actividad no se anula). Una por evidencia."""
    decision = models.CharField(max_length=10, choices=decisiones, verbose_name="Decisión")
    observacion = models.TextField(blank=True, default="", verbose_name="Observación")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    evidencia = models.OneToOneField(Evidencia, on_delete=models.CASCADE, related_name='validacion', verbose_name="Evidencia")
    verificador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='validaciones', verbose_name="Verificado por")
    # El validador decide si la actividad lleva punto: la coordinación previa (correos, salón, invitaciones) no lo
    # lleva; la acción realizada sí. Se puede cambiar después y el cambio queda en la auditoría
    otorga_puntaje = models.BooleanField(default=True, verbose_name="¿Suma puntaje?")

    def __str__(self):
        return f"{self.evidencia.codigo()}: {self.decision}"

    class Meta:
        db_table = "validacion"
        verbose_name = "Validación"
        verbose_name_plural = "Validaciones"
        ordering = ["-fecha"]


class AtencionSocial(models.Model):
    """Solicitud de una persona natural atendida por el área social. La registra un funcionario y después
    se le vinculan una o varias actividades: esas actividades son las acciones con que se atiende la solicitud."""
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha de ingreso")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True,
                                related_name='atenciones_registradas', verbose_name="Registrada por")
    nombre_solicitante = models.CharField(max_length=200, verbose_name="Nombre del solicitante")
    rut_solicitante = models.CharField(max_length=12, verbose_name="RUT del solicitante")
    telefono_solicitante = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono del solicitante")
    requiere_visita = models.BooleanField(default=False, verbose_name="¿Requiere visita?")
    tipo_atencion = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, related_name='atenciones_tipo', limit_choices_to={'tipo': 'TIPO_ATENCION'}, verbose_name="Tipo de atención")
    subtipo_atencion = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, null=True, blank=True, related_name='atenciones_subtipo', limit_choices_to={'tipo': 'SUBTIPO_ATENCION'}, verbose_name="Subtipo de atención")

    def __str__(self):
        return f"{self.codigo()} - {self.nombre_solicitante}"

    def codigo(self):
        return f"SOC{self.pk}"

    def estado(self):
        """Pendiente: ninguna actividad vinculada. En proceso: tiene actividades y alguna aún no se valida.
        Atendida: todas sus actividades fueron validadas."""
        actividades = self.actividades.all()
        if not actividades:
            return 'PENDIENTE'
        for actividad in actividades:
            if actividad.estado != 'VALIDADA':
                return 'EN_PROCESO'
        return 'ATENDIDA'

    def get_estado_display(self):
        return {'PENDIENTE': 'Pendiente', 'EN_PROCESO': 'En proceso', 'ATENDIDA': 'Atendida'}[self.estado()]

    def delegacion(self):
        return self.usuario.delegacion if self.usuario else None

    class Meta:
        db_table = "atencion_social"
        ordering = ["-fecha"]
        verbose_name = "Atención social"
        verbose_name_plural = "Atenciones sociales"
