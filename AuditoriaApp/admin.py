from django.contrib import admin

from UsuarioApp.admin_sgr import puede_entrar
from AuditoriaApp.models import Auditoria


class AuditoriaAdmin(admin.ModelAdmin):
    """Solo lectura (RNF-008): ni el Administrador agrega, modifica ni elimina registros de auditoría."""
    list_display = ("fecha", "usuario_texto", "evento", "entidad", "id_entidad", "canal", "ip")
    search_fields = ("entidad", "id_entidad", "valor_nuevo", "usuario_texto", "ip")
    list_filter = ("evento", "entidad", "canal")
    ordering = ("-fecha",)
    actions = None

    def has_module_permission(self, request):
        return puede_entrar(request)

    def has_view_permission(self, request, obj=None):
        return puede_entrar(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Auditoria, AuditoriaAdmin)
