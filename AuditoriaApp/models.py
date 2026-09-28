from django.conf import settings
from django.db import models
from django.utils import timezone

from AuditoriaApp.choices import eventos


class Auditoria(models.Model):
    """Registro de trazabilidad: quién hizo qué, sobre qué registro y cuándo."""
    evento = models.CharField(max_length=15, choices=eventos, verbose_name="Evento")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    entidad = models.CharField(max_length=100, verbose_name="Entidad")
    id_entidad = models.CharField(max_length=50, verbose_name="ID de la entidad")
    valor_anterior = models.TextField(blank=True, default="", verbose_name="Valor anterior")
    valor_nuevo = models.TextField(blank=True, default="", verbose_name="Valor nuevo")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='auditorias', verbose_name="Usuario")

    def __str__(self):
        return f"{self.evento} {self.entidad} #{self.id_entidad}"

    class Meta:
        db_table = "auditoria"
        verbose_name = "Auditoría"
        verbose_name_plural = "Auditorías"
        ordering = ["-fecha"]
