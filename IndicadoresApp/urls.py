from django.urls import path
from IndicadoresApp import views as vindicadores

app_name = 'indicadores'

urlpatterns = [
    path('', vindicadores.dashboard, name="dashboard"),
    path('semaforo/', vindicadores.semaforo, name="semaforo"),
    path('semaforo/exportar/', vindicadores.semaforo_exportar, name="semaforo_exportar"),
    path('resumen/', vindicadores.resumen_delegacion, name="resumen_delegacion"),
    path('periodos/nuevo/', vindicadores.periodo_crear, name="periodo_crear"),
    path('periodos/<int:pk>/editar/', vindicadores.periodo_editar, name="periodo_editar"),
    path('periodos/<int:pk>/estado/', vindicadores.periodo_estado, name="periodo_estado"),
    path('metas/guardar/', vindicadores.guardar_metas, name="guardar_metas"),
    path('metas/<int:pk>/editar/', vindicadores.meta_editar, name="meta_editar"),
    path('metas/<int:pk>/eliminar/', vindicadores.meta_eliminar, name="meta_eliminar"),
    path('ponderaciones/guardar/', vindicadores.guardar_ponderacion, name="guardar_ponderacion"),
    path('ponderaciones/<int:pk>/editar/', vindicadores.ponderacion_editar, name="ponderacion_editar"),
    path('ponderaciones/<int:pk>/eliminar/', vindicadores.ponderacion_eliminar, name="ponderacion_eliminar"),
    path('ausencias/nueva/', vindicadores.ausencia_crear, name="ausencia_crear"),
    path('ausencias/<int:pk>/eliminar/', vindicadores.ausencia_eliminar, name="ausencia_eliminar"),
    path('atrasos-validacion/', vindicadores.atrasos_validacion, name="atrasos_validacion"),
    path('felicitaciones/', vindicadores.felicitaciones_reclamos, name="felicitaciones_reclamos"),
    path('felicitaciones/nueva/', vindicadores.felicitacion_crear, name="felicitacion_crear"),
    path('felicitaciones/<int:pk>/eliminar/', vindicadores.felicitacion_eliminar, name="felicitacion_eliminar"),
    path('reclamos/nuevo/', vindicadores.reclamo_crear, name="reclamo_crear"),
    path('reclamos/<int:pk>/responder/', vindicadores.reclamo_responder, name="reclamo_responder"),
]
