# SGR: Sistema de Gestión de Resultados, Municipalidad de La Serena

Aplicación web en Django para registrar y medir la gestión territorial de los funcionarios municipales: actividades con evidencia, compromisos con fecha, Tubo de Trabajo para lo que depende de terceros, atenciones sociales, verificación, metas trimestrales con semáforo y auditoría de cambios.

Todas las operaciones se hacen desde pantallas propias del sistema. Django Admin queda solo como herramienta técnica del superusuario.

## Tecnologías

- Python 3.12 y Django 4.2 LTS
- MySQL / MariaDB (mysqlclient, motor InnoDB, utf8mb4, modo estricto)
- Bootstrap 5.3, Bootstrap Icons, Chart.js, SweetAlert2 y framework visual de la Municipalidad de La Serena
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

3. Copiar `.env.example` como `.env`, en la misma carpeta que `manage.py`, y completar los valores (ver "Variables de entorno"). El archivo `.env` no se sube a GitHub.

4. Crear las tablas, cargar los datos de ejemplo y crear los grupos, en este orden:

   ```
   python manage.py migrate
   ```

   Importar `datos_iniciales.sql` en la base (phpMyAdmin > Importar, una sola vez y en una base vacía). Luego:

   ```
   python manage.py crear_grupos
   python manage.py runserver
   ```

   `crear_grupos` crea los cuatro grupos de Django, les asigna sus permisos y deja a cada usuario en el grupo de su rol. Conviene repetirlo después de cada `migrate` que agregue permisos.

5. Entrar en http://127.0.0.1:8000 con un usuario de prueba. Todos usan la contraseña `Serena2026!`:

   | RUT | Rol |
   |---|---|
   | 11111111-1 | Administrador |
   | 22222222-2 | Coordinador (Supervisor) |
   | 33333333-3 | Delegada de Las Compañías |
   | 55555555-5 | Funcionaria de Las Compañías |
   | 66666666-6 | Funcionario de Las Compañías |

## Variables de entorno

| Variable | Uso |
|---|---|
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Configuración de Django |
| `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Conexión a MySQL / MariaDB |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, `EMAIL_PORT` | Correo de recuperación de contraseña. Sin usuario, el correo se muestra en la terminal |
| `CONTRASENA_TEMPORAL` | `True`: el sistema genera la contraseña de cada usuario nuevo y exige cambiarla en el primer ingreso |
| `MFA_ACTIVO` | `True`: segundo factor con código por correo. Activar solo con correos reales |
| `USAR_HTTPS`, `HSTS_SEGUNDOS`, `CSRF_TRUSTED_ORIGINS` | HTTPS en producción. Activar solo con certificado instalado |
| `AUDITORIA_CONFIAR_PROXY` | `True` solo con Nginx u otro proxy propio delante: toma la IP de `X-Forwarded-For` |
| `RESPALDO_DIR`, `RESPALDO_CANTIDAD`, `MYSQLDUMP` | Respaldos con `respaldar_bd` |

## Roles, grupos y permisos

Cada rol del negocio queda unido a un grupo de Django. Los permisos de cada grupo están en `PERMISOS_POR_GRUPO` (`UsuarioApp/choices.py`).

| Rol del SGR | Grupo de Django | Alcance |
|---|---|---|
| Admin | Administrador | Acceso total (superusuario) |
| Coordinador | Supervisor | Metas y ponderaciones; supervisa todas las delegaciones |
| Delegado | Delegado | Su delegación: funcionarios, verificación, ausencias, felicitaciones y reclamos |
| Funcionario | Administrativo | Registra y gestiona sus actividades; consulta el Tubo y los Hitos de su delegación |

Las vistas se protegen con `@login_required` o `@permiso_requerido(permiso, pantalla)` (`UsuarioApp/funciones.py`). Sin sesión, el usuario vuelve al login; sin permiso, vuelve a Mi Gestión y el intento queda en la auditoría como ACCESO_DENEGADO.

## Funcionalidades

- **Mi Gestión:** tablero de cada perfil con su avance contra lo esperado, actividades por estado, cumplimiento por ítem, tendencia semanal del avance y accesos a sus pantallas.
- **Actividades y compromisos:** una actividad con fecha de realización futura queda como compromiso (Programada) hasta que se registra su ejecución.
- **Hitos:** los compromisos de la delegación ordenados por fecha límite (vencidos, próximos 7 días y más adelante), con su responsable.
- **Tubo de Trabajo:** actividades que dependen de factores externos (aprobaciones, organizaciones u otras entidades). Avanzan por etapas: Ingresado, Pendiente y En proceso, que cambia su responsable, y Realizado, que marca el sistema al registrar la ejecución. Todos los funcionarios de la delegación lo consultan; cada uno modifica solo lo suyo.
- **Registro de Atenciones (Gestión Social):** solicitudes de vecinos identificados por RUT, con hasta tres gestiones vinculadas.
- **Verificación:** el Delegado aprueba o rechaza la evidencia de su delegación y decide si suma puntaje. Un rechazo exige observación y permite volver a subir fotos.
- **Metas y semáforo:** metas y ponderaciones por cargo, ítem, periodo y delegación; tope de 120% por ítem; ausencias que ajustan la meta; semáforo exportable a CSV.
- **Felicitaciones y reclamos:** los registra el Delegado o el Administrador.
- **Administración:** delegaciones con sus territorios, usuarios, metas y periodos, y auditoría de solo lectura.

## Reglas de la Municipalidad

- Máximo de 7 actividades por día por funcionario.
- La semana se cierra el lunes siguiente: desde el martes no se ingresa lo de la semana anterior.
- Sin nombre y teléfono de la persona atendida, la actividad no suma puntaje.
- Las gestiones del Delegado quedan registradas, pero no suman puntaje.
- Una vez alcanzado el 120% de un ítem, nuevas actividades de ese ítem no suben el puntaje.
- Las felicitaciones las registra el Delegado, con respaldo formal.
- Vacaciones, días administrativos y licencias ajustan la meta desde que se registran.

## Seguridad

- Contraseñas con PBKDF2 y validadores de Django, más mayúscula, minúscula, número y símbolo (`ContrasenaSeguraValidator`).
- Bloqueo de 15 minutos tras 5 intentos fallidos con un mismo RUT.
- Contraseña temporal con cambio obligatorio en el primer ingreso (`CONTRASENA_TEMPORAL`).
- Recuperación de contraseña por correo con un enlace de un solo uso que vence en 2 horas.
- Autorización por rol y por propiedad del registro en el servidor; protección CSRF; fotos de evidencia entregadas solo a quien puede ver la actividad.
- Auditoría inmutable con usuario, IP y canal de origen.
- Una transacción por petición y llaves foráneas con `PROTECT`.

## Comandos de mantenimiento

| Comando | Uso |
|---|---|
| `python manage.py crear_grupos` | Crea los grupos y asigna permisos y usuarios |
| `python manage.py respaldar_bd` | Respalda la base y las fotos en `RESPALDO_DIR` y conserva los últimos `RESPALDO_CANTIDAD`. Se programa una vez al día |
| `python manage.py alerta_semaforo` | Envía a cada Delegado los funcionarios en rojo de su delegación. Se programa una vez por semana |

## Pruebas automatizadas

```
python manage.py test
```

300 pruebas con `django.test`, sobre una base temporal. Cubren login y bloqueo, contraseña temporal, grupos y permisos, protección de vistas, recuperación de contraseña, tableros por perfil, mantenedores, reglas de la Municipalidad, Hitos, Tubo de Trabajo, tendencia semanal, transacciones y auditoría.

## Estructura del proyecto

| App | Contenido |
|---|---|
| `UsuarioApp` | Usuarios, roles, delegaciones, cargos, catálogos, login, contraseña temporal, recuperación de contraseña, Administración y comando `crear_grupos` |
| `IndicadoresApp` | Periodos, metas, ponderaciones, semáforo, tendencia semanal, resumen por delegación, ausencias, felicitaciones y reclamos, y comandos `respaldar_bd` y `alerta_semaforo` |
| `ActividadesApp` | Actividades, compromisos, Hitos, Tubo de Trabajo, evidencias, verificación, territorios y gestión social: organizaciones, solicitantes, representantes y atenciones |
| `AuditoriaApp` | Bitácora de cambios y accesos denegados |
| `config` | Configuración del proyecto (lee el `.env`) |

