from django.urls import path

from ChatbotApp import views as vchatbot

app_name = 'chatbot'

urlpatterns = [
    path('mensaje/', vchatbot.chat_mensaje, name="mensaje"),
    path('historial/', vchatbot.chat_historial, name="historial"),
    path('limpiar/', vchatbot.chat_limpiar, name="limpiar"),
]
