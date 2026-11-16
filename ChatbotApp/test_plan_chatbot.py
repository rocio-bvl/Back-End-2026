"""Plan de Pruebas Unitarias: chatbot con IA (CP-CHAT).

La llamada al proveedor SIEMPRE se mockea: ninguna prueba usa la red ni una ApiKey real.
"""
import json
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from AuditoriaApp.models import Auditoria
from ChatbotApp import cliente_ia
from ChatbotApp.cliente_ia import ErrorProveedorIA, MENSAJE_ERROR, PROMPT_SISTEMA
from ChatbotApp.models import MensajeChat
from UsuarioApp.models import Usuario
from UsuarioApp.tests import crear_datos_base, crear_usuario, CLAVE

# El endpoint solo funciona con el chatbot activo: en las pruebas se simula la clave configurada.
# El modelo local se deja vacío para que las pruebas no dependan del `.env` real ni de Ollama.
CHATBOT_DE_PRUEBA = dict(
    CHATBOT_ACTIVO=True,
    CHATBOT_API_KEY='clave-solo-para-pruebas',
    CHATBOT_API_URL='https://proveedor.test/v1/chat/completions',
    CHATBOT_MODEL='modelo-de-prueba',
    CHATBOT_TIMEOUT=5,
    CHATBOT_LOCAL_API_URL='http://127.0.0.1:11434/v1/chat/completions',
    CHATBOT_LOCAL_MODEL='',
    CHATBOT_LOCAL_TIMEOUT=5,
    CHATBOT_LOCAL_REASONING_EFFORT='none',
    CHATBOT_MAX_MENSAJE=2000,
    CHATBOT_MAX_HISTORIAL=12,
)


def enviar(cliente, mensaje, **extra):
    datos = {'mensaje': mensaje} if not extra else extra
    return cliente.post(reverse('chatbot:mensaje'), data=json.dumps(datos), content_type='application/json')


class RespuestaFalsa:
    """Imita la respuesta de urllib.request.urlopen: se usa como context manager y tiene read()."""

    def __init__(self, cuerpo):
        if isinstance(cuerpo, bytes):
            self.cuerpo = cuerpo
        else:
            self.cuerpo = json.dumps(cuerpo).encode('utf-8')

    def read(self):
        return self.cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class BaseChatbotTest(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()
        self.admin = crear_usuario('11111111-1', 'Admin', self.datos['delegacion'], self.datos['cargo'])
        self.coordinador = crear_usuario('22222222-2', 'Coordinador', self.datos['delegacion'])
        self.delegado = crear_usuario('33333333-3', 'Delegado', self.datos['delegacion'])
        self.funcionario = crear_usuario('55555555-5', 'Funcionario', self.datos['delegacion'], self.datos['cargo'])
        self.superusuario = Usuario.objects.create_superuser(
            username='99999999-9', password=CLAVE, email='superusuario@laserena.cl')


@override_settings(**CHATBOT_DE_PRUEBA)
class PlanChatbotPermisosTest(BaseChatbotTest):
    """CP-CHAT-001 a CP-CHAT-008: widget y permisos por rol."""

    def test_cp_chat_001_funcionario_post_mensaje_403_y_auditoria(self):
        self.client.login(username='55555555-5', password=CLAVE)
        respuesta = enviar(self.client, '¿Cómo registro una actividad?')
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(respuesta.json()['error'], 'No tienes permisos para usar el asistente.')
        registro = Auditoria.objects.get(evento='ACCESO_DENEGADO', entidad='Chatbot', usuario=self.funcionario)
        self.assertEqual(registro.valor_nuevo, 'Intento de uso del chatbot')
        self.assertEqual(registro.id_entidad, reverse('chatbot:mensaje')[:50])

    def test_cp_chat_002_funcionario_historial_y_limpiar_403(self):
        self.client.login(username='55555555-5', password=CLAVE)
        self.assertEqual(self.client.get(reverse('chatbot:historial')).status_code, 403)
        self.assertEqual(self.client.post(reverse('chatbot:limpiar')).status_code, 403)
        self.assertEqual(Auditoria.objects.filter(evento='ACCESO_DENEGADO', entidad='Chatbot').count(), 2)

    def test_cp_chat_003_anonimo_va_al_login(self):
        respuesta = enviar(self.client, 'Hola')
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse('users:login'), respuesta.url)
        respuesta = self.client.get(reverse('chatbot:historial'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse('users:login'), respuesta.url)

    def test_cp_chat_004_roles_habilitados_consultan_historial(self):
        for rut in ['11111111-1', '22222222-2', '33333333-3', '99999999-9']:
            self.client.login(username=rut, password=CLAVE)
            respuesta = self.client.get(reverse('chatbot:historial'))
            self.assertEqual(respuesta.status_code, 200, rut)
            self.assertEqual(respuesta.json(), {'mensajes': []})

    def test_cp_chat_005_roles_habilitados_envian_mensaje(self):
        for rut in ['11111111-1', '22222222-2', '33333333-3', '99999999-9']:
            self.client.login(username=rut, password=CLAVE)
            MensajeChat.objects.all().delete()
            with patch('ChatbotApp.views.responder', return_value='Respuesta simulada'):
                respuesta = enviar(self.client, 'Hola asistente')
            self.assertEqual(respuesta.status_code, 200, rut)
            self.assertEqual(respuesta.json()['respuesta'], 'Respuesta simulada')

    def test_cp_chat_006_widget_visible_para_admin(self):
        self.client.login(username='11111111-1', password=CLAVE)
        respuesta = self.client.get(reverse('actividades:mi_gestion'))
        self.assertContains(respuesta, 'id="chatbotWidget"')
        self.assertContains(respuesta, 'js/chatbot.js')
        self.assertContains(respuesta, 'css/chatbot.css')

    def test_cp_chat_007_widget_oculto_para_funcionario(self):
        self.client.login(username='55555555-5', password=CLAVE)
        respuesta = self.client.get(reverse('actividades:mi_gestion'))
        self.assertNotContains(respuesta, 'id="chatbotWidget"')
        self.assertNotContains(respuesta, 'js/chatbot.js')

    def test_cp_chat_008_widget_oculto_para_anonimo(self):
        # Sin sesión no hay página que extienda base.html: el login es propio y el resto redirige.
        # El widget se condiciona con user.puede_usar_chatbot, que un AnonymousUser no cumple.
        respuesta = self.client.get(reverse('users:login'))
        self.assertNotContains(respuesta, 'id="chatbotWidget"')
        self.assertNotContains(respuesta, 'js/chatbot.js')


@override_settings(**CHATBOT_DE_PRUEBA)
class PlanChatbotMensajeTest(BaseChatbotTest):
    """CP-CHAT-009 a CP-CHAT-018: endpoint de mensaje, validaciones y errores."""

    def setUp(self):
        super().setUp()
        self.client.login(username='11111111-1', password=CLAVE)

    def test_cp_chat_009_mensaje_exitoso(self):
        with patch('ChatbotApp.views.responder', return_value='Registra la actividad en Mi Gestión.') as simulado:
            respuesta = enviar(self.client, '  ¿Cómo registro una actividad?  ')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['respuesta'], 'Registra la actividad en Mi Gestión.')
        self.assertIn('fecha', respuesta.json())
        guardados = list(MensajeChat.objects.filter(usuario=self.admin).order_by('id'))
        self.assertEqual([m.emisor for m in guardados], ['USUARIO', 'ASISTENTE'])
        self.assertEqual(guardados[0].contenido, '¿Cómo registro una actividad?')
        self.assertEqual(guardados[1].contenido, 'Registra la actividad en Mi Gestión.')
        # El contexto enviado al proveedor lleva el rol de cada mensaje
        self.assertEqual(simulado.call_args[0][0],
                         [{'role': 'user', 'content': '¿Cómo registro una actividad?'}])

    def test_cp_chat_010_contexto_recortado_al_maximo(self):
        for numero in range(20):
            MensajeChat.objects.create(usuario=self.admin, emisor='USUARIO', contenido=f"pregunta {numero}")
        with patch('ChatbotApp.views.responder', return_value='ok') as simulado:
            with override_settings(CHATBOT_MAX_HISTORIAL=4):
                respuesta = enviar(self.client, 'pregunta final')
        self.assertEqual(respuesta.status_code, 200)
        contexto = simulado.call_args[0][0]
        self.assertEqual(len(contexto), 4)
        self.assertEqual(contexto[-1], {'role': 'user', 'content': 'pregunta final'})
        self.assertTrue(all(mensaje['role'] in ('user', 'assistant') for mensaje in contexto))

    def test_cp_chat_011_json_invalido_400(self):
        respuesta = self.client.post(reverse('chatbot:mensaje'), data='esto no es json',
                                     content_type='application/json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('error', respuesta.json())
        self.assertFalse(MensajeChat.objects.exists())

    def test_cp_chat_012_mensaje_vacio_400(self):
        for valor in ['', '   ', None]:
            respuesta = enviar(self.client, valor)
            self.assertEqual(respuesta.status_code, 400, valor)
        respuesta = self.client.post(reverse('chatbot:mensaje'), data=json.dumps({'otro': 'x'}),
                                     content_type='application/json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(MensajeChat.objects.exists())

    def test_cp_chat_013_mensaje_demasiado_largo_400(self):
        respuesta = enviar(self.client, 'a' * 2001)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('2000', respuesta.json()['error'])
        self.assertFalse(MensajeChat.objects.exists())

    @override_settings(CHATBOT_ACTIVO=False)
    def test_cp_chat_014_sin_clave_configurada_503(self):
        with patch('ChatbotApp.views.responder', return_value='no debería llamarse') as simulado:
            respuesta = enviar(self.client, 'Hola')
        self.assertEqual(respuesta.status_code, 503)
        self.assertIn('error', respuesta.json())
        simulado.assert_not_called()
        self.assertFalse(MensajeChat.objects.exists())

    def test_cp_chat_015_error_del_proveedor_502_sin_respuesta(self):
        with patch('ChatbotApp.views.responder', side_effect=ErrorProveedorIA(MENSAJE_ERROR)):
            respuesta = enviar(self.client, 'Hola')
        self.assertEqual(respuesta.status_code, 502)
        self.assertEqual(respuesta.json()['error'], MENSAJE_ERROR)
        guardados = list(MensajeChat.objects.filter(usuario=self.admin))
        self.assertEqual([m.emisor for m in guardados], ['USUARIO'])

    def test_cp_chat_016_get_a_endpoint_de_mensaje_no_permitido(self):
        self.assertEqual(self.client.get(reverse('chatbot:mensaje')).status_code, 405)

    def test_cp_chat_017_csrf_sin_token_403(self):
        cliente = Client(enforce_csrf_checks=True)
        self.assertTrue(cliente.login(username='11111111-1', password=CLAVE))
        respuesta = cliente.post(reverse('chatbot:mensaje'), data=json.dumps({'mensaje': 'Hola'}),
                                 content_type='application/json')
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(MensajeChat.objects.exists())

    def test_cp_chat_018_csrf_con_token_valido(self):
        cliente = Client(enforce_csrf_checks=True)
        self.assertTrue(cliente.login(username='11111111-1', password=CLAVE))
        cliente.get(reverse('actividades:mi_gestion'))   # la página entrega la cookie csrftoken
        token = cliente.cookies['csrftoken'].value
        with patch('ChatbotApp.views.responder', return_value='ok'):
            respuesta = cliente.post(reverse('chatbot:mensaje'), data=json.dumps({'mensaje': 'Hola'}),
                                     content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(respuesta.status_code, 200)


@override_settings(**CHATBOT_DE_PRUEBA)
class PlanChatbotHistorialTest(BaseChatbotTest):
    """CP-CHAT-019 a CP-CHAT-022: historial y nueva conversación."""

    def test_cp_chat_019_historial_en_orden_cronologico(self):
        MensajeChat.objects.create(usuario=self.admin, emisor='USUARIO', contenido='primera')
        MensajeChat.objects.create(usuario=self.admin, emisor='ASISTENTE', contenido='segunda')
        MensajeChat.objects.create(usuario=self.admin, emisor='USUARIO', contenido='tercera')
        MensajeChat.objects.create(usuario=self.delegado, emisor='USUARIO', contenido='de otro usuario')
        self.client.login(username='11111111-1', password=CLAVE)
        respuesta = self.client.get(reverse('chatbot:historial'))
        self.assertEqual(respuesta.status_code, 200)
        mensajes = respuesta.json()['mensajes']
        self.assertEqual([m['contenido'] for m in mensajes], ['primera', 'segunda', 'tercera'])
        self.assertEqual([m['emisor'] for m in mensajes], ['USUARIO', 'ASISTENTE', 'USUARIO'])
        self.assertEqual(set(mensajes[0].keys()), {'emisor', 'contenido', 'fecha'})

    def test_cp_chat_020_historial_solo_del_usuario_autenticado(self):
        MensajeChat.objects.create(usuario=self.admin, emisor='USUARIO', contenido='del admin')
        MensajeChat.objects.create(usuario=self.delegado, emisor='USUARIO', contenido='del delegado')
        self.client.login(username='33333333-3', password=CLAVE)
        mensajes = self.client.get(reverse('chatbot:historial')).json()['mensajes']
        self.assertEqual([m['contenido'] for m in mensajes], ['del delegado'])

    def test_cp_chat_021_limpiar_borra_solo_los_del_usuario(self):
        MensajeChat.objects.create(usuario=self.admin, emisor='USUARIO', contenido='del admin')
        MensajeChat.objects.create(usuario=self.delegado, emisor='USUARIO', contenido='del delegado')
        self.client.login(username='11111111-1', password=CLAVE)
        respuesta = self.client.post(reverse('chatbot:limpiar'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {'ok': True})
        self.assertFalse(MensajeChat.objects.filter(usuario=self.admin).exists())
        self.assertTrue(MensajeChat.objects.filter(usuario=self.delegado).exists())

    def test_cp_chat_022_historial_acotado_a_los_ultimos_50(self):
        for numero in range(60):
            MensajeChat.objects.create(usuario=self.admin, emisor='USUARIO', contenido=f"mensaje {numero}")
        self.client.login(username='11111111-1', password=CLAVE)
        mensajes = self.client.get(reverse('chatbot:historial')).json()['mensajes']
        self.assertEqual(len(mensajes), 50)
        self.assertEqual(mensajes[0]['contenido'], 'mensaje 10')
        self.assertEqual(mensajes[-1]['contenido'], 'mensaje 59')


@override_settings(**CHATBOT_DE_PRUEBA)
class PlanChatbotClienteIATest(TestCase):
    """CP-CHAT-023 a CP-CHAT-029: cliente HTTP unitario (urllib mockeado, sin red real)."""

    def test_cp_chat_023_payload_con_modelo_sistema_y_roles(self):
        respuesta = {'choices': [{'message': {'content': 'Hola, ¿en qué te ayudo?'}}]}
        with patch('ChatbotApp.cliente_ia.urllib.request.urlopen', return_value=RespuestaFalsa(respuesta)) as simulado:
            texto = cliente_ia.responder([
                {'role': 'user', 'content': '¿Cómo valido una evidencia?'},
                {'role': 'assistant', 'content': 'Desde Verificación.'},
                {'role': 'user', 'content': '¿Y quién puede?'},
            ])
        self.assertEqual(texto, 'Hola, ¿en qué te ayudo?')
        peticion = simulado.call_args[0][0]
        self.assertEqual(peticion.full_url, CHATBOT_DE_PRUEBA['CHATBOT_API_URL'])
        self.assertEqual(peticion.get_method(), 'POST')
        self.assertEqual(peticion.get_header('Authorization'), 'Bearer ' + CHATBOT_DE_PRUEBA['CHATBOT_API_KEY'])
        self.assertIn('application/json', peticion.get_header('Content-type'))
        self.assertEqual(simulado.call_args[1]['timeout'], CHATBOT_DE_PRUEBA['CHATBOT_TIMEOUT'])

        cuerpo = json.loads(peticion.data.decode('utf-8'))
        self.assertEqual(cuerpo['model'], 'modelo-de-prueba')
        self.assertEqual(cuerpo['temperature'], 0.3)
        self.assertEqual(cuerpo['max_tokens'], 600)
        self.assertEqual(cuerpo['messages'][0], {'role': 'system', 'content': PROMPT_SISTEMA})
        self.assertEqual([m['role'] for m in cuerpo['messages'][1:]], ['user', 'assistant', 'user'])
        self.assertIn('Municipalidad de La Serena', cuerpo['messages'][0]['content'])
        self.assertIn('español', cuerpo['messages'][0]['content'])

    def test_cp_chat_024_sin_historial_envia_solo_el_sistema(self):
        respuesta = {'choices': [{'message': {'content': 'ok'}}]}
        with patch('ChatbotApp.cliente_ia.urllib.request.urlopen', return_value=RespuestaFalsa(respuesta)) as simulado:
            cliente_ia.responder([])
        cuerpo = json.loads(simulado.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(len(cuerpo['messages']), 1)
        self.assertEqual(cuerpo['messages'][0]['role'], 'system')

    def test_cp_chat_025_sin_clave_lanza_error_sin_llamar_al_proveedor(self):
        with override_settings(CHATBOT_API_KEY='', CHATBOT_ACTIVO=False):
            with patch('ChatbotApp.cliente_ia.urllib.request.urlopen') as simulado:
                with self.assertRaises(ErrorProveedorIA):
                    cliente_ia.responder([{'role': 'user', 'content': 'Hola'}])
        simulado.assert_not_called()

    def test_cp_chat_026_json_invalido_lanza_error_generico(self):
        with patch('ChatbotApp.cliente_ia.urllib.request.urlopen',
                   return_value=RespuestaFalsa(b'<html>no es json</html>')):
            with self.assertRaises(ErrorProveedorIA) as contexto:
                cliente_ia.responder([{'role': 'user', 'content': 'Hola'}])
        self.assertEqual(str(contexto.exception), MENSAJE_ERROR)
        self.assertNotIn(CHATBOT_DE_PRUEBA['CHATBOT_API_KEY'], str(contexto.exception))

    def test_cp_chat_027_estructura_inesperada_lanza_error(self):
        for cuerpo in [{}, {'choices': []}, {'choices': [{'message': {}}]}, {'error': 'cuota'}]:
            with patch('ChatbotApp.cliente_ia.urllib.request.urlopen', return_value=RespuestaFalsa(cuerpo)):
                with self.assertRaises(ErrorProveedorIA):
                    cliente_ia.responder([{'role': 'user', 'content': 'Hola'}])

    def test_cp_chat_028_http_error_lanza_error_sin_filtrar_detalle(self):
        import urllib.error
        error = urllib.error.HTTPError('https://proveedor.test', 401, 'Unauthorized', {}, None)
        with patch('ChatbotApp.cliente_ia.urllib.request.urlopen', side_effect=error):
            with self.assertRaises(ErrorProveedorIA) as contexto:
                cliente_ia.responder([{'role': 'user', 'content': 'Hola'}])
        self.assertEqual(str(contexto.exception), MENSAJE_ERROR)
        self.assertNotIn('Bearer', str(contexto.exception))
        self.assertNotIn(CHATBOT_DE_PRUEBA['CHATBOT_API_KEY'], str(contexto.exception))

    def test_cp_chat_029_red_caida_o_timeout_lanza_error(self):
        import urllib.error
        for excepcion in [urllib.error.URLError('sin salida'), TimeoutError('timeout')]:
            with patch('ChatbotApp.cliente_ia.urllib.request.urlopen', side_effect=excepcion):
                with self.assertRaises(ErrorProveedorIA) as contexto:
                    cliente_ia.responder([{'role': 'user', 'content': 'Hola'}])
            self.assertEqual(str(contexto.exception), MENSAJE_ERROR)

    def test_cp_chat_030_sin_modelo_de_api_usa_el_modelo_local(self):
        respuesta = {'choices': [{'message': {'content': 'Hola desde Ollama'}}]}
        with override_settings(
            CHATBOT_API_KEY='',
            CHATBOT_MODEL='',
            CHATBOT_LOCAL_API_URL='http://127.0.0.1:11434/v1/chat/completions',
            CHATBOT_LOCAL_MODEL='modelo-local',
            CHATBOT_LOCAL_TIMEOUT=90,
        ):
            with patch('ChatbotApp.cliente_ia.urllib.request.urlopen',
                       return_value=RespuestaFalsa(respuesta)) as simulado:
                texto = cliente_ia.responder([{'role': 'user', 'content': 'Hola'}])

        self.assertEqual(texto, 'Hola desde Ollama')
        peticion = simulado.call_args[0][0]
        self.assertEqual(peticion.full_url, 'http://127.0.0.1:11434/v1/chat/completions')
        self.assertIsNone(peticion.get_header('Authorization'))
        cuerpo = json.loads(peticion.data.decode('utf-8'))
        self.assertEqual(cuerpo['model'], 'modelo-local')
        self.assertEqual(cuerpo['reasoning_effort'], 'none')
        self.assertEqual(simulado.call_args[1]['timeout'], 90)

    def test_cp_chat_031_la_api_remota_tiene_prioridad_sobre_el_modelo_local(self):
        respuesta = {'choices': [{'message': {'content': 'Hola desde la API'}}]}
        with override_settings(CHATBOT_LOCAL_MODEL='modelo-local',
                               CHATBOT_LOCAL_API_URL='http://127.0.0.1:11434/v1/chat/completions'):
            with patch('ChatbotApp.cliente_ia.urllib.request.urlopen',
                       return_value=RespuestaFalsa(respuesta)) as simulado:
                texto = cliente_ia.responder([{'role': 'user', 'content': 'Hola'}])

        self.assertEqual(texto, 'Hola desde la API')
        peticion = simulado.call_args[0][0]
        self.assertEqual(peticion.full_url, CHATBOT_DE_PRUEBA['CHATBOT_API_URL'])
        self.assertEqual(peticion.get_header('Authorization'),
                         'Bearer ' + CHATBOT_DE_PRUEBA['CHATBOT_API_KEY'])
        cuerpo = json.loads(peticion.data.decode('utf-8'))
        self.assertEqual(cuerpo['model'], 'modelo-de-prueba')
        # El parámetro de razonamiento es solo para el proveedor local
        self.assertNotIn('reasoning_effort', cuerpo)

    def test_cp_chat_032_sin_api_ni_modelo_local_lanza_error_sin_llamar(self):
        with override_settings(CHATBOT_API_KEY='', CHATBOT_MODEL='', CHATBOT_LOCAL_MODEL=''):
            with patch('ChatbotApp.cliente_ia.urllib.request.urlopen') as simulado:
                with self.assertRaises(ErrorProveedorIA) as contexto:
                    cliente_ia.responder([{'role': 'user', 'content': 'Hola'}])
        self.assertEqual(str(contexto.exception), MENSAJE_ERROR)
        simulado.assert_not_called()
