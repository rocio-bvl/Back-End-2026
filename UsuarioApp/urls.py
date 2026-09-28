from django.urls import path
from UsuarioApp import views as vusuario

app_name = 'users'

urlpatterns = [
    path('login/', vusuario.iniciar_sesion, name="login"),
    path('logout/', vusuario.cerrar_sesion, name="logout"),
    path('administracion/', vusuario.administracion, name="administracion"),
    path('crear/', vusuario.usuario_crear, name="usuario_crear"),
    path('<int:pk>/editar/', vusuario.usuario_editar, name="usuario_editar"),
]
