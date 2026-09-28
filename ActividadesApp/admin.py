from django.contrib import admin
from ActividadesApp.models import (Actividad, Evidencia, Validacion, Compromiso, HistorialCompromiso, AtencionSocial, GestionSocial)


class EvidenciaInline(admin.TabularInline):
    model = Evidencia
    extra = 0


class ActividadAdmin(admin.ModelAdmin):
    list_display = ("id", "fecha", "usuario", "item", "accion", "estado", "ingreso_agenda_colectiva")
    search_fields = ("accion", "solicitud_problema", "contacto")
    list_filter = ("estado", "item", "periodo")
    inlines = [EvidenciaInline]


class EvidenciaAdmin(admin.ModelAdmin):
    list_display = ("id", "actividad", "version", "estado_revision", "fecha")
    search_fields = ("comentario", "actividad__accion", "actividad__usuario__username")
    list_filter = ("estado_revision",)


class ValidacionAdmin(admin.ModelAdmin):
    list_display = ("evidencia", "decision", "verificador", "fecha")
    search_fields = ("observacion", "verificador__username", "verificador__first_name")
    list_filter = ("decision",)


class HistorialCompromisoInline(admin.TabularInline):
    model = HistorialCompromiso
    extra = 0


class CompromisoAdmin(admin.ModelAdmin):
    list_display = ("id", "origen", "delegacion", "responsable", "fecha_comprometida", "estado")
    search_fields = ("origen", "solicitante", "observacion")
    list_filter = ("estado", "delegacion")
    inlines = [HistorialCompromisoInline]


class GestionSocialInline(admin.TabularInline):
    model = GestionSocial
    extra = 0
    max_num = 3


class HistorialCompromisoAdmin(admin.ModelAdmin):
    list_display = ("compromiso", "estado_anterior", "estado_nuevo", "autor", "fecha")
    search_fields = ("observacion", "compromiso__origen", "autor__username")
    list_filter = ("estado_nuevo",)


class GestionSocialAdmin(admin.ModelAdmin):
    list_display = ("atencion", "numero_gestion", "tipo", "accion", "fecha")
    search_fields = ("accion", "atencion__nombre_solicitante", "atencion__rut_solicitante")
    list_filter = ("tipo",)


class AtencionSocialAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre_solicitante", "rut_solicitante", "tipo_atencion", "requiere_visita")
    search_fields = ("nombre_solicitante", "rut_solicitante")
    list_filter = ("tipo_atencion",)
    inlines = [GestionSocialInline]


admin.site.register(Actividad, ActividadAdmin)
admin.site.register(Evidencia, EvidenciaAdmin)
admin.site.register(Validacion, ValidacionAdmin)
admin.site.register(Compromiso, CompromisoAdmin)
admin.site.register(HistorialCompromiso, HistorialCompromisoAdmin)
admin.site.register(AtencionSocial, AtencionSocialAdmin)
admin.site.register(GestionSocial, GestionSocialAdmin)
