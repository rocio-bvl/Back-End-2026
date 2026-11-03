"""Datos que necesitan todas las plantillas (se agregan solos a cada render)."""
from UsuarioApp.funciones import opciones_delegacion


def delegaciones_navbar(request):
    """Lista del selector de delegación de la barra superior.
    Admin y Coordinador: General y todas las delegaciones, en todas las pantallas (por defecto, General).
    Delegado: General o su delegación, solo en Administración, para filtrar las metas (por defecto, la suya)."""
    usuario = request.user
    if not usuario.is_authenticated:
        return {}
    if usuario.tiene_rol(['Admin', 'Coordinador']):
        return {'delegaciones_navbar': opciones_delegacion(), 'delegacion_por_defecto': 'GENERAL'}
    pantalla = request.resolver_match.view_name if request.resolver_match else ''
    if usuario.es_delegado() and usuario.delegacion and pantalla == 'users:administracion':
        return {
            'delegaciones_navbar': [('GENERAL', 'General (Toda la Municipalidad)'),
                                    (usuario.delegacion.nombre, str(usuario.delegacion))],
            'delegacion_por_defecto': usuario.delegacion.nombre,
        }
    return {}
