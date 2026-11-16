from django.contrib import admin

from ChatbotApp.models import DocumentoConocimiento, EventoChatbot, MensajeChat
from UsuarioApp.admin_sgr import AdminSGR


class MensajeChatAdmin(AdminSGR):
    list_display = ("fecha", "usuario", "emisor", "contenido")
    search_fields = ("contenido", "usuario__username", "usuario__first_name", "usuario__last_name")
    list_filter = ("emisor",)
    ordering = ("-fecha",)


class DocumentoConocimientoAdmin(AdminSGR):
    """Los documentos del RAG son editables por el Administrador (superusuario)."""

    list_display = ("titulo", "activo", "roles_permitidos", "actualizado")
    search_fields = ("titulo", "contenido", "palabras_clave")
    list_filter = ("activo",)
    ordering = ("titulo",)


class EventoChatbotAdmin(AdminSGR):
    """Solo lectura: es el registro de auditoría de lo que hace la IA."""

    list_display = ("fecha", "usuario", "origen", "modelo", "duracion_ms", "cache_hit", "guardrail")
    search_fields = ("pregunta", "respuesta", "usuario__username")
    list_filter = ("origen", "guardrail", "cache_hit")
    date_hierarchy = "fecha"
    ordering = ("-fecha",)
    readonly_fields = [campo.name for campo in EventoChatbot._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(MensajeChat, MensajeChatAdmin)
admin.site.register(DocumentoConocimiento, DocumentoConocimientoAdmin)
admin.site.register(EventoChatbot, EventoChatbotAdmin)
