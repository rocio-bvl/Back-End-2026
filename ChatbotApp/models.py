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
    # Procedencia del mensaje: un payload bloqueado por el guardrail nunca debe volver al proveedor
    # como historial (WB-01/WB-03). Las filas anteriores a esta marca se revalidan en la vista.
    bloqueado = models.BooleanField(default=False, verbose_name="Bloqueado por guardrail")
    motivo = models.CharField(max_length=30, blank=True, default="", verbose_name="Motivo del bloqueo")

    def __str__(self):
        return f"{self.usuario} - {self.get_emisor_display()}: {self.contenido[:40]}"

    def es_del_asistente(self):
        return self.emisor == 'ASISTENTE'

    class Meta:
        db_table = "mensaje_chat"
        verbose_name = "Mensaje de chat"
        verbose_name_plural = "Mensajes de chat"
        ordering = ["fecha", "id"]
        indexes = [
            models.Index(fields=['usuario', '-fecha'], name='mensajechat_usuario_fecha_idx'),
        ]


class DocumentoConocimiento(models.Model):
    """Documento interno (procedimiento o FAQ) que el asistente usa como contexto RAG.

    El Administrador los edita desde Django Admin. `titulo` es la clave de idempotencia del comando
    `cargar_conocimiento_chatbot`, así que no se repiten al ejecutarlo varias veces.
    """
    titulo = models.CharField(max_length=120, unique=True, verbose_name="Título")
    contenido = models.TextField(verbose_name="Contenido")
    palabras_clave = models.CharField(max_length=250, blank=True, default="",
                                      verbose_name="Palabras clave (separadas por coma)")
    # Vacío = disponible para todos los roles del chatbot. Si no, lista separada por coma:
    # 'Admin,Coordinador,Delegado'. El superusuario ve todos los documentos.
    roles_permitidos = models.CharField(max_length=250, blank=True, default="",
                                        verbose_name="Roles permitidos (separados por coma)")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    actualizado = models.DateTimeField(auto_now=True, verbose_name="Actualizado")

    def __str__(self):
        return self.titulo

    class Meta:
        db_table = "documento_conocimiento"
        verbose_name = "Documento de conocimiento"
        verbose_name_plural = "Documentos de conocimiento"
        ordering = ["titulo"]


origenes_chatbot = (
    ('API', 'API remota'),
    ('LOCAL', 'Modelo local'),
    ('CACHE', 'Caché'),
)


class EventoChatbot(models.Model):
    """Registro de una interacción con el asistente (incluye bloqueos y errores).

    Guarda todo lo que hizo la IA para auditoría y depuración: prompts, contexto RAG, mensajes
    enviados, respuesta, modelo, origen, latencia, tokens y guardrails. Nunca contiene la ApiKey.
    """
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='eventos_chatbot', verbose_name="Usuario")
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")
    pregunta = models.TextField(blank=True, default="", verbose_name="Pregunta")
    respuesta = models.TextField(blank=True, default="", verbose_name="Respuesta")
    prompt_sistema = models.TextField(blank=True, default="", verbose_name="Prompt de sistema")
    contexto = models.TextField(blank=True, default="", verbose_name="Contexto RAG")
    mensajes_enviados = models.JSONField(default=list, blank=True, verbose_name="Mensajes enviados al proveedor")
    modelo = models.CharField(max_length=100, blank=True, default="", verbose_name="Modelo")
    origen = models.CharField(max_length=10, choices=origenes_chatbot, blank=True, default="",
                              verbose_name="Origen")
    prompt_version = models.CharField(max_length=20, blank=True, default="", verbose_name="Versión del prompt")
    duracion_ms = models.IntegerField(null=True, blank=True, verbose_name="Duración (ms)")
    tokens_prompt = models.IntegerField(null=True, blank=True, verbose_name="Tokens del prompt")
    tokens_respuesta = models.IntegerField(null=True, blank=True, verbose_name="Tokens de la respuesta")
    cache_hit = models.BooleanField(default=False, verbose_name="¿Respondió desde caché?")
    documentos_rag = models.JSONField(default=list, blank=True, verbose_name="Documentos RAG usados")
    # Códigos: INYECCION, SANEO_SALIDA, RATE_LIMIT, PERMISO (vacío = sin bloqueo)
    guardrail = models.CharField(max_length=30, blank=True, default="", verbose_name="Guardrail")
    error = models.TextField(blank=True, default="", verbose_name="Error")
    # Campo de esquema para el tope del prompt total (T-C-01). T-B-01 solo lo agrega a la base:
    # su cálculo y poblamiento pertenecen a T-C-01 y no se implementan aquí.
    prompt_caracteres = models.IntegerField(null=True, blank=True, verbose_name="Caracteres del prompt")

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y %H:%M} - {self.usuario or 'anónimo'} - {self.origen or 'sin origen'}"

    class Meta:
        db_table = "evento_chatbot"
        verbose_name = "Evento de chatbot"
        verbose_name_plural = "Eventos de chatbot"
        ordering = ["-fecha", "-id"]
