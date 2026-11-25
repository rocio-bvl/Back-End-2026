# SGR: Sistema de Gestión de Resultados, Municipalidad de La Serena

Aplicación web en Django para registrar la gestión territorial de los funcionarios municipales: actividades con evidencia, compromisos del Tubo de Trabajo, registro de atenciones sociales, verificación de la ejecución, metas trimestrales con semáforo de cumplimiento y auditoría de cambios.

Todas las operaciones se hacen desde pantallas propias del sistema (Django Templates). Django Admin queda solo como herramienta técnica del superusuario.

Asignatura: Programación Back End (TI3041), INACAP La Serena.
Integrantes: Juliet Araya y Rocío Vásquez.

## Tecnologías

- Python 3.11 y Django 4.2 LTS
- MariaDB 10.11 en contenedor y `mysqlclient`
- Docker y Docker Compose: Gunicorn como servidor de aplicación y Nginx como proxy inverso con HTTPS
- Bootstrap 5.3, Bootstrap Icons, SweetAlert2 y framework visual de la Municipalidad de La Serena
- `python-dotenv` para las variables de entorno
- `openpyxl` para la carga de datos desde planillas

## Despliegue con Docker Compose

El proyecto se levanta con tres servicios definidos en `docker-compose.yml`:

| Servicio | Imagen / construcción | Función |
|---|---|---|
| `db` | `mariadb:10.11` | Base de datos; persiste en el volumen `mariadb_data` |
| `web` | `Dockerfile` (Python 3.11) | Django con Gunicorn en el puerto interno `8000` |
| `nginx` | `nginx:alpine` | Publica los puertos `80` y `443`, sirve estáticos y multimedia |

### Requisitos

- Docker Engine y Docker Compose v2 (`docker compose`)
- Git y OpenSSL
- Puertos `80` y `443` libres en el servidor

### 1. Clonar la rama de despliegue

Los archivos de Docker están versionados en la rama `produccion`:

```
git clone -b produccion https://github.com/rocio-bvl/Back-End-2026.git
cd Back-End-2026
```

> `main` no incluye `Dockerfile`, `docker-compose.yml` ni `nginx/`. Para desplegar con Docker se debe usar la rama `produccion`.

### 2. Crear el certificado SSL

`docker-compose.yml` monta `./nginx/ssl` en el contenedor y `nginx/default.conf` espera `selfsigned.crt` y `selfsigned.key`. Los certificados no vienen en el repositorio porque `.gitignore` excluye `*.crt` y `*.key`; hay que generarlos antes de levantar los servicios:

```
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/selfsigned.key \
  -out nginx/ssl/selfsigned.crt \
  -subj "/CN=localhost"
```

Para un dominio o una IP pública, cambie `CN=localhost` por el nombre correspondiente. Al ser un certificado autofirmado, el navegador mostrará una advertencia que se debe aceptar.

### 3. Configurar las variables de entorno

```
cp .env.example .env
```

Edite `.env`. Para Docker, como mínimo deben quedar así:

```
SECRET_KEY='una-clave-larga-y-aleatoria'
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,IP_O_DOMINIO

DB_ENGINE=django.db.backends.mysql
DB_NAME=municipalidad
DB_USER=admin_muni
DB_PASSWORD='tu_clave'
DB_HOST=db
DB_PORT=3306

MYSQL_ROOT_PASSWORD='tu_clave_root'
```

Consideraciones importantes:

- `DB_HOST=db` es obligatorio dentro de Docker; no use `127.0.0.1`, porque dentro del contenedor `web` esa dirección apunta al propio contenedor.
- `MYSQL_ROOT_PASSWORD` lo usa el contenedor `db`. No aparece en `.env.example`, así que agréguelo al `.env`.
- `DB_PASSWORD` y `MYSQL_ROOT_PASSWORD` deben estar entre comillas si contienen caracteres especiales como `$`.
- Como Nginx redirige todo a HTTPS, conviene activar HTTPS en Django:

```
USAR_HTTPS=True
CSRF_TRUSTED_ORIGINS=https://localhost,https://IP_O_DOMINIO
AUDITORIA_CONFIAR_PROXY=True
```

- `AUDITORIA_CONFIAR_PROXY=True` permite que la auditoría registre la IP real del cliente a través de Nginx.
- `MFA_ACTIVO=False` mientras los correos de los usuarios sean de ejemplo. Si se activa sin correos reales, nadie podrá iniciar sesión.
- El archivo `.env` no se sube al repositorio.

### 4. Levantar los servicios

```
docker compose up -d --build
```

Compruebe que los tres contenedores estén activos:

```
docker compose ps
```

### 5. Preparar la base de datos y los estáticos

La primera vez, el contenedor `db` crea automáticamente la base de datos y el usuario a partir de `DB_NAME`, `DB_USER`, `DB_PASSWORD` y `MYSQL_ROOT_PASSWORD` del `.env`. No es necesario crearlos a mano si el volumen `mariadb_data` está vacío.

Si la base o el usuario no existen (por ejemplo, porque el volumen ya estaba creado o se cambiaron las credenciales), créelos desde el contenedor `db`:

```
docker compose exec db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD"'
```

Dentro de MySQL/MariaDB ejecute, usando los mismos valores del `.env`:

```
CREATE DATABASE IF NOT EXISTS municipalidad CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'admin_muni'@'%' IDENTIFIED BY 'tu_clave';
GRANT ALL PRIVILEGES ON municipalidad.* TO 'admin_muni'@'%';
FLUSH PRIVILEGES;
EXIT;
```

> El host `%` permite que el contenedor `web` se conecte a la base. Reemplace `municipalidad`, `admin_muni` y `tu_clave` por los valores reales de `DB_NAME`, `DB_USER` y `DB_PASSWORD`.

El `docker-compose.yml` no ejecuta migraciones, carga de datos ni `collectstatic` automáticamente. Ejecute estos comandos en orden, la primera vez:

```
docker compose exec web python manage.py migrate

docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < datos_iniciales.sql

docker compose exec web python manage.py crear_grupos

docker compose exec web python manage.py collectstatic --noinput
```

- `datos_iniciales.sql` se importa **una sola vez**, después de `migrate` y sobre una base vacía. Si se importa dos veces fallará por llaves duplicadas.
- `collectstatic` llena el volumen `static_volume` que Nginx sirve en `/static/`.
- `crear_grupos` crea los cuatro grupos de Django, les asigna sus permisos y deja a cada usuario en el grupo de su rol. Se puede repetir después de cada `migrate` que agregue permisos.

### 6. Acceder al sistema

Abra `https://localhost` (o `https://IP_O_DOMINIO`) y acepte la advertencia del certificado autofirmado.

Usuarios de prueba, todos con la contraseña `Serena2026!`:

| RUT | Rol |
|---|---|
| 11111111-1 | Administrador |
| 22222222-2 | Coordinador (Supervisor) |
| 33333333-3 | Delegada de Las Compañías |
| 44444444-4 | Delegado de Rural |
| 14141414-3 | Delegada de La Pampa |
| 55555555-5 | Funcionaria de Las Compañías |
| 66666666-6 | Funcionario de Las Compañías |

`datos_iniciales.sql` incluye además otros funcionarios de ejemplo en Las Compañías, Rural, La Pampa, La Antena y Centro.

### Operación y actualización

```
docker compose logs -f web        # ver registros
docker compose down               # detener sin borrar datos
docker compose down -v            # detener y borrar base de datos, estáticos y multimedia
```

`down -v` elimina los volúmenes `mariadb_data`, `static_volume` y `media_volume`: se pierden la base de datos, las fotografías de evidencia y los estáticos generados.

Para actualizar un despliegue existente:

```
git pull
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py crear_grupos
```

## Instalación local sin Docker (opcional)

1. Crear el entorno virtual e instalar dependencias:

   ```
   python -m venv venv
   source venv/bin/activate       (Linux o Mac)
   venv\Scripts\activate          (Windows)
   pip install -r requirements.txt
   ```

   `mysqlclient` requiere las bibliotecas de desarrollo de MySQL o MariaDB instaladas en el sistema.

2. Crear una base de datos vacía `municipalidad` (utf8mb4) en MySQL o MariaDB.

3. Copiar `.env.example` como `.env` y usar la conexión local:

   ```
   DB_HOST=127.0.0.1
   DB_PORT=3306
   DB_NAME=municipalidad
   DB_USER=admin_muni
   DB_PASSWORD='tu_clave'
   ```

4. Crear las tablas, importar los datos y crear los grupos:

   ```
   python manage.py migrate
   mysql -u root -p municipalidad < datos_iniciales.sql
   python manage.py crear_grupos
   python manage.py runserver
   ```

   También se puede importar `datos_iniciales.sql` desde phpMyAdmin. Debe ser una sola vez y en una base vacía.

5. Entrar en http://127.0.0.1:8000 con los mismos usuarios de prueba.

## Roles, grupos y permisos

Cada rol del negocio queda unido a un grupo de Django con el nombre de perfil que pide la evaluación. Los permisos de cada grupo están en `PERMISOS_POR_GRUPO` (`UsuarioApp/choices.py`).

| Rol del SGR | Grupo de Django | Nivel |
|---|---|---|
| Admin | Administrador | Acceso total (superusuario) |
| Coordinador | Supervisor | Define metas y ponderaciones; gestiona delegaciones, territorios y usuarios; supervisa todas las delegaciones y ve la auditoría |
| Delegado | Delegado | Gestiona su delegación y sus funcionarios; registra sus propias gestiones, valida evidencias y asigna encargados |
| Funcionario | Administrativo | Solo lo propio: actividades y atenciones sociales |

Además de los permisos que Django crea por modelo (`add_`, `change_`, `delete_`, `view_`), hay dos permisos propios: `ActividadesApp.validar_evidencia` y `ActividadesApp.asignar_encargado`.

Las vistas se protegen con `@login_required` o con `@permiso_requerido(permiso, pantalla)` (`UsuarioApp/funciones.py`). Sin sesión, el usuario vuelve al login; sin permiso, vuelve a Mi Gestión con un mensaje y el intento queda en la auditoría como ACCESO_DENEGADO.

| Acción | Admin | Coordinador | Delegado | Funcionario |
|---|:-:|:-:|:-:|:-:|
| Ver actividades | Todas (filtra por delegación) | Todas (filtra por delegación) | Su delegación | Su delegación |
| Registrar actividades | Sí | No | Sí (propias, sin puntaje) | Sí |
| Registrar atenciones sociales | Sí | No | No | Sí |
| Modificar y eliminar actividades | Sí | No | No | No |
| Validar o rechazar la ejecución | Sí | No | Sí (su delegación) | No |
| Asignar encargado a una actividad pendiente | Sí | Sí | Sí (su delegación) | Al registrar, de su delegación |
| Ver la pantalla de Administración | Sí | Sí | Sí (su delegación) | No |
| Crear, editar y desactivar usuarios | Sí (todos) | Sí (Delegados y Funcionarios) | Sí (Funcionarios de su delegación) | No |
| Eliminar usuarios (con confirmación) | Sí, si no tienen registros | No | No | No |
| Agregar, modificar y eliminar delegaciones y territorios | Sí | Sí | No | No |
| Ponderación de cada ítem por cargo (una para toda la municipalidad) | Agrega y edita | Agrega y edita | Visualiza | No |
| Metas generales de la municipalidad | Agrega y edita | Agrega y edita | Visualiza | No |
| Metas propias de una delegación (cambian el valor objetivo de un ítem) | Agrega y edita | Agrega y edita | Visualiza | No |
| Ausencias (vacaciones, días administrativos y licencias) | Sí | Sí | Sí (su delegación) | No |
| Felicitaciones y reclamos | Sí | No | Sí (su delegación) | No |
| Auditoría (solo lectura) | Sí | Sí | No | No |
| Asistente de chat con IA | Sí | Sí | Sí | No |
| Entrar a Django Admin | Sí (superusuario) | No | No | No |

## Funcionalidades

- **Tablero por perfil:** cada grupo tiene su panel de inicio (`dashboard_admin`, `dashboard_coordinador`, `dashboard_delegado` y `dashboard_administrativo`).
- **Mantenedores con crear, buscar, listar, modificar y eliminar:** Usuarios (búsqueda por nombre, RUT o correo), Delegaciones con sus territorios (búsqueda por nombre, ámbito o territorio), Metas (búsqueda por cargo o ítem) y Registro de Atenciones (búsqueda por nombre o RUT). Eliminar siempre pide confirmación.
- **Selector de delegación** en la barra superior: filtra la información por delegación. En Metas, General muestra las metas de toda la municipalidad y una delegación muestra las suyas; el Delegado elige entre General y la suya. Un cargo cuya ponderación no suma 100% no se mide hasta completarla.
- **Transacciones:** registrar una actividad (con su ejecución, si corresponde) y validar o rechazar la ejecución.
- **Tubo de Trabajo:** actividades que dependen de factores externos y que se programan cuando aparece la fecha.
- **Semáforo de cumplimiento:** metas trimestrales, ponderaciones por cargo, resumen por delegación, atrasos de validación y exportación del semáforo.
- **Ausencias:** registro de vacaciones, días administrativos y licencias.
- **Felicitaciones y reclamos:** el Administrador gestiona los de todos los funcionarios y el Delegado los de su delegación; ambos pueden responder los reclamos de su alcance.
- **Auditoría de solo lectura**, con filtros por usuario, evento y fechas.
- **Perfil propio:** cada usuario edita su foto, teléfono y correo desde Editar perfil.

## Recuperación de contraseña y segundo factor

En el login, "¿Olvidaste tu contraseña?" envía un enlace con un token de un solo uso que vence en 2 horas. Se usan las vistas de recuperación de Django con plantillas propias (`templates/users/recuperar*`).

Para enviar correos reales con Gmail se usa una contraseña de aplicación (no la clave normal) en el `.env`:

```
EMAIL_HOST_USER=cuenta@gmail.com
EMAIL_HOST_PASSWORD='contraseña de aplicación'
EMAIL_PORT=587
```

`EMAIL_PORT=587` usa TLS. Si la red bloquea ese puerto, `EMAIL_PORT=465` usa SSL. Si `EMAIL_HOST_USER` queda vacío, el correo se muestra en la terminal en vez de enviarse.

El segundo factor por correo es opcional y se controla con `MFA_ACTIVO=True` en el `.env`. Debe activarse solo cuando los usuarios tengan correos reales y el envío de correo funcione.

Las contraseñas nuevas deben tener mayúscula, minúscula, número y símbolo (`ContrasenaSeguraValidator`, en `UsuarioApp/validators.py`).

## Flujo de una actividad

La **fecha de ingreso** se guarda sola; quien registra elige la **fecha de ejecución**, el **territorio**, opcionalmente un **encargado** (Funcionario de su delegación) y opcionalmente la **solicitud social** a la que responde.

| Caso | Estado inicial |
|---|---|
| Fecha de ejecución hoy o anterior | `REGISTRADA` (en revisión). Comentario obligatorio, foto opcional. |
| Fecha de ejecución posterior a hoy | `PROGRAMADA` (compromiso). |
| Depende de factores externos, sin fecha | `EN_TUBO`. La fecha se agrega después y pasa a `PROGRAMADA`. |
| Depende de factores externos, con fecha | `PROGRAMADA`, y sigue en el Tubo de Trabajo. |

Luego se registra la ejecución, el Delegado valida (`VALIDADA`) o rechaza con motivo (`RECHAZADA`), y se pueden agregar comentarios con fecha en la bitácora. El Administrador puede modificar una actividad no validada (el estado se recalcula) o eliminarla.

## Registro de Atenciones (Gestión Social)

Un funcionario registra la solicitud de una persona natural (fecha y funcionario automáticos). La persona (solicitante) se identifica por su RUT: si ya está registrada, el sistema completa nombre y teléfono; si no, pregunta "¿Desea agregar solicitante al sistema?" y la registra, opcionalmente como presidente, secretario o tesorero de una organización. Sus datos se guardan una sola vez, en la tabla `solicitante`, y las atenciones y actividades la referencian. Las acciones para atenderla son actividades vinculadas a ella. Estado de la solicitud: **Pendiente** (sin actividades), **En proceso** (con actividades) y **Atendida** (todas sus actividades vinculadas fueron validadas).

## Chatbot con IA

El sistema incluye un asistente de chat con IA en un widget flotante (abajo a la derecha), disponible para los roles **Admin, Coordinador y Delegado** y para el superusuario. El rol **Funcionario** no ve el widget y, si invoca los endpoints directamente, recibe `403` con el intento registrado en la auditoría (`ACCESO_DENEGADO`). Sin sesión, el usuario es enviado al login. El código vive en `ChatbotApp` y el historial se guarda por usuario en la tabla `mensaje_chat`; el botón **Nueva** del widget borra la conversación propia.

El asistente responde con **contexto real del SGR** (Fase 2): documentación interna y FAQ cargadas en la base (`DocumentoConocimiento`) más datos agregados de actividades, metas, atenciones, usuarios y ausencias, filtrados por el alcance del rol. Cada usuario tiene su **propia caché** y cada interacción queda registrada en `EventoChatbot` (prompt, contexto, mensajes, respuesta, modelo, origen, latencia, tokens, guardrails y documentos usados). El detalle técnico está en [`docs/chatbot.md`](docs/chatbot.md).

La conversación se envía al proveedor **desde el servidor**: la ApiKey se lee del `.env`, nunca se incluye en plantillas, JavaScript ni respuestas, y los errores del proveedor se muestran con un mensaje genérico. El cliente HTTP usa solo la biblioteca estándar (`urllib.request`), por lo que no se agregaron dependencias.

Configuración en el `.env` (cualquier proveedor compatible con la API *OpenAI Chat Completions*):

```
CHATBOT_API_KEY='clave-del-proveedor'
CHATBOT_API_URL='https://api.openai.com/v1/chat/completions'
CHATBOT_MODEL='gpt-4o-mini'
CHATBOT_TIMEOUT=30

# Alternativa local (Ollama): se usa si CHATBOT_MODEL queda vacío
CHATBOT_LOCAL_API_URL='http://127.0.0.1:11434/v1/chat/completions'
CHATBOT_LOCAL_MODEL=''
CHATBOT_LOCAL_TIMEOUT=120

# Fase 2: RAG, caché por usuario y observabilidad
CHATBOT_PROMPT_VERSION=2.0
CHATBOT_CACHE_TTL=600         # segundos de vida de una respuesta cacheada
CHATBOT_RATE_LIMIT=30         # consultas por usuario y ventana
CHATBOT_RATE_VENTANA=3600     # segundos de la ventana
CHATBOT_RAG_MAX_CARACTERES=4000
CHATBOT_MAX_RESPUESTA=4000
CHATBOT_LOG_LEVEL=INFO
```

| Proveedor | `CHATBOT_API_URL` | Ejemplo de `CHATBOT_MODEL` |
|---|---|----------------------------|
| OpenAI | `https://api.openai.com/v1/chat/completions` | `gpt-4o-mini`              |
| OpenRouter | `https://openrouter.ai/api/v1/chat/completions` | `openai/gpt-4o-mini`       |
| Groq | `https://api.groq.com/openai/v1/chat/completions` | `llama-3.3-70b-versatile`  |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` | `gemini-2.0-flash`         |
| Ollama (local) | `http://127.0.0.1:11434/v1/chat/completions` | `Nombre del modelo`        |

El cliente elige el proveedor en este orden:

1. **API remota**: si `CHATBOT_API_KEY` y `CHATBOT_MODEL` tienen valor, se usa `CHATBOT_API_URL` con esa clave.
2. **Modelo local (Ollama)**: si `CHATBOT_MODEL` queda vacío y `CHATBOT_LOCAL_MODEL` tiene valor, se usa `CHATBOT_LOCAL_API_URL`, sin clave ni internet.
3. Si no hay ninguna de las dos configuraciones, el chatbot queda **desactivado** y el endpoint responde `503`.

Para usar un **modelo local con Ollama** basta con tener Ollama corriendo (`ollama serve`, por defecto en `http://127.0.0.1:11434`) y el modelo descargado (`ollama pull qwen3.5_progra_128k:latest` o el que se prefiera). El nombre debe ser el ID exacto que muestra `ollama list`. Si el modelo es de **razonamiento** (por ejemplo las familias Qwen), `CHATBOT_LOCAL_REASONING_EFFORT='none'` hace que la respuesta llegue en `content` en lugar de quedarse en `reasoning`; dejar esa variable vacía si el servidor local no acepta el parámetro. Cambiar de proveedor solo requiere editar el `.env` y reiniciar el servidor; no hay que tocar código. Cada mensaje se limita a 2000 caracteres y al proveedor se le envían como contexto los últimos 12 mensajes del usuario.

Endpoints (JSON, solo usuarios autenticados con acceso):

| Ruta | Método | Uso |
|---|---|---|
| `/chatbot/mensaje/` | POST | Envía la pregunta y devuelve `{"respuesta", "fecha"}` (400/403/429/502/503 ante errores) |
| `/chatbot/historial/` | GET | Últimos 50 mensajes del usuario, en orden cronológico |
| `/chatbot/limpiar/` | POST | Borra la conversación del usuario autenticado |

### RAG, caché y observabilidad (Fase 2)

- **Documentación**: `python manage.py cargar_conocimiento_chatbot` carga 12 documentos iniciales
  (idempotente, se puede ejecutar varias veces). El Administrador los edita en Django Admin.
- **Datos por rol**: Admin, Coordinador y superusuario reciben datos de toda la municipalidad; el
  Delegado, solo de su delegación. El contexto no incluye nombres, RUT ni teléfonos.
- **Guardrails**: se rechazan los intentos claros de prompt injection, se aplica un rate limit por
  usuario (`429`) y se sanean secretos/truncado en la salida.
- **Caché por usuario**: clave `chatbot:respuesta:{usuario_id}:{sha256(...)}`; nunca se comparte
  entre usuarios. TTL configurable (`CHATBOT_CACHE_TTL`, 600 s por defecto).
- **Observabilidad**: cada interacción (incluidos bloqueos y errores) queda en `EventoChatbot` y en
  `logs/chatbot.log`. El evento es de solo lectura en Django Admin.
- **Limitación**: la caché es `LocMemCache`, por proceso. Con varios workers cada uno tiene su
  propia caché y su propio contador de rate limit.

## Pruebas automatizadas

```
python manage.py test
```

281 pruebas con `django.test`, sobre una base temporal. Cubren login, grupos y permisos, protección de vistas, recuperación de contraseña, tableros por perfil, mantenedores, buscadores, transacciones y auditoría.

## Estructura del proyecto

| App | Contenido |
|---|---|
| `UsuarioApp` | Usuarios, roles, delegaciones, cargos, catálogos, login, recuperación de contraseña, Administración y comando `crear_grupos` |
| `IndicadoresApp` | Periodos, metas, ponderaciones, semáforo, resumen por delegación, ausencias, felicitaciones, reclamos y tableros |
| `ActividadesApp` | Actividades, evidencias, validación, territorios, Tubo de Trabajo y gestión social: organizaciones, solicitantes, representantes y atenciones sociales |
| `AuditoriaApp` | Bitácora de cambios y accesos denegados |
| `ChatbotApp` | Asistente de chat con IA: modelos `MensajeChat`, `DocumentoConocimiento` y `EventoChatbot`, cliente del proveedor, RAG, guardrails, caché por usuario, endpoints JSON, widget, JS y CSS |
| `config` | Configuración del proyecto (lee el `.env`) |
| `nginx` | Configuración del proxy inverso y ubicación de los certificados SSL |
| `Dockerfile` y `docker-compose.yml` | Imagen de la aplicación y orquestación de `db`, `web` y `nginx` |

