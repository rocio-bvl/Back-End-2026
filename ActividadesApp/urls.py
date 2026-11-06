from django.urls import path
from ActividadesApp import views as vactividades

app_name = 'actividades'

urlpatterns = [
    path('', vactividades.mi_gestion, name="mi_gestion"),
    path('nueva/', vactividades.actividad_crear, name="actividad_crear"),
    path('<int:pk>/', vactividades.actividad_detalle, name="actividad_detalle"),
    path('<int:pk>/editar/', vactividades.actividad_editar, name='actividad_editar'),
    path('<int:pk>/eliminar/', vactividades.actividad_eliminar, name='actividad_eliminar'),
    path('<int:pk>/evidencia/', vactividades.registrar_evidencia, name="registrar_evidencia"),
    path('<int:pk>/fecha/', vactividades.asignar_fecha, name="asignar_fecha"),
    path('<int:pk>/encargado/', vactividades.asignar_encargado, name="asignar_encargado"),
    path('<int:pk>/puntaje/', vactividades.cambiar_puntaje, name="cambiar_puntaje"),
    path('<int:pk>/comentar/', vactividades.comentar_actividad, name="comentar_actividad"),
    path('tubo/', vactividades.tubo_trabajo, name="tubo_trabajo"),
    path('gestion-social/', vactividades.gestion_social, name="gestion_social"),
    path('solicitantes/buscar/', vactividades.buscar_solicitante, name="buscar_solicitante"),
    path('gestion-social/nueva/', vactividades.atencion_crear, name="atencion_crear"),
    path('gestion-social/<int:pk>/', vactividades.atencion_detalle, name="atencion_detalle"),
    path('gestion-social/<int:pk>/vincular/', vactividades.atencion_vincular, name="atencion_vincular"),
    path('gestion-social/<int:pk>/editar/', vactividades.atencion_editar, name="atencion_editar"),
    path('gestion-social/<int:pk>/eliminar/', vactividades.atencion_eliminar, name="atencion_eliminar"),
    path('verificacion/', vactividades.verificacion, name="verificacion"),
    path('verificacion/<int:pk>/validar/', vactividades.validar_evidencia, name="validar_evidencia"),
]
