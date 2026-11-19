from django.contrib import admin
from django.urls import path, include
from ActividadesApp.archivos import archivo_protegido
from UsuarioApp import views as vusuario

urlpatterns = [
    path('admin/', admin.site.urls),
    path('usuarios/', include('UsuarioApp.urls')),
    path('indicadores/', include('IndicadoresApp.urls')),
    path('actividades/', include('ActividadesApp.urls')),
    path('auditoria/', include('AuditoriaApp.urls')),
    path('', vusuario.inicio, name="home"),
    # Fotografías subidas: pasan por Django para revisar la sesión y el permiso (ActividadesApp/archivos.py)
    path('media/<path:ruta>', archivo_protegido, name="archivo_protegido"),
]
