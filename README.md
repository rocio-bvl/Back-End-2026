# SGR: Sistema de Gestión de Resultados, Municipalidad de La Serena

Aplicación web en Django para registrar la gestión territorial de los funcionarios municipales: actividades con evidencia, compromisos del Tubo de Trabajo, registro de atenciones sociales, verificación de la ejecución, metas trimestrales con semáforo de cumplimiento y auditoría de cambios.

Todas las operaciones se hacen desde pantallas propias del sistema (Django Templates). Django Admin queda solo como herramienta técnica del superusuario.

Asignatura: Programación Back End (TI3041), INACAP La Serena.
Integrantes: Juliet Araya y Rocío Vásquez.

## Tecnologías

- Python 3.12 y Django 4.2 LTS
- MySQL / MariaDB (mysqlclient, motor InnoDB)
- Bootstrap 5.3, Bootstrap Icons, SweetAlert2 y framework visual de la Municipalidad de La Serena
- python-dotenv para las variables de entorno
- Despliegue en AWS EC2 (Ubuntu Server, Gunicorn y Nginx)

## Instalación local

1. Clonar el repositorio y crear el entorno virtual:

   ```
   git clone https://github.com/rocio-bvl/Back-End-2026.git
   cd Back-End-2026
   python -m venv venv
   venv\Scripts\activate          (Windows)
   source venv/bin/activate       (Linux o Mac)
   pip install -r requirements.txt
   ```

2. Crear la base de datos vacía `municipalidad` (utf8mb4) en MySQL o phpMyAdmin.

3. Copiar `.env.example` como `.env`, en la misma carpeta que `manage.py`, y completar los valores: `SECRET_KEY`, datos de la base (`DB_*`) y, si se quiere enviar correos reales, los datos de correo; para el asistente de chat con IA, la `CHATBOT_*` (ver más abajo). El archivo `.env` no se sube a GitHub.

4. Crear las tablas, cargar los datos de ejemplo y crear los grupos, en este orden:

   ```
   python manage.py migrate
   ```

   Importar `datos_iniciales.sql` en la base (phpMyAdmin > Importar, una sola vez y en una base vacía). Luego:

   ```
   python manage.py crear_grupos
   python manage.py runserver
   ```

   `crear_grupos` crea los cuatro grupos de Django, les asigna sus permisos y deja a cada usuario en el grupo de su rol. Se puede ejecutar las veces que sea necesario; conviene repetirlo después de cada `migrate` que agregue permisos.

5. Entrar en http://127.0.0.1:8000 con un usuario de prueba. Todos usan la contraseña `Serena2026!`:

   | RUT | Rol |
   |---|---|
   | 11111111-1 | Administrador |
   | 22222222-2 | Coordinador (Supervisor) |
   | 33333333-3 | Delegada de Las Compañías |
   | 55555555-5 | Funcionaria de Las Compañías |
   | 66666666-6 | Funcionario de Las Compañías |

## Roles, grupos y permisos

Cada rol del negocio queda unido a un grupo de Django con el nombre de perfil que pide la evaluación. Los permisos de cada grupo están en `PERMISOS_POR_GRUPO` (`UsuarioApp/choices.py`).

| Rol del SGR | Grupo de Django | Nivel |
|---|---|---|
| Admin | Administrador | Acceso total (superusuario) |
| Coordinador | Supervisor | Define metas y ponderaciones; supervisa todas las delegaciones |
| Delegado | Delegado | Gestiona su delegación |
| Funcionario | Administrativo | Solo lo propio |

Además de los permisos que Django crea por modelo (`add_`, `change_`, `delete_`, `view_`), hay dos permisos propios: `ActividadesApp.validar_evidencia` y `ActividadesApp.asignar_encargado`.

Las vistas se protegen con `@login_required` o con `@permiso_requerido(permiso, pantalla)` (`UsuarioApp/funciones.py`). Sin sesión, el usuario vuelve al login; sin permiso, vuelve a Mi Gestión con un mensaje y el intento queda en la auditoría como ACCESO_DENEGADO.

| Acción | Admin | Coordinador | Delegado | Funcionario |
|---|:-:|:-:|:-:|:-:|
| Ver actividades | Todas (filtra por delegación) | Todas (filtra por delegación) | Su delegación | Su delegación |
| Registrar actividades y atenciones sociales | Sí | No | No | Sí |
| Modificar y eliminar actividades | Sí | No | No | No |
| Validar o rechazar la ejecución | Sí | No | Sí (su delegación) | No |
| Asignar encargado a una actividad pendiente | Sí | Sí | Sí (su delegación) | Al registrar, de su delegación |
| Ver usuarios y delegaciones (Administración) | Sí | Solo visualiza | Funcionarios de su delegación | No |
| Crear, editar y desactivar usuarios | Sí | No | Funcionarios de su delegación | No |
| Eliminar usuarios (con confirmación) | Sí, si no tienen registros | No | No | No |
| Agregar, modificar y eliminar delegaciones y territorios | Sí | No | No | No |
| Ponderación de cada ítem por cargo (una para toda la municipalidad) | Agrega y edita | Agrega y edita | Visualiza | No |
| Metas generales de la municipalidad | Agrega y edita | Agrega y edita | Visualiza | No |
| Metas propias de una delegación (cambian el valor objetivo de un ítem) | Agrega y edita | Agrega y edita | Visualiza | No |
| Auditoría (solo lectura) | Sí | Sí | No | No |
| Asistente de chat con IA | Sí | Sí | Sí | No |
| Entrar a Django Admin | Sí (superusuario) | No | No | No |

## Funcionalidades

- **Tablero por perfil:** cada grupo tiene su panel de inicio (`dashboard_admin`, `dashboard_coordinador`, `dashboard_delegado` y `dashboard_administrativo`).
- **Mantenedores con crear, buscar, listar, modificar y eliminar:** Usuarios (búsqueda por nombre, RUT o correo), Delegaciones con sus territorios (búsqueda por nombre, ámbito o territorio), Metas (búsqueda por cargo o ítem) y Registro de Atenciones (búsqueda por nombre o RUT). Eliminar siempre pide confirmación.
- **Selector de delegación** en la barra superior: filtra la información por delegación. En Metas, General muestra las metas de toda la municipalidad y una delegación muestra las suyas; el Delegado elige entre General y la suya. Un cargo cuya ponderación no suma 100% no se mide hasta completarla.
- **Transacciones:** registrar una actividad (con su ejecución, si corresponde) y validar o rechazar la ejecución.
- **Auditoría de solo lectura**, con filtros por usuario, evento y fechas.
- **Perfil propio:** cada usuario edita su foto, teléfono y correo desde Editar perfil.

## Recuperación de contraseña por correo

En el login, "¿Olvidaste tu contraseña?" envía un enlace con un token de un solo uso que vence en 2 horas. Se usan las vistas de recuperación de Django con plantillas propias (`templates/users/recuperar*`).

Para enviar correos reales con Gmail se usa una contraseña de aplicación (no la clave normal) en el `.env`:

```
EMAIL_HOST_USER=cuenta@gmail.com
EMAIL_HOST_PASSWORD='contraseña de aplicación'
EMAIL_PORT=587
```

`EMAIL_PORT=587` usa TLS. Si la red bloquea ese puerto, `EMAIL_PORT=465` usa SSL. Si `EMAIL_HOST_USER` queda vacío, el correo se muestra en la terminal en vez de enviarse.

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
|---|---|---|
| OpenAI | `https://api.openai.com/v1/chat/completions` | `gpt-4o-mini` |
| OpenRouter | `https://openrouter.ai/api/v1/chat/completions` | `openai/gpt-4o-mini` |
| Groq | `https://api.groq.com/openai/v1/chat/completions` | `llama-3.3-70b-versatile` |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` | `gemini-2.0-flash` |
| Ollama (local) | `http://127.0.0.1:11434/v1/chat/completions` | `qwen3.5_progra_128k:latest` |

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

269 pruebas con `django.test`, sobre una base temporal. Cubren login, grupos y permisos, protección de vistas, recuperación de contraseña, tableros por perfil, mantenedores, buscadores, transacciones, auditoría y chatbot (con la llamada al proveedor de IA mockeada: nunca se usa la red ni una clave real). Las pruebas del chatbot incluyen RAG de documentos y de datos por rol, idempotencia del comando de carga, caché por usuario y TTL, rate limit, prompt injection, saneo de salida, eventos de observabilidad y el cliente detallado.

## Estructura del proyecto

| App | Contenido |
|---|---|
| `UsuarioApp` | Usuarios, roles, delegaciones, cargos, catálogos, login, recuperación de contraseña, Administración y comando `crear_grupos` |
| `IndicadoresApp` | Periodos, metas, semáforo, resumen por delegación y tableros |
| `ActividadesApp` | Actividades, evidencias, validación, territorios, Tubo de Trabajo y gestión social: organizaciones, solicitantes, representantes y atenciones sociales |
| `AuditoriaApp` | Bitácora de cambios y accesos denegados |
| `ChatbotApp` | Asistente de chat con IA: modelos `MensajeChat`, `DocumentoConocimiento` y `EventoChatbot`, cliente del proveedor, RAG, guardrails, caché por usuario, endpoints JSON, widget, JS y CSS |
| `config` | Configuración del proyecto (lee el `.env`) |

## Ramas

Cada integrante trabaja en su rama (`juliet` y `rocío`) y los cambios llegan a `main` mediante Pull Requests, después de correr las pruebas.
