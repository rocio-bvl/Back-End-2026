# «enumeration» Semaforo
semaforos = (
    ('VERDE', 'Verde'),
    ('AMBAR', 'Ámbar'),
    ('ROJO', 'Rojo'),
)

# «enumeration» EstadoPeriodo
estados_periodo = (
    ('ACTIVO', 'Activo'),
    ('CERRADO', 'Cerrado'),
)

# «enumeration» EstadoReclamo: el reclamo se cierra cuando el Delegado (o el Administrador) escribe la respuesta
estados_reclamo = (
    ('PENDIENTE', 'Pendiente'),
    ('RESUELTO', 'Resuelto'),
)

# Tipo de ajuste de desempeño que crea cada felicitación (catálogo TIPO_AJUSTE; lo crea la migración 0005)
TIPO_AJUSTE_FELICITACION = 'Felicitación de usuarios'
