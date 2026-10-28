"""Reglas de Django Admin para los roles del SGR.

Solo el Administrador (superusuario) entra a Django Admin. El Coordinador solo visualiza desde las
pantallas propias del sistema, y el Delegado y el Funcionario tampoco entran (is_staff = False en los
tres; ver Usuario.sincronizar_acceso_admin).
"""
from django.contrib import admin


def puede_entrar(request):
    return request.user.is_active and request.user.is_superuser


class PermisosSGR:
    """Mezcla común para ModelAdmin e Inline: todo el acceso queda reservado al superusuario."""

    def has_module_permission(self, request):
        return puede_entrar(request)

    def has_view_permission(self, request, obj=None):
        return puede_entrar(request)

    def has_add_permission(self, request, *args):
        return puede_entrar(request)

    def has_change_permission(self, request, obj=None):
        return puede_entrar(request)

    def has_delete_permission(self, request, obj=None):
        return puede_entrar(request)


class AdminSGR(PermisosSGR, admin.ModelAdmin):
    pass


class TabularInlineSGR(PermisosSGR, admin.TabularInline):
    pass
