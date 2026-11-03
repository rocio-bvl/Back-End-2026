from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

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

    # Recuperación de contraseña por correo (vistas que trae Django). success_url es obligatorio:
    # las rutas llevan el prefijo users: y Django buscaría los nombres sin él.
    path('recuperar/', auth_views.PasswordResetView.as_view(
        template_name='users/recuperar.html',
        email_template_name='users/recuperar_email.txt',
        subject_template_name='users/recuperar_asunto.txt',
        success_url=reverse_lazy('users:recuperar_enviado')), name='recuperar'),
    path('recuperar/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='users/recuperar_enviado.html'), name='recuperar_enviado'),
    path('recuperar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='users/recuperar_nueva.html',
        success_url=reverse_lazy('users:recuperar_listo')), name='password_reset_confirm'),
    path('recuperar/listo/', auth_views.PasswordResetCompleteView.as_view(
        template_name='users/recuperar_listo.html'), name='recuperar_listo'),
]
