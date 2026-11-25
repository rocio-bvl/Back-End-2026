# «enumeration» EstadoActividad
# PROGRAMADA: compromiso. Se registró con una fecha de realización futura y queda pendiente hasta que se realice.
# EN_TUBO: depende de factores externos. Sigue en el Tubo de Trabajo, con o sin fecha, hasta que se realice.
# EVIDENCIA_INGRESADA: se informó como realizada (con foto si la hay) y espera la validación.
# RECHAZADA: el Delegado rechazó la evidencia. La actividad NO se anula: se vuelve a agregar la evidencia.
# VALIDADA: el Delegado (o el Administrador) la validó; queda completada y cuenta para la meta.
estados_actividad = (
    ('PROGRAMADA', 'Programada (compromiso)'),
    ('EN_TUBO', 'En Tubo de Trabajo'),
    ('EVIDENCIA_INGRESADA', 'Evidencia ingresada'),
    ('RECHAZADA', 'Rechazada (volver a agregar la evidencia)'),
    ('VALIDADA', 'Validada (completada)'),
)

# «enumeration» EstadoTubo: etapas de una actividad del Tubo de Trabajo, la que depende de factores externos
# (aprobaciones, organizaciones, otras entidades). No aplica a los compromisos (PROGRAMADA), que solo esperan su fecha.
# Guía del proyecto 4.2 y presentación de la matriz: Ingresado, Pendiente, En proceso y Realizado. Realizado no se elige: lo marca el sistema cuando se registra la ejecución.
estados_tubo = (
    ('INGRESADO', 'Ingresado'),
    ('PENDIENTE', 'Pendiente'),
    ('EN_PROCESO', 'En proceso'),
    ('REALIZADO', 'Realizado'),
)
ESTADOS_TUBO_ELEGIBLES = ['INGRESADO', 'PENDIENTE', 'EN_PROCESO']

# Estados en que la actividad todavía no se ha realizado
ESTADOS_PENDIENTES = ['PROGRAMADA', 'EN_TUBO']

# Reglas de ingreso (requerimientos de la municipalidad)
MAX_ACTIVIDADES_DIA = 7  # actividades que un usuario puede ingresar por día (el Administrador queda exento)
MAX_GESTIONES_ATENCION = 3  # RF-015 / RN-012: gestiones (actividades vinculadas) por atención social

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
    ('JUNTA_VECINOS', 'Junta de vecinos'),
    ('FUNCIONAL', 'Organización comunitaria funcional'),
    ('ADULTO_MAYOR', 'Club de adulto mayor'),
    ('DEPORTIVA', 'Organización deportiva'),
    ('CULTURAL', 'Centro de madres, centro cultural o agrupación juvenil'),
    ('COMITE', 'Comité de vecinos, de allegados o de seguridad'),
)
