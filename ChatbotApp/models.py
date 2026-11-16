from django.conf import settings
from django.db import models

# Quién escribió el mensaje: la persona o el asistente
emisores = (
    ('USUARIO', 'Usuario'),
    ('ASISTENTE', 'Asistente'),
)


class MensajeChat(models.Model):
    """Cada mensaje de la conversación del asistente, guardado por usuario para mantener el historial
    entre sesiones y navegadores."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='mensajes_chat', verbose_name="Usuario")
    emisor = models.CharField(max_length=10, choices=emisores, verbose_name="Emisor")
    contenido = models.TextField(verbose_name="Contenido")
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")

    def __str__(self):
        return f"{self.usuario} - {self.get_emisor_display()}: {self.contenido[:40]}"

    def es_del_asistente(self):
        return self.emisor == 'ASISTENTE'

    class Meta:
        db_table = "mensaje_chat"
        verbose_name = "Mensaje de chat"
        verbose_name_plural = "Mensajes de chat"
        ordering = ["fecha", "id"]
