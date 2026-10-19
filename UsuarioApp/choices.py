# «enumeration» RolChoices
roles = (
    ('Admin', 'Administrador'),
    ('Coordinador', 'Coordinador'),
    ('Delegado', 'Delegado'),
    ('Funcionario', 'Funcionario'),
    ('Consulta', 'Usuario Consulta'),
)

# Orden de importancia
orden_roles = ['Admin', 'Coordinador', 'Delegado', 'Funcionario', 'Consulta']

# Grupos de roles que usan las views y los templates (una sola fuente para los permisos)
ROLES_ADMINISTRACION = ['Admin', 'Coordinador']          # usuarios, metas, auditoría, modificar y eliminar
ROLES_REGISTRO = ['Admin', 'Coordinador', 'Funcionario']  # agregan actividades y compromisos
ROLES_VERIFICACION = ['Admin', 'Coordinador', 'Delegado']  # validan evidencias y cambian estados del Tubo
ROLES_RESERVADOS = ['Admin', 'Coordinador']              # solo el Admin puede asignarlos

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