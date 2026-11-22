from AuditoriaApp.models import Auditoria
from AuditoriaApp.origen import peticion_actual, ip_de, canal_de


def registrar_auditoria(usuario, evento, entidad, id_entidad, anterior='', nuevo=''):
    """Equivale a Auditoria.registrar(usuario, evento, entidad, id_entidad, anterior, nuevo) {static}.
    Se llama desde las views cada vez que se crea o modifica un registro. El origen (IP y canal) sale de la
    petición en curso, que guarda OrigenAuditoriaMiddleware."""
    if usuario is not None and not usuario.is_authenticated:
        usuario = None
    peticion = peticion_actual()
    return Auditoria.objects.create(
        usuario=usuario,
        usuario_texto=f"{usuario.get_full_name() or usuario.username} ({usuario.username})" if usuario else '',
        evento=evento,
        entidad=entidad,
        id_entidad=str(id_entidad),
        valor_anterior=str(anterior),
        valor_nuevo=str(nuevo),
        ip=ip_de(peticion),
        canal=canal_de(peticion),
    )
