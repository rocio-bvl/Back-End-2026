from django.contrib import admin

from ChatbotApp.models import MensajeChat
from UsuarioApp.admin_sgr import AdminSGR


class MensajeChatAdmin(AdminSGR):
    list_display = ("fecha", "usuario", "emisor", "contenido")
    search_fields = ("contenido", "usuario__username", "usuario__first_name", "usuario__last_name")
    list_filter = ("emisor",)
    ordering = ("-fecha",)


admin.site.register(MensajeChat, MensajeChatAdmin)
