"""Reglas de Django Admin para los roles del SGR.

- Admin (superusuario): acceso total, incluidas las fechas.
- Coordinador (staff, no superusuario): mismas funciones que el Admin, pero
  * no puede modificar fechas ni horas: las que se registran solas quedan de solo lectura siempre
    y, al modificar un registro (también en las filas existentes de un inline), todas las fechas
    quedan bloqueadas;
  * no puede crear ni asignar los roles Admin y Coordinador (ver UsuarioApp/admin.py);
  * las entidades marcadas con solo_lectura_coordinador (Rol, Auditoría) solo las puede ver.
- Delegado, Funcionario y Consulta no entran a Django Admin (is_staff = False).
"""
from django.contrib import admin
from django.db import models


def es_coordinador(request):
    usuario = request.user
    return (usuario.is_active and usuario.is_staff and not usuario.is_superuser
            and usuario.tiene_rol(['Coordinador']))


def puede_entrar(request):
    return request.user.is_active and (request.user.is_superuser or es_coordinador(request))


def campos_fecha(modelo, solo_automaticos, automaticos_extra=()):
    """Campos de fecha/hora editables del modelo. Si solo_automaticos=True, solo los que se
    registran solos (tienen valor por defecto o se completan por el sistema)."""
    nombres = []
    for campo in modelo._meta.fields:
        if not isinstance(campo, models.DateField) or not campo.editable:  # DateTimeField hereda de DateField
            continue
        if solo_automaticos and not (campo.has_default() or campo.name in automaticos_extra):
            continue
        nombres.append(campo.name)
    return nombres


class PermisosSGR:
    """Mezcla común para ModelAdmin e Inline."""
    solo_lectura_coordinador = False
    fechas_automaticas = ()  # fechas sin default que llena el sistema (ej.: fecha_cierre)

    def has_module_permission(self, request):
        return puede_entrar(request)

    def has_view_permission(self, request, obj=None):
        return puede_entrar(request)

    def has_add_permission(self, request, *args):
        if request.user.is_superuser:
            return True
        return es_coordinador(request) and not self.solo_lectura_coordinador

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return es_coordinador(request) and not self.solo_lectura_coordinador

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return es_coordinador(request) and not self.solo_lectura_coordinador


class AdminSGR(PermisosSGR, admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return campos
        # Al agregar: las fechas que se registran solas. Al modificar: todas las fechas.
        fechas = campos_fecha(self.model, solo_automaticos=obj is None, automaticos_extra=self.fechas_automaticas)
        return campos + [nombre for nombre in fechas if nombre not in campos]


class InlineSGR(PermisosSGR):
    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return campos
        fechas = campos_fecha(self.model, solo_automaticos=True, automaticos_extra=self.fechas_automaticas)
        return campos + [nombre for nombre in fechas if nombre not in campos]

    def get_formset(self, request, obj=None, **kwargs):
        """En las filas que ya existen, las fechas quedan bloqueadas para quien no es Admin.
        En las filas nuevas se pueden elegir (ej.: fecha de una gestión social que se agrega)."""
        formset = super().get_formset(request, obj, **kwargs)
        if request.user.is_superuser:
            return formset
        fechas = campos_fecha(self.model, solo_automaticos=False)
        formulario = formset.form

        class FormularioFechasBloqueadas(formulario):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if self.instance.pk is not None:
                    for nombre in fechas:
                        if nombre in self.fields:
                            # disabled: Django ignora lo que llegue en el POST y conserva el valor guardado
                            self.fields[nombre].disabled = True

        formset.form = FormularioFechasBloqueadas
        return formset


class TabularInlineSGR(InlineSGR, admin.TabularInline):
    pass
