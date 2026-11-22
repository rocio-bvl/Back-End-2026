from django.conf import settings
from django.db import models
from django.utils import timezone

from AuditoriaApp.choices import eventos, canales


class AuditoriaInmutable(Exception):
    """Un registro de auditoría no se modifica ni se borra (RNF-008), ni siquiera el Administrador."""


class AuditoriaQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AuditoriaInmutable("Los registros de auditoría no se pueden modificar.")

    def delete(self):
        raise AuditoriaInmutable("Los registros de auditoría no se pueden eliminar.")


class Auditoria(models.Model):
    """Registro de trazabilidad: quién hizo qué, sobre qué registro, cuándo y desde dónde.
    Solo se agregan registros: modificarlos o borrarlos desde el código o Django Admin lanza AuditoriaInmutable."""
    evento = models.CharField(max_length=15, choices=eventos, verbose_name="Evento")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    entidad = models.CharField(max_length=100, verbose_name="Entidad")
    id_entidad = models.CharField(max_length=50, verbose_name="ID de la entidad")
    valor_anterior = models.TextField(blank=True, default="", verbose_name="Valor anterior")
    valor_nuevo = models.TextField(blank=True, default="", verbose_name="Valor nuevo")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='auditorias', verbose_name="Usuario")
    # Nombre y RUT al momento del evento: si después se elimina el usuario, el registro sigue diciendo quién fue
    usuario_texto = models.CharField(max_length=200, blank=True, default="", verbose_name="Usuario (al registrar)")
    # Origen (RNF-008): IP del equipo y canal del sistema desde donde se hizo la acción
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP de origen")
    canal = models.CharField(max_length=10, choices=canales, blank=True, default='EXTERNO', verbose_name="Canal")

    objects = AuditoriaQuerySet.as_manager()

    def __str__(self):
        return f"{self.evento} {self.entidad} #{self.id_entidad}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditoriaInmutable("Los registros de auditoría no se pueden modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditoriaInmutable("Los registros de auditoría no se pueden eliminar.")

    class Meta:
        db_table = "auditoria"
        verbose_name = "Auditoría"
        verbose_name_plural = "Auditorías"
        ordering = ["-fecha"]
