from django.urls import path
from AuditoriaApp import views as vauditoria

app_name = 'auditoria'

urlpatterns = [
    path('', vauditoria.logs, name="logs"),
]
