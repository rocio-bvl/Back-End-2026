# «enumeration» RolChoices
roles = (
    ('Admin', 'Administrador'),
    ('Coordinador', 'Coordinador'),
    ('Delegado', 'Delegado'),
    ('Funcionario', 'Funcionario'),
)

# Orden de importancia
orden_roles = ['Admin', 'Coordinador', 'Delegado', 'Funcionario']

# Grupos de roles que usan las views y los templates (una sola fuente para los permisos)
ROLES_ADMINISTRACION = ['Admin', 'Coordinador']             # metas, auditoría y todas las delegaciones
ROLES_VER_USUARIOS = ['Admin', 'Coordinador', 'Delegado']  # ven la pantalla de usuarios (el Coordinador solo mira)
ROLES_GESTION_USUARIOS = ['Admin', 'Delegado']             # crean y editan (el Delegado, solo Funcionarios de su delegación)
ROLES_METAS = ['Admin', 'Delegado']                        # agregan y editan metas (el Delegado, las de su delegación)
ROLES_REGISTRO = ['Admin', 'Funcionario']                  # agregan actividades (el Coordinador solo las ve)
ROLES_VERIFICACION = ['Admin', 'Delegado']                 # validan la ejecución (el Delegado, en su delegación)
ROLES_ASIGNAN_ENCARGADO = ['Admin', 'Coordinador', 'Delegado']  # asignan un Funcionario a una actividad pendiente
ROLES_RESERVADOS = ['Admin', 'Coordinador']                # solo el Admin puede asignarlos

# «enumeration» EstadoRegistro
estados_registro = (
    ('ACTIVO', 'Activo'),
    ('INACTIVO', 'Inactivo'),
)

# Delegaciones iniciales (las usa la migración 0005). Desde ahí, el Administrador las agrega y edita en Gestión,
# así que la lista para los <select> se arma desde la base de datos: UsuarioApp.funciones.opciones_delegacion()
delegaciones = (
    ('RURAL', 'Rural'),
    ('LAS_COMPANIAS', 'Las Compañías'),
    ('LA_PAMPA', 'La Pampa'),
    ('LA_ANTENA', 'La Antena'),
    ('CENTRO', 'Centro'),
)

# «enumeration» TipoCatalogo
tipos_catalogo = (
    ('AREA', 'Área'),
    ('ITEM_GESTION', 'Ítem de gestión'),
    ('SERVICIO', 'Servicio'),
    ('TIPO_ATENCION', 'Tipo de atención'),
    ('SUBTIPO_ATENCION', 'Subtipo de atención'),
    ('TIPO_AJUSTE', 'Tipo de ajuste'),
)