"""Reglas de Django Admin para los roles del SGR.

Solo el Administrador (superusuario) entra a Django Admin. El Coordinador solo visualiza desde las
pantallas propias del sistema, y el Delegado y el Funcionario tampoco entran (is_staff = False en los
tres; ver Usuario.sincronizar_acceso_admin).
"""
from django.contrib import admin

from AuditoriaApp.registro import registrar_auditoria


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


def resumen_admin(obj):
    return f"{obj} (desde Django Admin)"[:1000]


class AdminSGR(PermisosSGR, admin.ModelAdmin):
    """Los cambios hechos en Django Admin también quedan en la auditoría del SGR (OWASP A09)."""

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        evento = 'MODIFICACION' if change else 'CREACION'
        cambios = ', '.join(form.changed_data) if change and form is not None else ''
        registrar_auditoria(request.user, evento, str(obj._meta.verbose_name), obj.pk,
                            f"Campos modificados: {cambios}" if cambios else '', resumen_admin(obj))

    def delete_model(self, request, obj):
        pk, texto = obj.pk, resumen_admin(obj)
        super().delete_model(request, obj)
        registrar_auditoria(request.user, 'ELIMINACION', str(obj._meta.verbose_name), pk, texto, '')

    def delete_queryset(self, request, queryset):
        eliminados = [(obj.pk, resumen_admin(obj)) for obj in queryset]
        nombre = str(queryset.model._meta.verbose_name)
        super().delete_queryset(request, queryset)
        for pk, texto in eliminados:
            registrar_auditoria(request.user, 'ELIMINACION', nombre, pk, texto, '')


class TabularInlineSGR(PermisosSGR, admin.TabularInline):
    pass
