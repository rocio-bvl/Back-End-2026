from django.urls import path
from UsuarioApp import views as vusuario

app_name = 'users'

urlpatterns = [
    path('login/', vusuario.iniciar_sesion, name="login"),
    path('logout/', vusuario.cerrar_sesion, name="logout"),
    path('administracion/', vusuario.administracion, name="administracion"),
    path('crear/', vusuario.usuario_crear, name="usuario_crear"),
    path('<int:pk>/editar/', vusuario.usuario_editar, name="usuario_editar"),
    path('<int:pk>/estado/', vusuario.usuario_desactivar, name="usuario_desactivar"),
    path('<int:pk>/eliminar/', vusuario.usuario_eliminar, name="usuario_eliminar"),
    path('delegaciones/nueva/', vusuario.delegacion_crear, name="delegacion_crear"),
    path('delegaciones/<int:pk>/editar/', vusuario.delegacion_editar, name="delegacion_editar"),
    path('delegaciones/<int:pk>/eliminar/', vusuario.delegacion_eliminar, name="delegacion_eliminar"),
    path('perfil/', vusuario.perfil_editar, name="perfil_editar"),
]
