# «enumeration» RolChoices
roles = (
    ('Admin', 'Administrador'),
    ('Coordinador', 'Coordinador'),
    ('Delegado', 'Delegado'),
    ('Verificador', 'Verificador'),
    ('Funcionario', 'Funcionario'),
    ('Consulta', 'Usuario Consulta'),
)

# Orden de importancia
orden_roles = ['Admin', 'Coordinador', 'Delegado', 'Verificador', 'Funcionario', 'Consulta']

# «enumeration» EstadoRegistro
estados_registro = (
    ('ACTIVO', 'Activo'),
    ('INACTIVO', 'Inactivo'),
)

# Nombres de las delegaciones
delegaciones = (
    ('RURAL', 'Rural'),
    ('LAS_COMPANIAS', 'Las Compañías'),
    ('LA_PAMPA', 'La Pampa'),
    ('LA_ANTENA', 'La Antena'),
    ('CENTRO', 'Centro'),
)

# Opción para ver todas las delegaciones juntas
opciones_delegacion = (('GENERAL', 'General (Toda la Municipalidad)'),) + delegaciones

# «enumeration» TipoCatalogo
tipos_catalogo = (
    ('AREA', 'Área'),
    ('ITEM_GESTION', 'Ítem de gestión'),
    ('SERVICIO', 'Servicio'),
    ('TIPO_ATENCION', 'Tipo de atención'),
    ('SUBTIPO_ATENCION', 'Subtipo de atención'),
    ('TIPO_AJUSTE', 'Tipo de ajuste'),
)

# «enumeration» PropositoOTP
propositos_otp = (
    ('LOGIN', 'Inicio de sesión'),
    ('RECUPERACION', 'Recuperación de contraseña'),
)