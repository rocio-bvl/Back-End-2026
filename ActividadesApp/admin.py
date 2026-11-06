from django.contrib import admin

from UsuarioApp.admin_sgr import AdminSGR, TabularInlineSGR
from ActividadesApp.models import (Actividad, Evidencia, Validacion, AtencionSocial, Territorio,
                                   ComentarioActividad, Organizacion, Solicitante, Representante)


class EvidenciaInline(TabularInlineSGR):
    model = Evidencia
    extra = 0


class ComentarioInline(TabularInlineSGR):
    model = ComentarioActividad
    extra = 0


class ActividadAdmin(AdminSGR):
    list_display = ("id", "fecha", "usuario", "encargado", "item", "accion", "estado", "depende_externos", "fecha_realizacion")
    search_fields = ("accion", "solicitud_problema", "territorio__nombre")
    list_filter = ("estado", "depende_externos", "item", "periodo")
    inlines = [EvidenciaInline, ComentarioInline]


class TerritorioAdmin(AdminSGR):
    list_display = ("nombre", "delegacion", "estado")
    search_fields = ("nombre",)
    list_filter = ("delegacion", "estado")


class EvidenciaAdmin(AdminSGR):
    list_display = ("id", "actividad", "version", "estado_revision", "fecha")
    search_fields = ("comentario", "actividad__accion", "actividad__usuario__username")
    list_filter = ("estado_revision",)


class ValidacionAdmin(AdminSGR):
    list_display = ("evidencia", "decision", "verificador", "fecha")
    search_fields = ("observacion", "verificador__username", "verificador__first_name")
    list_filter = ("decision",)


class ComentarioActividadAdmin(AdminSGR):
    list_display = ("actividad", "usuario", "fecha")
    search_fields = ("texto", "actividad__accion", "usuario__username")


class AtencionSocialAdmin(AdminSGR):
    list_display = ("id", "fecha", "solicitante", "tipo_atencion", "usuario", "requiere_visita")
    search_fields = ("solicitante__nombre", "solicitante__rut")
    list_filter = ("tipo_atencion",)


admin.site.register(Actividad, ActividadAdmin)
admin.site.register(Evidencia, EvidenciaAdmin)
admin.site.register(Validacion, ValidacionAdmin)
admin.site.register(AtencionSocial, AtencionSocialAdmin)
admin.site.register(Territorio, TerritorioAdmin)
admin.site.register(ComentarioActividad, ComentarioActividadAdmin)


class OrganizacionAdmin(AdminSGR):
    list_display = ("nombre", "tipo", "delegacion", "socios_activos", "numero_registro_pj", "fecha_inscripcion")
    search_fields = ("nombre", "domicilio_legal", "numero_registro_pj")
    list_filter = ("tipo", "delegacion")


class RepresentanteInline(TabularInlineSGR):
    model = Representante
    extra = 0


class SolicitanteAdmin(AdminSGR):
    list_display = ("nombre", "rut", "telefono")
    search_fields = ("nombre", "rut", "telefono")
    inlines = [RepresentanteInline]


class RepresentanteAdmin(AdminSGR):
    list_display = ("organizacion", "cargo", "solicitante")
    search_fields = ("organizacion__nombre", "solicitante__nombre", "solicitante__rut")
    list_filter = ("cargo",)


admin.site.register(Organizacion, OrganizacionAdmin)
admin.site.register(Solicitante, SolicitanteAdmin)
admin.site.register(Representante, RepresentanteAdmin)
