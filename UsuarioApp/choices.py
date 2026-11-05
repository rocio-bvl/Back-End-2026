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
ROLES_VER_USUARIOS = ['Admin', 'Coordinador', 'Delegado']  # ven la pantalla de usuarios
# Crean y editan usuarios: el Admin (cualquier perfil), el Coordinador (Delegados y Funcionarios) y el Delegado
# (solo Funcionarios de su delegación)
ROLES_GESTION_USUARIOS = ['Admin', 'Coordinador', 'Delegado']
ROLES_DELEGACIONES = ['Admin', 'Coordinador']              # agregan, modifican y eliminan delegaciones
ROLES_AUSENCIAS = ['Admin', 'Coordinador', 'Delegado']     # registran vacaciones, días administrativos y licencias
ROLES_METAS = ['Admin', 'Delegado']                        # agregan y editan metas (el Delegado, las de su delegación)
ROLES_REGISTRO = ['Admin', 'Funcionario']                  # agregan actividades (el Coordinador solo las ve)
ROLES_VERIFICACION = ['Admin', 'Delegado']                 # validan la evidencia (el Delegado, en su delegación)
# Asignan un Funcionario a una actividad pendiente. El Coordinador no: coordina y supervisa, pero no interviene
# en las actividades de los funcionarios
ROLES_ASIGNAN_ENCARGADO = ['Admin', 'Delegado']
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

# ----- Grupos y permisos de Django (pauta: perfiles = grupos) -----
GRUPO_DE_ROL = {
    'Admin': 'Administrador',
    'Coordinador': 'Supervisor',
    'Delegado': 'Delegado',
    'Funcionario': 'Administrativo',
}

_VER = ['ActividadesApp.view_actividad', 'ActividadesApp.view_atencionsocial']
_AUSENCIAS = ['IndicadoresApp.view_ausencia', 'IndicadoresApp.add_ausencia', 'IndicadoresApp.delete_ausencia']
PERMISOS_POR_GRUPO = {
    'Administrador': _VER + [
        'ActividadesApp.add_actividad', 'ActividadesApp.add_evidencia', 'ActividadesApp.add_comentarioactividad',
        'ActividadesApp.change_actividad', 'ActividadesApp.delete_actividad',
        'ActividadesApp.validar_evidencia', 'ActividadesApp.asignar_encargado',
        'ActividadesApp.add_atencionsocial', 'ActividadesApp.change_atencionsocial', 'ActividadesApp.delete_atencionsocial',
        'ActividadesApp.view_territorio', 'ActividadesApp.add_territorio', 'ActividadesApp.change_territorio',
        'ActividadesApp.delete_territorio',
        'UsuarioApp.view_usuario', 'UsuarioApp.add_usuario', 'UsuarioApp.change_usuario', 'UsuarioApp.delete_usuario',
        'UsuarioApp.view_delegacion', 'UsuarioApp.add_delegacion', 'UsuarioApp.change_delegacion',
        'UsuarioApp.delete_delegacion',
        'IndicadoresApp.view_metadesempeno', 'IndicadoresApp.add_metadesempeno', 'IndicadoresApp.change_metadesempeno',
        'IndicadoresApp.delete_metadesempeno',
        'AuditoriaApp.view_auditoria',
    ] + _AUSENCIAS,
    # Coordinador: gestiona delegaciones (con sus territorios) y delegados, y supervisa. No interviene en las
    # actividades de los funcionarios
    'Supervisor': _VER + [
        'ActividadesApp.view_territorio', 'ActividadesApp.add_territorio', 'ActividadesApp.change_territorio',
        'ActividadesApp.delete_territorio',
        'UsuarioApp.view_usuario', 'UsuarioApp.add_usuario', 'UsuarioApp.change_usuario',
        'UsuarioApp.view_delegacion', 'UsuarioApp.add_delegacion', 'UsuarioApp.change_delegacion',
        'UsuarioApp.delete_delegacion',
        'IndicadoresApp.view_metadesempeno',
        'AuditoriaApp.view_auditoria',
    ] + _AUSENCIAS,
    # Delegado: valida, gestiona su equipo y sus metas, y registra sus propias gestiones (sin puntaje)
    'Delegado': _VER + [
        'ActividadesApp.add_actividad', 'ActividadesApp.add_evidencia',
        'ActividadesApp.add_comentarioactividad', 'ActividadesApp.validar_evidencia', 'ActividadesApp.asignar_encargado',
        'UsuarioApp.view_usuario', 'UsuarioApp.add_usuario', 'UsuarioApp.change_usuario', 'UsuarioApp.view_delegacion',
        'IndicadoresApp.view_metadesempeno', 'IndicadoresApp.add_metadesempeno', 'IndicadoresApp.change_metadesempeno',
        'IndicadoresApp.delete_metadesempeno',
    ] + _AUSENCIAS,
    'Administrativo': _VER + [
        'ActividadesApp.add_actividad', 'ActividadesApp.add_evidencia', 'ActividadesApp.add_comentarioactividad',
        'ActividadesApp.add_atencionsocial', 'ActividadesApp.change_atencionsocial',
    ],
}

