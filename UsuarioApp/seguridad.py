"""Protección del inicio de sesión (OWASP A07): límite de intentos y segundo factor por correo.

Límite de intentos: los fallos se guardan en la auditoría (evento LOGIN_FALLIDO, id_entidad = RUT).
Con LOGIN_MAX_INTENTOS fallos dentro de LOGIN_MINUTOS_BLOQUEO minutos, ese RUT queda bloqueado hasta que pase
ese tiempo. Un inicio de sesión exitoso (last_login) reinicia la cuenta.

Segundo factor: después de la contraseña correcta se envía un código de 6 dígitos al correo del usuario.
La sesión de Django recién se abre cuando el código es correcto. En la sesión solo se guarda un resumen (HMAC)
del código, nunca el código mismo.
"""
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from AuditoriaApp.models import Auditoria
from AuditoriaApp.registro import registrar_auditoria

CLAVE_SESION = 'mfa_pendiente'


def ip_cliente(request):
    return request.META.get('REMOTE_ADDR', '')


# ---------------------------------------------------------------------------
# Límite de intentos
# ---------------------------------------------------------------------------
def inicio_ventana(rut, usuario=None):
    """Desde cuándo se cuentan los fallos: los últimos minutos del bloqueo, o desde el último ingreso exitoso."""
    desde = timezone.now() - timedelta(minutes=settings.LOGIN_MINUTOS_BLOQUEO)
    if usuario is not None and usuario.last_login and usuario.last_login > desde:
        desde = usuario.last_login
    return desde


def fallos_recientes(rut, usuario=None):
    return Auditoria.objects.filter(evento='LOGIN_FALLIDO', id_entidad=rut,
                                    fecha__gt=inicio_ventana(rut, usuario)).order_by('fecha')


def minutos_bloqueo_restantes(rut, usuario=None):
    """0 si el RUT puede intentar; si no, los minutos que faltan para que se libere."""
    fallos = fallos_recientes(rut, usuario)
    if fallos.count() < settings.LOGIN_MAX_INTENTOS:
        return 0
    libera = fallos[fallos.count() - settings.LOGIN_MAX_INTENTOS].fecha + timedelta(minutes=settings.LOGIN_MINUTOS_BLOQUEO)
    segundos = (libera - timezone.now()).total_seconds()
    return max(1, int(segundos // 60) + 1) if segundos > 0 else 0


def registrar_fallo(request, rut, motivo):
    registrar_auditoria(None, 'LOGIN_FALLIDO', 'Inicio de sesión', rut, '', f"{motivo} | IP {ip_cliente(request)}")


def registrar_bloqueo(request, rut):
    registrar_auditoria(None, 'LOGIN_BLOQUEADO', 'Inicio de sesión', rut, '',
                        f"Intento con el RUT bloqueado | IP {ip_cliente(request)}")


# ---------------------------------------------------------------------------
# Segundo factor por correo
# ---------------------------------------------------------------------------
def resumen_codigo(usuario_id, codigo):
    return salted_hmac('sgr-mfa', f"{usuario_id}:{codigo}").hexdigest()


def correo_oculto(correo):
    """b***@gmail.com: el usuario reconoce su correo sin que la pantalla lo muestre completo."""
    nombre, _, dominio = correo.partition('@')
    return f"{nombre[:1]}***@{dominio}" if dominio else correo


def enviar_codigo(request, usuario):
    """Genera el código, lo envía y deja la verificación pendiente en la sesión. Devuelve False si el correo falla."""
    codigo = f"{secrets.randbelow(1000000):06d}"
    minutos = settings.MFA_MINUTOS_VIGENCIA
    try:
        send_mail(
            'SGR: código de verificación',
            f"Su código para ingresar al SGR es: {codigo}\n\nVence en {minutos} minutos. "
            f"Si usted no intentó ingresar, cambie su contraseña y avise al Administrador.",
            None, [usuario.email])
    except Exception:
        return False
    request.session[CLAVE_SESION] = {
        'usuario_id': usuario.pk,
        'resumen': resumen_codigo(usuario.pk, codigo),
        'vence': time.time() + minutos * 60,
        'intentos': 0,
    }
    return True


def pendiente(request):
    return request.session.get(CLAVE_SESION)


def descartar(request):
    request.session.pop(CLAVE_SESION, None)


def revisar_codigo(request, codigo):
    """'ok', 'incorrecto', 'vencido' o 'agotado' (demasiados intentos con el mismo código)."""
    datos = pendiente(request)
    if not datos or time.time() > datos['vence']:
        return 'vencido'
    datos['intentos'] += 1
    request.session[CLAVE_SESION] = datos
    if constant_time_compare(resumen_codigo(datos['usuario_id'], codigo.strip()), datos['resumen']):
        return 'ok'
    if datos['intentos'] >= settings.MFA_MAX_INTENTOS:
        return 'agotado'
    return 'incorrecto'
