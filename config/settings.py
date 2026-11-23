from pathlib import Path
import os
from dotenv import load_dotenv
from django.contrib.messages import constants as message_constants

# Carga las variables definidas en tu archivo .env
load_dotenv()

# Ruta base del proyecto (carpeta donde está manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargamos las variables del archivo .env (está junto a manage.py y NO se sube a GitHub)
load_dotenv(os.path.join(BASE_DIR, '.env'))
# Creamos una ruta para nuestros html
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

# Configuración sensible leída desde .env
SECRET_KEY = os.getenv('SECRET_KEY')

# DEBUG = True es necesario para que runserver sirva los archivos de /static
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Direcciones desde las que se puede entrar (en EC2 se agrega la IP pública)
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'UsuarioApp',
    'IndicadoresApp',
    'ActividadesApp',
    'AuditoriaApp',
    'ChatbotApp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [TEMPLATES_DIR],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.debug',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'UsuarioApp.context_processors.delegaciones_navbar',
                'UsuarioApp.context_processors.alertas_validacion',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Base de datos MySQL / MariaDB (datos de conexión en .env)

DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE'),
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
        'OPTIONS': {
            # WAMP trae MyISAM como motor por defecto: se fuerza InnoDB (transacciones y llaves foraneas)
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES', default_storage_engine=INNODB",
            'charset': 'utf8mb4',
        },
    }
}

# Todas las llaves primarias serán bigint (como en el modelo físico)
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Usuario personalizado: la tabla "usuario" reemplaza a auth_user
AUTH_USER_MODEL = 'UsuarioApp.Usuario'

# Si alguien entra sin sesión, se le envía al login
LOGIN_URL = 'users:login'

# Correo (recuperación de contraseña). Usuario y clave se leen del .env: en Gmail es una
# "contraseña de aplicación" (requiere verificación en dos pasos). Si el .env no trae usuario,
# el correo se imprime en la terminal (backend de consola), útil mientras se programa.
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
if EMAIL_HOST_USER:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT') or '587')  # 'or': si en el .env queda EMAIL_PORT= vacío, usa 587
# 587 usa TLS (STARTTLS). Si la red bloquea el 587, se puede usar 465 con SSL: EMAIL_PORT=465 en el .env
EMAIL_USE_SSL = EMAIL_PORT == 465
EMAIL_USE_TLS = not EMAIL_USE_SSL
EMAIL_TIMEOUT = 20  # segundos: si el servidor de correo no responde, falla rápido en vez de colgar la página
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'no-responder@laserena.cl')

# El enlace para crear una contraseña nueva vence en 2 horas (en segundos)
PASSWORD_RESET_TIMEOUT = 2 * 60 * 60


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        # Propio: mayúscula, minúscula, número y símbolo especial (UsuarioApp/validators.py)
        'NAME': 'UsuarioApp.validators.ContrasenaSeguraValidator',
    },
]


# Internationalization

LANGUAGE_CODE = 'es-cl'

TIME_ZONE = 'America/Santiago'

USE_I18N = True

USE_TZ = True


# Archivos estáticos (CSS, JavaScript, Imágenes)
# El styles.css vive en Proyecto/static/css/styles.css

STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Archivos subidos por los usuarios (fotografías de evidencia)
MEDIA_URL = 'media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Tamaño máximo de una fotografía de evidencia (5 MB)
MAX_IMAGEN_EVIDENCIA = 5 * 1024 * 1024

# messages.error se muestra con la clase de Bootstrap "alert-danger"
MESSAGE_TAGS = {message_constants.ERROR: 'danger'}


# Chatbot con IA: la clave NUNCA se expone al navegador, solo la usa el servidor en ChatbotApp/cliente_ia.py.
# Si no hay proveedor configurado (ni API ni modelo local), el chatbot se desactiva y el endpoint responde 503
# (el widget se muestra solo a los roles con acceso, así que el aviso aparece dentro del panel de chat).
# La URL debe hablar la API "OpenAI Chat Completions" (OpenAI, OpenRouter, Groq, Gemini compatible).
CHATBOT_API_KEY = os.getenv('CHATBOT_API_KEY', '')
CHATBOT_API_URL = os.getenv('CHATBOT_API_URL', 'https://api.openai.com/v1/chat/completions')
# Modelo de la API remota. Si queda vacío se usa el modelo local configurado más abajo (Ollama).
CHATBOT_MODEL = os.getenv('CHATBOT_MODEL', 'gpt-4o-mini')
CHATBOT_TIMEOUT = int(os.getenv('CHATBOT_TIMEOUT') or '30')  # segundos: igual que EMAIL_PORT, 'or' cubre la variable vacía
# Alternativa local (Ollama u otro servidor compatible): se usa cuando no hay modelo de API configurado.
# Ollama no valida la clave, así que aquí no se necesita CHATBOT_API_KEY.
CHATBOT_LOCAL_API_URL = os.getenv('CHATBOT_LOCAL_API_URL', 'http://127.0.0.1:11434/v1/chat/completions')
CHATBOT_LOCAL_MODEL = os.getenv('CHATBOT_LOCAL_MODEL', '')
CHATBOT_LOCAL_TIMEOUT = int(os.getenv('CHATBOT_LOCAL_TIMEOUT') or '120')  # un modelo local puede tardar más
# Modelos locales de razonamiento: con 'none' la respuesta llega en 'content' y no solo en 'reasoning'.
# Dejar vacío para no enviar el parámetro (otros servidores locales podrían no aceptarlo).
CHATBOT_LOCAL_REASONING_EFFORT = os.getenv('CHATBOT_LOCAL_REASONING_EFFORT', 'none')
CHATBOT_ACTIVO = bool((CHATBOT_API_KEY and CHATBOT_MODEL) or CHATBOT_LOCAL_MODEL)
CHATBOT_MAX_MENSAJE = 2000    # caracteres máximos por pregunta del usuario
CHATBOT_MAX_HISTORIAL = 12    # mensajes (6 turnos) que se envían al proveedor como contexto
CHATBOT_MAX_HISTORIAL_MENSAJE = int(os.getenv('CHATBOT_MAX_HISTORIAL_MENSAJE') or '1000')   # tope por mensaje del historial
CHATBOT_MAX_HISTORIAL_CARACTERES = int(os.getenv('CHATBOT_MAX_HISTORIAL_CARACTERES') or '4000')  # presupuesto total del historial
# Techo duro del prompt completo (prompt de sistema + contexto + historial + pregunta). Al superarlo
# se descarta primero el historial más antiguo y luego se recorta el contexto; la pregunta nunca se
# recorta (ya está acotada por CHATBOT_MAX_MENSAJE). Rollback: subirlo por `.env`.
CHATBOT_MAX_PROMPT_CARACTERES = int(os.getenv('CHATBOT_MAX_PROMPT_CARACTERES') or '20000')

# ----- Retención y tope de historial (T-C-04) -----
# La purga se ejecuta con `manage.py purgar_chatbot`; programarla (cron/systemd timer) es una
# decisión de Operaciones y no se activa desde el código. Los mensajes se borran por antigüedad y
# cada usuario conserva como máximo los N más recientes.
CHATBOT_RETENCION_MENSAJES_DIAS = int(os.getenv('CHATBOT_RETENCION_MENSAJES_DIAS') or '90')
CHATBOT_RETENCION_EVENTOS_DIAS = int(os.getenv('CHATBOT_RETENCION_EVENTOS_DIAS') or '365')
CHATBOT_MAX_MENSAJES_POR_USUARIO = int(os.getenv('CHATBOT_MAX_MENSAJES_POR_USUARIO') or '200')

# ----- Fase 2: RAG, caché por usuario y observabilidad -----
# Versión del prompt de sistema: se incrementa al cambiarlo y queda en cada EventoChatbot y en la clave de caché.
CHATBOT_PROMPT_VERSION = os.getenv('CHATBOT_PROMPT_VERSION', '2.1')
# Guardrail de entrada: 'completo' (multicapa) o 'basico' (los 9 patrones históricos, rollback).
CHATBOT_GUARDRAIL_MODO = os.getenv('CHATBOT_GUARDRAIL_MODO', 'completo').strip().lower()
CHATBOT_CACHE_TTL = int(os.getenv('CHATBOT_CACHE_TTL') or '600')          # segundos de vida de una respuesta cacheada
# Mensajes recientes del historial que entran en la huella de la clave de caché (0 = sin historial).
# Incluirlos evita servir respuestas de otra conversación, pero baja la tasa de acierto: cada turno
# cambia la huella. Valor configurable (4 = dos turnos completos).
CHATBOT_CACHE_HISTORIAL_MENSAJES = int(os.getenv('CHATBOT_CACHE_HISTORIAL_MENSAJES') or '4')
CHATBOT_RATE_LIMIT = int(os.getenv('CHATBOT_RATE_LIMIT') or '30')         # consultas permitidas por ventana
CHATBOT_RATE_VENTANA = int(os.getenv('CHATBOT_RATE_VENTANA') or '3600')   # segundos de la ventana del rate limit
# Backend del rate limit: 'db' (contador compartido por todos los procesos, recomendado) o 'cache'
# (LocMemCache por proceso, solo para desarrollo/rollback).
CHATBOT_RATE_BACKEND = os.getenv('CHATBOT_RATE_BACKEND', 'db').strip().lower()
CHATBOT_RAG_MAX_CARACTERES = int(os.getenv('CHATBOT_RAG_MAX_CARACTERES') or '4000')  # presupuesto del contexto RAG
CHATBOT_MAX_RESPUESTA = int(os.getenv('CHATBOT_MAX_RESPUESTA') or '4000')            # tope de la respuesta saneada
# Canarios sintéticos (CSV) que el saneo de salida debe redactar siempre. Vacío por defecto.
CHATBOT_CANARIOS = os.getenv('CHATBOT_CANARIOS', '')

# Caché en memoria del proceso (sin dependencias). LocMemCache es por proceso: con varios workers
# la caché de respuestas no se comparte entre ellos (solo afecta rendimiento, no el rate limit, que
# por defecto vive en la BD). Trade-off documentado en docs/chatbot.md.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'sgr-chatbot',
        'TIMEOUT': CHATBOT_CACHE_TTL,
    }
}

# Carpeta de logs del chatbot: se crea sola al arrancar (no se versiona, ver .gitignore).
LOGS_DIR = BASE_DIR / 'logs'
try:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Sin permisos de escritura la aplicación sigue funcionando: el logger escribe solo en consola.
    pass

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'chatbot': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
    },
    'handlers': {
        'chatbot_consola': {
            'class': 'logging.StreamHandler',
            'formatter': 'chatbot',
        },
        'chatbot_archivo': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'chatbot.log'),
            'maxBytes': 1024 * 1024,   # 1 MB
            'backupCount': 5,
            'encoding': 'utf-8',
            'formatter': 'chatbot',
        },
    },
    'loggers': {
        'chatbot': {
            'handlers': ['chatbot_consola', 'chatbot_archivo'],
            'level': os.getenv('CHATBOT_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}
