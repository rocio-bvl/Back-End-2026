# «enumeration» EstadoActividad
# PROGRAMADA: compromiso. Se registró con una fecha de realización futura y queda pendiente hasta que se realice.
# EN_TUBO: depende de factores externos. Queda registrada sin fecha, en el Tubo de Trabajo, hasta que se
#          le asigne la fecha en que se realizará (entonces pasa a PROGRAMADA).
# EVIDENCIA_INGRESADA: tiene evidencia. Tiene su comentario (y una foto si la hay) y espera la validación.
# RECHAZADA: el Delegado rechazó la evidencia. La actividad NO se anula: se vuelve a agregar la evidencia.
# VALIDADA: el Delegado (o el Administrador) la validó; queda completada y cuenta para la meta.
estados_actividad = (
    ('PROGRAMADA', 'Programada (compromiso)'),
    ('EN_TUBO', 'En Tubo de Trabajo (sin fecha)'),
    ('EVIDENCIA_INGRESADA', 'Evidencia ingresada'),
    ('RECHAZADA', 'Rechazada (volver a agregar la evidencia)'),
    ('VALIDADA', 'Validada (completada)'),
)

# Estados en que la actividad todavía no se ha realizado
ESTADOS_PENDIENTES = ['PROGRAMADA', 'EN_TUBO']

# Reglas de ingreso (requerimientos de la municipalidad)
MAX_ACTIVIDADES_DIA = 7  # actividades que un usuario puede ingresar por día (el Administrador queda exento)

# «enumeration» EstadoEvidencia
estados_evidencia = (
    ('PENDIENTE', 'Pendiente'),
    ('APROBADA', 'Aprobada'),
    ('RECHAZADA', 'Rechazada'),
)

# «enumeration» DecisionValidacion
decisiones = (
    ('APROBAR', 'Aprobar'),
    ('RECHAZAR', 'Rechazar (volver a agregar la evidencia)'),
)

# Cargos del directorio de una organización que se registran como representantes
cargos_representante = (
    ('PRESIDENTE', 'Presidente'),
    ('SECRETARIO', 'Secretario'),
    ('TESORERO', 'Tesorero'),
)

# «enumeration» TipoOrganizacion: tipos de organización comunitaria (tabla organizacion)
tipos_organizacion = (
    ('FUNCIONAL', 'Organización comunitaria funcional'),
    ('ADULTO_MAYOR', 'Club de adulto mayor'),
    ('DEPORTIVA', 'Organización deportiva'),
    ('CULTURAL', 'Centro de madres, centro cultural o agrupación juvenil'),
    ('COMITE', 'Comité de vecinos, de allegados o de seguridad'),
)
