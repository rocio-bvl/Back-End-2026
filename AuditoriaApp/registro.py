from AuditoriaApp.models import Auditoria


def registrar_auditoria(usuario, evento, entidad, id_entidad, anterior='', nuevo=''):
    """Equivale a Auditoria.registrar(usuario, evento, entidad, id_entidad, anterior, nuevo) {static}.
    Se llama desde las views cada vez que se crea o modifica un registro."""
    if usuario is not None and not usuario.is_authenticated:
        usuario = None
    return Auditoria.objects.create(
        usuario=usuario,
        evento=evento,
        entidad=entidad,
        id_entidad=str(id_entidad),
        valor_anterior=str(anterior),
        valor_nuevo=str(nuevo),
    )
