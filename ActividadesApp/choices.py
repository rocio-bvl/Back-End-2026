# «enumeration» EstadoActividad
# PROGRAMADA: compromiso. Se registró con una fecha de realización futura y queda pendiente hasta que se ejecute.
# EN_TUBO: depende de factores externos. Queda registrada sin fecha, en el Tubo de Trabajo, hasta que se
#          le asigne la fecha en que se realizará (entonces pasa a PROGRAMADA).
# REGISTRADA: ejecutada. Tiene su comentario de ejecución (y una foto si la hay) y espera la validación.
# RECHAZADA: el Delegado rechazó la ejecución. La actividad NO se anula: se vuelve a registrar la ejecución.
# VALIDADA: el Delegado (o el Administrador) la validó; queda completada y cuenta para la meta.
estados_actividad = (
    ('PROGRAMADA', 'Programada (compromiso)'),
    ('EN_TUBO', 'En Tubo de Trabajo (sin fecha)'),
    ('REGISTRADA', 'Ejecutada (en revisión)'),
    ('RECHAZADA', 'Rechazada (volver a registrar)'),
    ('VALIDADA', 'Validada (completada)'),
)

# Estados en que la actividad todavía no se ha ejecutado
ESTADOS_PENDIENTES = ['PROGRAMADA', 'EN_TUBO']

# «enumeration» EstadoEvidencia
estados_evidencia = (
    ('PENDIENTE', 'Pendiente'),
    ('APROBADA', 'Aprobada'),
    ('RECHAZADA', 'Rechazada'),
)

# «enumeration» DecisionValidacion
decisiones = (
    ('APROBAR', 'Aprobar'),
    ('RECHAZAR', 'Rechazar (volver a registrar la ejecución)'),
)
