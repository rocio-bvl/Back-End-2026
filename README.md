# SGR: Sistema de Gestión y Control, Municipalidad de La Serena

Aplicación web en Django para registrar la gestión territorial de los funcionarios municipales: actividades diarias con evidencia fotográfica, compromisos del Tubo de Trabajo, gestión social, verificación de evidencias, metas trimestrales con semáforo de cumplimiento y auditoría de cambios.

Asignatura: Programación Back End (TI3041)

## Tecnologías

- Python 3.12 y Django 4.2 LTS 
- MariaDB / MySQL (mysqlclient)
- Bootstrap 5.3 y framework visual de la Municipalidad de La Serena
- python-dotenv para las variables de entorno

## Roles y permisos

| Acción | Admin | Coordinador | Delegado | Funcionario | Consulta |
|---|:-:|:-:|:-:|:-:|:-:|
| Ver tablero, semáforo y resumen | Sí | Sí | Sí (su delegación) | Tablero | Sí |
| Registrar actividades (con evidencia o al Tubo) | Sí | Sí | No | Sí | No |
| Subir la evidencia de su propia actividad | Sí | Sí | No | Sí | No |
| Validar o rechazar evidencias | Sí | Sí | Sí (su delegación) | No | No |
| Modificar y eliminar (Django Admin) | Sí | Sí, sin fechas | No | No | No |
| Crear y editar usuarios, metas y ver auditoría | Sí | Sí | No | No | No |
| Crear o asignar Coordinador y Administrador | Sí | No | No | No | No |
| Modificar fechas y horas | Sí | No | No | No | No |

- El rol Verificador ya no existe: sus funciones pasaron al Delegado. La migración `UsuarioApp/0003` convierte a los usuarios que eran Verificador en Delegado (hay que asignarles una delegación).
- Las fechas y horas de actividades y compromisos se registran solas. En Django Admin el Coordinador las ve de solo lectura; solo el Administrador (superusuario) puede corregirlas. Las reglas están en `UsuarioApp/admin_sgr.py`.
- El Administrador es superusuario. El Coordinador entra a Django Admin como staff con permisos restringidos. Delegado, Funcionario y Consulta no entran a Django Admin.

## Flujo de una actividad

1. **Con evidencia** (el funcionario ya la realizó): se registra con la fotografía y queda `REGISTRADA`.
2. **Sin evidencia** (necesita tiempo): el mismo funcionario la envía al **Tubo de Trabajo** con una fecha límite. Eso es un **compromiso**: no es otra tabla, es la actividad en estado `EN_TUBO`. Se marca vencida si pasa la fecha.
3. Cuando ejecuta el compromiso, el funcionario sube la evidencia desde el detalle de la actividad (botón Ejecutar) y pasa a `REGISTRADA`.
4. El Delegado de la delegación revisa la evidencia: **Validar** deja la actividad `VALIDADA`, es decir, **completada** (también la que vino del Tubo) y cuenta para la meta. **Rechazar evidencia** exige un motivo y deja la actividad `RECHAZADA`: la evidencia no es válida, pero la actividad no se anula porque se debe cumplir; el funcionario sube una nueva evidencia (nueva versión) y vuelve a `REGISTRADA`.


