# SGR: Sistema de Gestión de Resultados, Municipalidad de La Serena

Aplicación web en Django para registrar la gestión territorial de los funcionarios municipales: actividades diarias con evidencia fotográfica, compromisos del Tubo de Trabajo, gestión social, verificación de evidencias, metas trimestrales con semáforo de cumplimiento y auditoría de cambios.

Asignatura: Programación Back End (TI3041)

## Tecnologías

- Python 3.12 y Django 4.2 LTS 
- MariaDB / MySQL (mysqlclient)
- Bootstrap 5.3 y framework visual de la Municipalidad de La Serena
- python-dotenv para las variables de entorno

## Roles y permisos

| Acción | Admin | Coordinador | Delegado | Funcionario |
|---|:-:|:-:|:-:|:-:|
| Ver actividades | Todas (filtra por delegación) | Todas (filtra por delegación) | Su delegación | Su delegación |
| Registrar actividades y atenciones sociales | Sí | No | No | Sí |
| Validar o rechazar la ejecución | Sí | No | Sí (su delegación) | No |
| Asignar encargado a una actividad pendiente | Sí | Sí | Sí (su delegación) | Al registrar, de su delegación |
| Ver usuarios y delegaciones (Administración) | Sí, con el nombre "Gestión" | Solo visualiza ("Usuarios") | Funcionarios de su delegación | No |
| Crear, editar y desactivar usuarios | Sí | No | Funcionarios de su delegación | No |
| Eliminar usuarios (con confirmación) | Sí, si no tienen registros | No | No | No |
| Agregar, modificar y eliminar delegaciones y territorios | Sí | No | No | No |
| Metas generales de la municipalidad | Agrega y edita | Visualiza | Visualiza | No |
| Metas propias de una delegación | Todas | Visualiza | Las de su delegación | No |
| Auditoría | Sí | Solo visualiza | No | No |
| Entrar a Django Admin | Sí (superusuario) | No | No | No |

- Cada usuario edita su foto, teléfono y correo desde **Editar perfil**.
- Las delegaciones ya no son una lista fija: el Administrador las agrega en Administración > Gestión > Delegaciones. Cada Funcionario puede tener un territorio de su delegación.
- Una meta de delegación reemplaza a la meta general para los cargos que la delegación defina.

## Flujo de una actividad

La **fecha de ingreso** se guarda sola; quien registra elige la **fecha de ejecución**, el **territorio**, opcionalmente un **encargado** (Funcionario de su delegación) y opcionalmente la **solicitud social** a la que responde.

| Caso | Estado inicial |
|---|---|
| Fecha de ejecución hoy o anterior | `REGISTRADA` (en revisión). Comentario obligatorio, foto opcional. |
| Fecha de ejecución posterior a hoy | `PROGRAMADA` (compromiso). |
| Depende de factores externos, sin fecha | `EN_TUBO`. La fecha se agrega después y pasa a `PROGRAMADA`. |
| Depende de factores externos, con fecha | `PROGRAMADA`, y sigue en el Tubo de Trabajo. |

Luego se registra la ejecución, el Delegado valida (`VALIDADA`) o rechaza con motivo (`RECHAZADA`), y se pueden agregar comentarios con fecha en la bitácora.

## Registro de Atenciones (Gestión Social)

Un funcionario registra la solicitud de una persona natural (fecha y funcionario automáticos). Las acciones para atenderla son actividades vinculadas a ella: una o varias, según lo que la solicitud requiera. Estado de la solicitud: **Pendiente** (sin actividades), **En proceso** (con actividades) y **Atendida** (todas sus actividades vinculadas fueron validadas).

## Tablas nuevas o modificadas

- Nuevas: `territorio`, `comentario_actividad`. Se eliminó `gestion_social` (las acciones de una solicitud son sus actividades).
- `actividad`: `territorio_id`, `fecha_realizacion` (fecha de ejecución), `depende_externos`, `encargado_id`, `solicitud_id`. Se quitaron `contacto` y `telefono`.
- `atencion_social`: `fecha` y `usuario_id` (quién la registró). Se quitó `actividad_id`: ahora es la actividad la que apunta a la solicitud.
- `delegacion`: `nombre_visible`. `usuario`: `telefono`, `foto`, `territorio_id`. `meta_desempeno`: `delegacion_id` (vacío = meta general).
- `evidencia.imagen` es opcional.
