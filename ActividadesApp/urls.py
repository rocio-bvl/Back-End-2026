from django.urls import path
from ActividadesApp import views as vactividades

app_name = 'actividades'

urlpatterns = [
    path('', vactividades.mi_gestion, name="mi_gestion"),
    path('nueva/', vactividades.actividad_crear, name="actividad_crear"),
    path('tubo/', vactividades.tubo_trabajo, name="tubo_trabajo"),
    path('tubo/nuevo/', vactividades.compromiso_crear, name="compromiso_crear"),
    path('tubo/<int:pk>/', vactividades.compromiso_detalle, name="compromiso_detalle"),
    path('gestion-social/', vactividades.gestion_social, name="gestion_social"),
    path('verificacion/', vactividades.verificacion, name="verificacion"),
    path('verificacion/<int:pk>/validar/', vactividades.validar_evidencia, name="validar_evidencia"),
]
