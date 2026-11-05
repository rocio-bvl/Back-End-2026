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


def alertas_validacion(request):
    """Alerta para el Delegado apenas entra: evidencias de su delegación que llevan un día o más sin validar.
    El color sube con el atraso (1 o 2 días: amarillo; 3 o más: rojo), para que la alerta no pase inadvertida."""
    usuario = request.user
    if not usuario.is_authenticated or not usuario.es_delegado() or usuario.delegacion_id is None:
        return {}
    from django.utils import timezone
    from ActividadesApp.models import Evidencia
    hoy = timezone.localdate()
    pendientes = Evidencia.objects.filter(estado_revision='PENDIENTE', actividad__es_gestion=False,
                                          actividad__usuario__delegacion_id=usuario.delegacion_id)
    edades = [(hoy - timezone.localtime(fecha).date()).days for fecha in pendientes.values_list('fecha', flat=True)]
    atrasadas = [edad for edad in edades if edad >= 1]
    if not atrasadas:
        return {}
    return {'alerta_validacion': {'cantidad': len(atrasadas), 'mas_antigua': max(atrasadas),
                                  'nivel': 'danger' if max(atrasadas) >= 3 else 'warning'}}
