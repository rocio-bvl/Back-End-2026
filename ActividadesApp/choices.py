# «enumeration» EstadoActividad
estados_actividad = (
    ('REGISTRADA', 'Registrada'),
    ('EN_REVISION', 'En revisión'),
    ('OBSERVADA', 'Observada'),
    ('VALIDADA', 'Validada'),
    ('RECHAZADA', 'Rechazada'),
)

# «enumeration» EstadoEvidencia
estados_evidencia = (
    ('PENDIENTE', 'Pendiente'),
    ('APROBADA', 'Aprobada'),
    ('OBSERVADA', 'Observada'),
    ('RECHAZADA', 'Rechazada'),
)

# «enumeration» DecisionValidacion
decisiones = (
    ('APROBAR', 'Aprobar'),
    ('CORREGIR', 'Corregir'),
    ('RECHAZAR', 'Rechazar'),
)

# «enumeration» EstadoCompromiso (el orden importa: se avanza de a un paso)
estados_compromiso = (
    ('INGRESADO', 'Ingresado'),
    ('PENDIENTE', 'Pendiente'),
    ('EN_PROCESO', 'En proceso'),
    ('REALIZADO', 'Realizado'),
)

# «enumeration» TipoGestionSocial
tipos_gestion_social = (
    ('VISITA', 'Visita'),
    ('INFORME', 'Informe'),
    ('BENEFICIO', 'Beneficio'),
)
