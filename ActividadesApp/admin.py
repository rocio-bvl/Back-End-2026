from django.contrib import admin

from UsuarioApp.admin_sgr import AdminSGR, TabularInlineSGR
from ActividadesApp.models import Actividad, Evidencia, Validacion, AtencionSocial, GestionSocial


class EvidenciaInline(TabularInlineSGR):
    model = Evidencia
    extra = 0


class ActividadAdmin(AdminSGR):
    list_display = ("id", "fecha", "usuario", "item", "accion", "estado", "ingreso_agenda_colectiva", "fecha_comprometida")
    search_fields = ("accion", "solicitud_problema", "contacto", "territorio")
    list_filter = ("estado", "ingreso_agenda_colectiva", "item", "periodo")
    inlines = [EvidenciaInline]


class EvidenciaAdmin(AdminSGR):
    list_display = ("id", "actividad", "version", "estado_revision", "fecha")
    search_fields = ("comentario", "actividad__accion", "actividad__usuario__username")
    list_filter = ("estado_revision",)


class ValidacionAdmin(AdminSGR):
    list_display = ("evidencia", "decision", "verificador", "fecha")
    search_fields = ("observacion", "verificador__username", "verificador__first_name")
    list_filter = ("decision",)


class GestionSocialInline(TabularInlineSGR):
    model = GestionSocial
    extra = 0
    max_num = 3


class GestionSocialAdmin(AdminSGR):
    list_display = ("atencion", "numero_gestion", "tipo", "accion", "fecha")
    search_fields = ("accion", "atencion__nombre_solicitante", "atencion__rut_solicitante")
    list_filter = ("tipo",)


class AtencionSocialAdmin(AdminSGR):
    list_display = ("id", "nombre_solicitante", "rut_solicitante", "tipo_atencion", "requiere_visita")
    search_fields = ("nombre_solicitante", "rut_solicitante")
    list_filter = ("tipo_atencion",)
    inlines = [GestionSocialInline]


admin.site.register(Actividad, ActividadAdmin)
admin.site.register(Evidencia, EvidenciaAdmin)
admin.site.register(Validacion, ValidacionAdmin)
admin.site.register(AtencionSocial, AtencionSocialAdmin)
admin.site.register(GestionSocial, GestionSocialAdmin)
