from django.conf import settings
from django.db import models
from django.utils import timezone

from ActividadesApp.choices import (estados_actividad, estados_evidencia, decisiones,
                                    estados_compromiso, tipos_gestion_social)

# Orden de los estados del compromiso (RF-018)
ORDEN_ESTADOS = ['INGRESADO', 'PENDIENTE', 'EN_PROCESO', 'REALIZADO']


class Compromiso(models.Model):
    """Compromiso del Tubo de Trabajo (agenda colectiva) de una delegación."""
    origen = models.CharField(max_length=150, verbose_name="Origen")
    solicitante = models.CharField(max_length=200, verbose_name="Solicitante")
    territorio = models.CharField(max_length=150, blank=True, default="", verbose_name="Territorio")
    area_apoyo = models.CharField(max_length=150, blank=True, default="", verbose_name="Área de apoyo")
    observacion = models.TextField(verbose_name="Descripción del requerimiento")
    fecha_registro = models.DateTimeField(default=timezone.now, verbose_name="Fecha de registro")
    fecha_comprometida = models.DateField(verbose_name="Fecha comprometida")
    estado = models.CharField(max_length=15, choices=estados_compromiso, default='INGRESADO', verbose_name="Estado")
    fecha_cierre = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de cierre")
    delegacion = models.ForeignKey('UsuarioApp.Delegacion', on_delete=models.PROTECT, related_name='compromisos', verbose_name="Delegación")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='compromisos_registrados', verbose_name="Registrado por")
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='compromisos_responsable', verbose_name="Responsable")

    def __str__(self):
        return f"{self.folio()} - {self.origen}"

    # ----- atributos derivados (/) del diagrama -----
    def folio(self):
        return f"COM{self.pk}"

    def vencido(self):
        return self.estado != 'REALIZADO' and timezone.localdate() > self.fecha_comprometida

    def proximo_a_vencer(self):
        dias = (self.fecha_comprometida - timezone.localdate()).days
        return self.estado != 'REALIZADO' and 0 <= dias <= 3

    def realizado_fuera_de_plazo(self):
        if self.estado != 'REALIZADO' or self.fecha_cierre is None:
            return False
        return timezone.localtime(self.fecha_cierre).date() > self.fecha_comprometida

    # ----- operaciones -----
    def puede_supervisar(self, usuario):
        """Supervisión = Delegado de la misma delegación, Coordinador o Administrador."""
        if usuario.tiene_rol(['Admin', 'Coordinador']):
            return True
        return usuario.tiene_rol(['Delegado']) and usuario.delegacion_id == self.delegacion_id

    def cambiar_estado(self, nuevo_estado, autor, observacion):
        """Aplica las reglas de RF-018. Devuelve (True/False, mensaje)."""
        if nuevo_estado not in ORDEN_ESTADOS:
            return False, "El estado seleccionado no es válido."
        if not observacion.strip():
            return False, "Debe ingresar una observación para cambiar el estado."

        actual = ORDEN_ESTADOS.index(self.estado)
        nuevo = ORDEN_ESTADOS.index(nuevo_estado)
        if nuevo == actual:
            return False, "El compromiso ya se encuentra en ese estado."
        if nuevo > actual + 1:
            return False, "El estado solo puede avanzar un paso a la vez."
        if nuevo < actual and not self.puede_supervisar(autor):
            return False, "Solo el Delegado de la delegación, un Coordinador o un Administrador pueden retroceder o reabrir."
        if nuevo > actual and autor.pk != self.responsable_id and not self.puede_supervisar(autor):
            return False, "Solo el responsable o la supervisión pueden avanzar este compromiso."

        anterior = self.estado
        self.estado = nuevo_estado
        if nuevo_estado == 'REALIZADO':
            self.fecha_cierre = timezone.now()
        else:
            self.fecha_cierre = None
        self.save()
        HistorialCompromiso.objects.create(compromiso=self, autor=autor, estado_anterior=anterior, estado_nuevo=nuevo_estado, observacion=observacion)
        return True, f"Estado actualizado de {anterior} a {nuevo_estado}."

    def reasignar(self, nuevo_responsable, autor):
        if not self.puede_supervisar(autor):
            return False
        self.responsable = nuevo_responsable
        self.save()
        return True

    class Meta:
        db_table = "compromiso"
        verbose_name = "Compromiso"
        verbose_name_plural = "Compromisos"
        ordering = ["fecha_comprometida"]


class HistorialCompromiso(models.Model):
    compromiso = models.ForeignKey(Compromiso, on_delete=models.CASCADE, related_name='historial', verbose_name="Compromiso")
    estado_anterior = models.CharField(max_length=15, blank=True, default="", choices=estados_compromiso, verbose_name="Estado anterior")
    estado_nuevo = models.CharField(max_length=15, choices=estados_compromiso, verbose_name="Estado nuevo")
    observacion = models.TextField(verbose_name="Observación")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='historial_compromisos', verbose_name="Autor")

    def __str__(self):
        return f"{self.compromiso.folio()}: {self.estado_anterior} -> {self.estado_nuevo}"

    class Meta:
        db_table = "historial_compromiso"
        verbose_name = "Historial de compromiso"
        verbose_name_plural = "Historial de compromisos"
        ordering = ["-fecha"]


class Actividad(models.Model):
    """Ingreso diario de actividad territorial de un funcionario."""
    fecha = models.DateTimeField(default=timezone.now, editable=False, verbose_name="Fecha")
    solicitud_problema = models.TextField(verbose_name="Actividad / solicitud / problema")
    accion = models.CharField(max_length=255, verbose_name="Acción realizada")
    contacto = models.CharField(max_length=255, blank=True, default="", verbose_name="Contacto")
    telefono = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono")
    ingreso_agenda_colectiva = models.BooleanField(default=False, verbose_name="¿Ingresa al tubo?")
    estado = models.CharField(max_length=15, choices=estados_actividad, default='REGISTRADA', verbose_name="Estado")
    item = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, related_name='actividades_item', limit_choices_to={'tipo': 'ITEM_GESTION'}, verbose_name="Ítem de gestión")
    periodo = models.ForeignKey('IndicadoresApp.Periodo', on_delete=models.PROTECT, related_name='actividades', verbose_name="Periodo")
    servicio = models.ForeignKey('UsuarioApp.Catalogo', on_delete=models.PROTECT, null=True, blank=True, related_name='actividades_servicio', limit_choices_to={'tipo': 'SERVICIO'}, verbose_name="Servicio")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='actividades', verbose_name="Funcionario")
    compromiso = models.ForeignKey(Compromiso, on_delete=models.SET_NULL, null=True, blank=True, related_name='actividades', verbose_name="Compromiso (tubo)")

    def __str__(self):
        return f"Actividad {self.pk} - {self.accion}"

    def evidencia_vigente(self):
        """La última versión de evidencia subida."""
        return self.evidencias.order_by('-version').first()

    def puede_subir_evidencia(self):
        if self.periodo.periodo_cerrado():
            return False
        evidencia = self.evidencia_vigente()
        return evidencia is None or evidencia.estado_revision == 'OBSERVADA'

    def sincronizar_estado(self):
        """El estado de la actividad sigue al de su evidencia vigente."""
        evidencia = self.evidencia_vigente()
        if evidencia is None:
            self.estado = 'REGISTRADA'
        elif evidencia.estado_revision == 'PENDIENTE':
            self.estado = 'EN_REVISION'
        elif evidencia.estado_revision == 'APROBADA':
            self.estado = 'VALIDADA'
        elif evidencia.estado_revision == 'OBSERVADA':
            self.estado = 'OBSERVADA'
        else:
            self.estado = 'RECHAZADA'
        self.save()

    def marcar_ingreso_agenda(self, compromiso):
        self.ingreso_agenda_colectiva = True
        self.compromiso = compromiso
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
    """Decisión del Verificador sobre una evidencia (una por evidencia)."""
    decision = models.CharField(max_length=10, choices=decisiones, verbose_name="Decisión")
    observacion = models.TextField(blank=True, default="", verbose_name="Observación")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    evidencia = models.OneToOneField(Evidencia, on_delete=models.CASCADE, related_name='validacion', verbose_name="Evidencia")
    verificador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='validaciones', verbose_name="Verificador")

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
