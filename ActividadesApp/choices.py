# «enumeration» EstadoActividad
# EN_TUBO: sin evidencia, es un compromiso con fecha límite.
# REGISTRADA: con evidencia, espera la validación del Delegado.
# RECHAZADA: el Delegado rechazó la evidencia (no es válida). La actividad NO se anula: se debe
#            cumplir igual, así que el funcionario resube una nueva evidencia y vuelve a REGISTRADA.
# VALIDADA: el Delegado aprobó la evidencia; la actividad queda completada y cuenta para la meta.
estados_actividad = (
    ('EN_TUBO', 'En Tubo de Trabajo'),
    ('REGISTRADA', 'Registrada'),
    ('RECHAZADA', 'Rechazada (resubir evidencia)'),
    ('VALIDADA', 'Validada (completada)'),
)

# «enumeration» EstadoEvidencia
estados_evidencia = (
    ('PENDIENTE', 'Pendiente'),
    ('APROBADA', 'Aprobada'),
    ('RECHAZADA', 'Rechazada'),
)

# «enumeration» DecisionValidacion
decisiones = (
    ('APROBAR', 'Aprobar'),
    ('RECHAZAR', 'Rechazar (resubir evidencia)'),
)

# «enumeration» TipoGestionSocial
tipos_gestion_social = (
    ('VISITA', 'Visita'),
    ('INFORME', 'Informe'),
    ('BENEFICIO', 'Beneficio'),
)
