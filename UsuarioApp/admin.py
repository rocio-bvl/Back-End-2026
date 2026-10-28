from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from UsuarioApp.admin_sgr import AdminSGR, TabularInlineSGR
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo

# Solo el Administrador (superusuario) entra a Django Admin: ver UsuarioApp/admin_sgr.py.


class UsuarioRolInline(TabularInlineSGR):
    model = UsuarioRol
    fk_name = 'usuario'
    extra = 0


class UsuarioAdmin(AdminSGR, UserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "cargo", "delegacion", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    list_filter = ("is_active", "delegacion", "cargo")
    ordering = ("first_name", "last_name")
    inlines = [UsuarioRolInline]
    # Se agregan cargo y delegación a las secciones del admin de usuarios de Django
    fieldsets = UserAdmin.fieldsets + (("Datos SGR", {"fields": ("cargo", "delegacion", "territorio", "telefono")}),)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Si cambió el rol, se ajusta is_staff / is_superuser
        form.instance.sincronizar_acceso_admin()


class RolAdmin(AdminSGR):
    list_display = ("codigo", "nombre", "descripcion")
    search_fields = ("codigo", "nombre", "descripcion")


class UsuarioRolAdmin(AdminSGR):
    list_display = ("usuario", "rol", "fecha_asignacion", "asignado_por")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "rol__nombre")
    list_filter = ("rol",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.usuario.sincronizar_acceso_admin()

    def delete_model(self, request, obj):
        usuario = obj.usuario
        super().delete_model(request, obj)
        usuario.sincronizar_acceso_admin()


class CargoAdmin(AdminSGR):
    list_display = ("codigo", "nombre", "area", "vigencia_inicio", "vigencia_fin", "estado")
    search_fields = ("codigo", "nombre")
    list_filter = ("estado", "area")


class DelegacionAdmin(AdminSGR):
    list_display = ("nombre_visible", "nombre", "ambito", "estado")
    search_fields = ("nombre", "nombre_visible", "ambito")


class CatalogoAdmin(AdminSGR):
    list_display = ("id", "tipo", "nombre", "valor", "area", "padre", "estado")
    search_fields = ("nombre",)
    list_filter = ("tipo", "estado")


admin.site.register(Usuario, UsuarioAdmin)
admin.site.register(Rol, RolAdmin)
admin.site.register(UsuarioRol, UsuarioRolAdmin)
admin.site.register(Cargo, CargoAdmin)
admin.site.register(Delegacion, DelegacionAdmin)
admin.site.register(Catalogo, CatalogoAdmin)
