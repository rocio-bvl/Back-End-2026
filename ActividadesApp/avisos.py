"""Avisos por correo (además de las alertas en pantalla).

Se envían con transaction.on_commit: el correo sale solo si la operación quedó guardada. Si el servidor de
correo falla, la operación no se pierde: el aviso en pantalla sigue existiendo y el error queda en el log.
"""
import logging

from django.core.mail import send_mail
from django.db import transaction

logger = logging.getLogger(__name__)


def destinatarios_actividad(actividad):
    """Quien registró la actividad y su encargado (si tiene), sin repetir y solo con correo."""
    personas = [actividad.usuario, actividad.encargado]
    correos = []
    for persona in personas:
        if persona is not None and persona.is_active and persona.email and persona.email not in correos:
            correos.append(persona.email)
    return correos


def enviar(asunto, cuerpo, correos):
    if not correos:
        return
    try:
        send_mail(asunto, cuerpo, None, correos)
    except Exception:
        logger.exception("No se pudo enviar el aviso '%s'", asunto)


def aviso_rechazo(evidencia, observacion, verificador):
    actividad = evidencia.actividad
    asunto = f"SGR: evidencia rechazada en la actividad {actividad.folio()}"
    cuerpo = (f"La evidencia {evidencia.codigo()} de la actividad {actividad.folio()} fue rechazada por "
              f"{verificador.get_full_name() or verificador.username}.\n\n"
              f"Motivo: {observacion}\n\n"
              f"La actividad sigue vigente: ingrese al SGR y agregue una nueva evidencia.")
    correos = destinatarios_actividad(actividad)
    transaction.on_commit(lambda: enviar(asunto, cuerpo, correos))
