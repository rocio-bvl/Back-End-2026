from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo


class UsuarioRolInline(admin.TabularInline):
    model = UsuarioRol
    fk_name = 'usuario'
    extra = 0


class UsuarioAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "cargo", "delegacion", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    list_filter = ("is_active", "delegacion", "cargo")
    ordering = ("first_name", "last_name")
    inlines = [UsuarioRolInline]
    # Se agregan cargo y delegación a las secciones del admin de usuarios de Django
    fieldsets = UserAdmin.fieldsets + (("Datos SGR", {"fields": ("cargo", "delegacion")}),)


class RolAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "descripcion")
    search_fields = ("codigo", "nombre", "descripcion")


class UsuarioRolAdmin(admin.ModelAdmin):
    list_display = ("usuario", "rol", "fecha_asignacion", "asignado_por")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "rol__nombre")
    list_filter = ("rol",)


class CargoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "area", "vigencia_inicio", "vigencia_fin", "estado")
    search_fields = ("codigo", "nombre")
    list_filter = ("estado", "area")


class DelegacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ambito", "estado")
    search_fields = ("nombre", "ambito")


class CatalogoAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo", "nombre", "valor", "area", "padre", "estado")
    search_fields = ("nombre",)
    list_filter = ("tipo", "estado")


admin.site.register(Usuario, UsuarioAdmin)
admin.site.register(Rol, RolAdmin)
admin.site.register(UsuarioRol, UsuarioRolAdmin)
admin.site.register(Cargo, CargoAdmin)
admin.site.register(Delegacion, DelegacionAdmin)
admin.site.register(Catalogo, CatalogoAdmin)