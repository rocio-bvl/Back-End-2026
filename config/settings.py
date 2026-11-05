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
