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
]
