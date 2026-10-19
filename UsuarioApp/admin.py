from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from UsuarioApp.admin_sgr import AdminSGR, TabularInlineSGR, es_coordinador
from UsuarioApp.choices import ROLES_RESERVADOS
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo


def validar_rol_para_coordinador(request, rol, instancia):
    """El Coordinador no puede asignar Admin ni Coordinador (sí conservar el que ya tenía la fila)."""
    if rol is None or request.user.is_superuser:
        return
    ya_lo_tenia = instancia.pk is not None and instancia.rol_id == rol.pk
    if rol.codigo in ROLES_RESERVADOS and not ya_lo_tenia:
        raise forms.ValidationError("Solo el Administrador puede asignar los roles Administrador y Coordinador.")


class UsuarioRolInline(TabularInlineSGR):
    model = UsuarioRol
    fk_name = 'usuario'
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formulario = formset.form

        class FormularioRol(formulario):
            def clean_rol(self):
                rol = self.cleaned_data.get('rol')
                validar_rol_para_coordinador(request, rol, self.instance)
                return rol

        formset.form = FormularioRol
        return formset


class UsuarioAdmin(AdminSGR, UserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "cargo", "delegacion", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    list_filter = ("is_active", "delegacion", "cargo")
    ordering = ("first_name", "last_name")
    inlines = [UsuarioRolInline]
    fechas_automaticas = ('last_login',)
    # Se agregan cargo y delegación a las secciones del admin de usuarios de Django
    fieldsets = UserAdmin.fieldsets + (("Datos SGR", {"fields": ("cargo", "delegacion")}),)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser or obj is None:
            return fieldsets
        # El Coordinador no ve is_staff, is_superuser, grupos ni permisos: solo si la cuenta está activa
        resultado = []
        for titulo, opciones in fieldsets:
            campos = opciones.get('fields', ())
            if 'is_superuser' in campos:
                resultado.append(("Estado", {"fields": ("is_active",)}))
            else:
                resultado.append((titulo, opciones))
        return resultado

    def has_change_permission(self, request, obj=None):
        if obj is not None and es_coordinador(request) and obj.pk != request.user.pk:
            if obj.is_superuser or obj.tiene_rol(ROLES_RESERVADOS):
                return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and es_coordinador(request):
            if obj.pk == request.user.pk or obj.is_superuser or obj.tiene_rol(ROLES_RESERVADOS):
                return False
        return super().has_delete_permission(request, obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Si cambió el rol, se ajusta is_staff / is_superuser
        form.instance.sincronizar_acceso_admin()


class RolAdmin(AdminSGR):
    list_display = ("codigo", "nombre", "descripcion")
    search_fields = ("codigo", "nombre", "descripcion")
    solo_lectura_coordinador = True  # los roles son fijos del sistema


class UsuarioRolAdmin(AdminSGR):
    list_display = ("usuario", "rol", "fecha_asignacion", "asignado_por")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "rol__nombre")
    list_filter = ("rol",)

    def get_form(self, request, obj=None, **kwargs):
        formulario = super().get_form(request, obj, **kwargs)

        class FormularioConValidacion(formulario):
            def clean_rol(self):
                rol = self.cleaned_data.get('rol')
                validar_rol_para_coordinador(request, rol, self.instance)
                return rol

        return FormularioConValidacion

    def has_change_permission(self, request, obj=None):
        if obj is not None and es_coordinador(request) and obj.rol.codigo in ROLES_RESERVADOS:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and es_coordinador(request) and obj.rol.codigo in ROLES_RESERVADOS:
            return False
        return super().has_delete_permission(request, obj)

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
    list_display = ("nombre", "ambito", "estado")
    search_fields = ("nombre", "ambito")


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
