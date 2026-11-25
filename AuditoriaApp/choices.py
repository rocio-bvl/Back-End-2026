# «enumeration» EventoAuditoria
eventos = (
    ('CREACION', 'Creación'),
    ('MODIFICACION', 'Modificación'),
    ('ELIMINACION', 'Eliminación'),
    ('ACCESO_DENEGADO', 'Acceso denegado'),
    ('LOGIN_FALLIDO', 'Inicio de sesión fallido'),
    ('LOGIN_BLOQUEADO', 'Inicio de sesión bloqueado'),
)

# Canal del sistema desde donde se hizo la acción (RNF-008: origen)
canales = (
    ('SGR', 'Sistema SGR'),
    ('ADMIN', 'Django Admin'),
    ('EXTERNO', 'Externo'),
)
