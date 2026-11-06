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

3. Copiar `.env.example` como `.env`, en la misma carpeta que `manage.py`, y completar los valores: `SECRET_KEY`, datos de la base (`DB_*`) y, si se quiere enviar correos reales, los datos de correo (ver más abajo). El archivo `.env` no se sube a GitHub.

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
| Coordinador | Supervisor | Solo visualiza todas las delegaciones |
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
| Metas generales de la municipalidad | Agrega y edita | Visualiza | Visualiza | No |
| Metas propias de una delegación | Todas | Visualiza | Las de su delegación | No |
| Auditoría (solo lectura) | Sí | Sí | No | No |
| Entrar a Django Admin | Sí (superusuario) | No | No | No |

## Funcionalidades

- **Tablero por perfil:** cada grupo tiene su panel de inicio (`dashboard_admin`, `dashboard_coordinador`, `dashboard_delegado` y `dashboard_administrativo`).
- **Mantenedores con crear, buscar, listar, modificar y eliminar:** Usuarios (búsqueda por nombre, RUT o correo), Delegaciones con sus territorios (búsqueda por nombre, ámbito o territorio), Metas (búsqueda por cargo o ítem) y Registro de Atenciones (búsqueda por nombre o RUT). Eliminar siempre pide confirmación.
- **Selector de delegación** en la barra superior: filtra la información por delegación. En Metas, General muestra las metas de toda la municipalidad y una delegación muestra las suyas; el Delegado elige entre General y la suya.
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

## Pruebas automatizadas

```
python manage.py test
```

175 pruebas con `django.test`, sobre una base temporal. Cubren login, grupos y permisos, protección de vistas, recuperación de contraseña, tableros por perfil, mantenedores, buscadores, transacciones y auditoría.

## Estructura del proyecto

| App | Contenido |
|---|---|
| `UsuarioApp` | Usuarios, roles, delegaciones, cargos, catálogos, login, recuperación de contraseña, Administración y comando `crear_grupos` |
| `IndicadoresApp` | Periodos, metas, semáforo, resumen por delegación y tableros |
| `ActividadesApp` | Actividades, evidencias, validación, territorios, Tubo de Trabajo y gestión social: organizaciones, solicitantes, representantes y atenciones sociales |
| `AuditoriaApp` | Bitácora de cambios y accesos denegados |
| `config` | Configuración del proyecto (lee el `.env`) |

## Ramas

Cada integrante trabaja en su rama (`juliet` y `rocío`) y los cambios llegan a `main` mediante Pull Requests, después de correr las pruebas.
