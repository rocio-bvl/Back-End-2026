from django.contrib import admin

from UsuarioApp.admin_sgr import AdminSGR
from AuditoriaApp.models import Auditoria


class AuditoriaAdmin(AdminSGR):
    list_display = ("fecha", "usuario", "evento", "entidad", "id_entidad")
    search_fields = ("entidad", "id_entidad", "valor_nuevo")
    list_filter = ("evento", "entidad")
    ordering = ("-fecha",)


admin.site.register(Auditoria, AuditoriaAdmin)
