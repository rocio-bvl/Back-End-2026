from django.contrib import admin

from UsuarioApp.admin_sgr import AdminSGR
from IndicadoresApp.models import Periodo, MetaDesempeno, IndicadorDesempeno, AjusteDesempeno


class PeriodoAdmin(AdminSGR):
    list_display = ("nombre", "fecha_inicio", "fecha_termino", "dias_computables", "estado")
    search_fields = ("nombre",)
    list_filter = ("estado",)
    ordering = ("-fecha_inicio",)


class MetaDesempenoAdmin(AdminSGR):
    list_display = ("periodo", "delegacion", "cargo", "item", "valor_objetivo", "unidad", "ponderador")
    search_fields = ("cargo__nombre", "item__nombre", "periodo__nombre")
    list_filter = ("periodo", "cargo")
    ordering = ("periodo", "cargo", "item")


class IndicadorDesempenoAdmin(AdminSGR):
    list_display = ("fecha_calculo", "usuario", "meta", "avance_actual", "meta_esperada",
                    "cumplimiento", "cumplimiento_ponderado", "semaforo")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "meta__item__nombre")
    list_filter = ("semaforo", "fecha_calculo")


class AjusteDesempenoAdmin(AdminSGR):
    list_display = ("fecha", "usuario", "tipo", "valor", "periodo", "registrado_por")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "motivo")
    list_filter = ("periodo", "tipo")


admin.site.register(Periodo, PeriodoAdmin)
admin.site.register(MetaDesempeno, MetaDesempenoAdmin)
admin.site.register(IndicadorDesempeno, IndicadorDesempenoAdmin)
admin.site.register(AjusteDesempeno, AjusteDesempenoAdmin)
