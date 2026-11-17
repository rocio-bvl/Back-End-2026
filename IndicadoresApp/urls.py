from django.urls import path
from IndicadoresApp import views as vindicadores

app_name = 'indicadores'

urlpatterns = [
    path('', vindicadores.dashboard, name="dashboard"),
    path('semaforo/', vindicadores.semaforo, name="semaforo"),
    path('resumen/', vindicadores.resumen_delegacion, name="resumen_delegacion"),
    path('metas/guardar/', vindicadores.guardar_metas, name="guardar_metas"),
    path('metas/<int:pk>/editar/', vindicadores.meta_editar, name="meta_editar"),
    path('metas/<int:pk>/eliminar/', vindicadores.meta_eliminar, name="meta_eliminar"),
    path('ausencias/nueva/', vindicadores.ausencia_crear, name="ausencia_crear"),
    path('ausencias/<int:pk>/eliminar/', vindicadores.ausencia_eliminar, name="ausencia_eliminar"),
    path('atrasos-validacion/', vindicadores.atrasos_validacion, name="atrasos_validacion"),
    path('felicitaciones/', vindicadores.felicitaciones_reclamos, name="felicitaciones_reclamos"),
    path('felicitaciones/nueva/', vindicadores.felicitacion_crear, name="felicitacion_crear"),
    path('felicitaciones/<int:pk>/eliminar/', vindicadores.felicitacion_eliminar, name="felicitacion_eliminar"),
    path('reclamos/nuevo/', vindicadores.reclamo_crear, name="reclamo_crear"),
    path('reclamos/<int:pk>/responder/', vindicadores.reclamo_responder, name="reclamo_responder"),
]
