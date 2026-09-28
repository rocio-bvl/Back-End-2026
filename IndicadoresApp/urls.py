from django.urls import path
from IndicadoresApp import views as vindicadores

app_name = 'indicadores'

urlpatterns = [
    path('', vindicadores.dashboard, name="dashboard"),
    path('semaforo/', vindicadores.semaforo, name="semaforo"),
    path('resumen/', vindicadores.resumen_delegacion, name="resumen_delegacion"),
    path('metas/guardar/', vindicadores.guardar_metas, name="guardar_metas"),
]
