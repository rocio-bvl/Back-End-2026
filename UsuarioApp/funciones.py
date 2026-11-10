"""Funciones de apoyo que usan las views de todas las apps."""
from django.contrib import messages
from django.shortcuts import redirect

from AuditoriaApp.registro import registrar_auditoria
from UsuarioApp.models import Delegacion

from functools import wraps
from django.contrib.auth.decorators import login_required


# ---------------------------------------------------------------------------
# RUT: se guarda sin puntos y con guion (22043402-8). Lo mismo valida static/js/validaciones.js en el navegador
# ---------------------------------------------------------------------------
def limpiar_rut(rut):
    """Paso 1 del cálculo: quita puntos y espacios y deja el guion antes del dígito verificador."""
    rut = rut.replace('.', '').replace(' ', '').upper()
    if '-' not in rut and len(rut) > 1:
        rut = rut[:-1] + '-' + rut[-1]
    return rut


def validar_rut(rut):
    """Dígito verificador por módulo 11:
    2. se separa el número del dígito verificador;
    3 y 4. cada dígito del número, de derecha a izquierda, se multiplica por la serie 2, 3, 4, 5, 6, 7 (y vuelve a 2);
    5. se suman los productos;
    6 y 7. el dígito es 11 menos el resto de dividir la suma por 11. Si da 10 es K, y si da 11 es 0."""
    rut = limpiar_rut(rut)
    if '-' not in rut:
        return False
    numero, dv = rut.split('-')
    if not numero.isdigit() or len(dv) != 1:
        return False
    suma = 0
    multiplicador = 2
    for digito in reversed(numero):
        suma = suma + int(digito) * multiplicador
        multiplicador = multiplicador + 1
        if multiplicador > 7:
            multiplicador = 2
    resto = 11 - (suma % 11)
    if resto == 11:
        esperado = '0'
    elif resto == 10:
        esperado = 'K'
    else:
        esperado = str(resto)
    return dv == esperado


# ---------------------------------------------------------------------------
# Teléfono: 9 dígitos chilenos (celular 9XXXXXXXX o fijo con código de área), con o sin +56
# ---------------------------------------------------------------------------
def normalizar_telefono(telefono):
    """Devuelve el teléfono con un solo formato (+56 9 1234 5678) o None si no es un número chileno válido.
    Acepta espacios, guiones, paréntesis y el prefijo +56 o 56."""
    digitos = ''.join(c for c in (telefono or '') if c.isdigit())
    if len(digitos) == 11 and digitos.startswith('56'):
        digitos = digitos[2:]
    if len(digitos) != 9 or digitos[0] in '01':
        return None
    return f"+56 {digitos[0]} {digitos[1:5]} {digitos[5:]}"


MENSAJE_TELEFONO = "Escriba un teléfono chileno de 9 dígitos, por ejemplo 9 1234 5678 o +56 51 220 6600."


def delegacion_seleccionada(request):
    usuario = request.user
    if usuario.tiene_rol(['Admin', 'Coordinador']):
        codigo = request.GET.get('delegacion', 'GENERAL')
    elif usuario.delegacion:
        codigo = usuario.delegacion.nombre
    else:
        codigo = 'GENERAL'

    delegacion = Delegacion.objects.filter(nombre=codigo).first()
    if delegacion is None:
        return 'GENERAL', None, 'General'
    return codigo, delegacion, str(delegacion)


def acceso_denegado(request, pantalla):
    registrar_auditoria(request.user, 'ACCESO_DENEGADO', 'Vista', request.path[:50],
                        '', f"Intento de acceso a {pantalla}")
    messages.error(request, f"No tienes permisos para acceder a {pantalla}.")
    return redirect('actividades:mi_gestion')

def permiso_requerido(permiso, pantalla):
    """Pide sesión y el permiso de Django (ej. 'IndicadoresApp.view_metadesempeno').
    Sin sesión manda al login; sin permiso, lo anota en auditoría y vuelve a Mi Gestión."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.has_perm(permiso):
                return acceso_denegado(request, pantalla)
            return vista(request, *args, **kwargs)
        return login_required(envoltura)
    return decorador


def opciones_delegacion():
    """Opciones de los <select> de delegación: 'GENERAL' (toda la municipalidad) y las delegaciones activas.
    Se arma desde la base de datos porque el Administrador agrega y edita delegaciones en Gestión."""
    opciones = [('GENERAL', 'General (Toda la Municipalidad)')]
    for delegacion in Delegacion.objects.filter(estado='ACTIVO').order_by('nombre_visible'):
        opciones.append((delegacion.nombre, str(delegacion)))
    return opciones
