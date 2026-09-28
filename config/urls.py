from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from UsuarioApp import views as vusuario

urlpatterns = [
    path('admin/', admin.site.urls),
    path('usuarios/', include('UsuarioApp.urls')),
    path('indicadores/', include('IndicadoresApp.urls')),
    path('actividades/', include('ActividadesApp.urls')),
    path('auditoria/', include('AuditoriaApp.urls')),
    path('', vusuario.inicio, name="home"),
]

# En desarrollo (DEBUG = True) Django sirve las fotografías subidas en /media/
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
