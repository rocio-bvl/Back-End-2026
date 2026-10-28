"""Datos que necesitan todas las plantillas (se agregan solos a cada render)."""
from UsuarioApp.funciones import opciones_delegacion


def delegaciones_navbar(request):
    """Lista del selector de delegación de la barra superior (solo Admin y Coordinador lo ven)."""
    if not request.user.is_authenticated or not request.user.tiene_rol(['Admin', 'Coordinador']):
        return {}
    return {'delegaciones_navbar': opciones_delegacion()}
