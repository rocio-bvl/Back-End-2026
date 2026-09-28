from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404

from AuditoriaApp.models import Auditoria
from AuditoriaApp.registro import registrar_auditoria
from IndicadoresApp.models import periodo_vigente
from UsuarioApp.forms import UsuarioCrearForm, UsuarioEditarForm
from UsuarioApp.funciones import limpiar_rut, acceso_denegado
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion


def inicio(request):
    if request.user.is_authenticated:
        return redirect('indicadores:dashboard')
    return redirect('users:login')


def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect('indicadores:dashboard')

    if request.method == 'POST':
        datos = request.POST.copy()
        datos['username'] = limpiar_rut(datos.get('username', ''))  # acepta 12.345.678-9
        form = AuthenticationForm(request, data=datos)
        if form.is_valid():
            login(request, form.get_user())
            return redirect('indicadores:dashboard')
    else:
        form = AuthenticationForm(request)

    return render(request, 'users/login.html', {'form': form})


def cerrar_sesion(request):
    logout(request)
    return redirect('users:login')


def resumen_usuario(usuario):
    return (f"{usuario.username} | {usuario.get_full_name()} | {usuario.email} | rol={usuario.rol()} | "
            f"cargo={usuario.cargo} | delegacion={usuario.delegacion} | activo={usuario.is_active}")


def asignar_rol(usuario, codigo, asignado_por):
    if codigo == usuario.rol():
        return
    rol = Rol.objects.filter(codigo=codigo).first()
    if rol is None:
        return
    UsuarioRol.objects.filter(usuario=usuario).delete()
    UsuarioRol.objects.create(usuario=usuario, rol=rol, asignado_por=asignado_por)
    usuario.is_staff = codigo == 'Admin'
    usuario.is_superuser = codigo == 'Admin'
    usuario.save()


def administracion(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin']):
        return acceso_denegado(request, 'Administración')

    periodo = periodo_vigente()
    if periodo is None:
        periodo = {'nombre': 'Sin periodo vigente'}

    data = {
        'lista_usuarios': Usuario.objects.select_related('cargo', 'delegacion').all(),
        'periodo_activo': periodo,
        'cargos': Cargo.objects.filter(estado='ACTIVO'),
        'logs_auditoria': Auditoria.objects.select_related('usuario')[:50],
    }
    return render(request, 'users/administracion.html', data)


def usuario_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin']):
        return acceso_denegado(request, 'Crear Usuario')
    if request.method != 'POST':
        return redirect('users:administracion')

    form = UsuarioCrearForm(request.POST)
    if not form.is_valid():
        for campo, errores in form.errors.items():
            for error in errores:
                messages.error(request, f"{form.fields[campo].label if campo in form.fields else 'Error'}: {error}")
        return redirect('users:administracion')

    datos = form.cleaned_data
    cargo = None
    if datos['cargo']:
        cargo = Cargo.objects.filter(codigo__iexact=datos['cargo']).first()
        if cargo is None:
            cargo = Cargo.objects.filter(nombre__iexact=datos['cargo']).first()
        if cargo is None:
            messages.warning(request, f"No existe el cargo '{datos['cargo']}'. El usuario quedó sin cargo; asígnelo con el botón de edición.")

    usuario = Usuario(
        username=datos['rut'],
        email=datos['email'],
        first_name=datos['first_name'],
        last_name=datos['last_name'],
        cargo=cargo,
    )
    usuario.set_password(datos['password1'])
    usuario.save()
    asignar_rol(usuario, datos['rol'], request.user)

    registrar_auditoria(request.user, 'CREACION', 'Usuario', usuario.pk, '', resumen_usuario(usuario))
    messages.success(request, f"Usuario {usuario.get_full_name()} creado correctamente.")
    return redirect('users:administracion')


def usuario_editar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin']):
        return acceso_denegado(request, 'Editar Usuario')

    usuario = get_object_or_404(Usuario, pk=pk)
    antes = resumen_usuario(usuario)  # se guarda antes de que el formulario modifique el objeto
    rol_actual = usuario.rol()
    if usuario.is_superuser and rol_actual == '':
        rol_actual = 'Admin'

    if request.method == 'POST':
        form = UsuarioEditarForm(request.POST, instance=usuario)
        if form.is_valid():
            es_el_mismo = usuario.pk == request.user.pk
            if es_el_mismo and (not form.cleaned_data['is_active'] or form.cleaned_data['rol'] != rol_actual):
                messages.error(request, "No puede desactivarse ni cambiarse el rol a sí mismo.")
                return redirect('users:usuario_editar', pk=usuario.pk)

            usuario = form.save(commit=False)
            usuario.delegacion = Delegacion.objects.filter(nombre=form.cleaned_data['delegacion']).first()
            usuario.save()
            if form.cleaned_data['rol'] != rol_actual:
                asignar_rol(usuario, form.cleaned_data['rol'], request.user)

            registrar_auditoria(request.user, 'MODIFICACION', 'Usuario', usuario.pk, antes, resumen_usuario(usuario))
            messages.success(request, f"Usuario {usuario.get_full_name()} actualizado.")
            return redirect('users:administracion')
    else:
        delegacion = 'GENERAL'
        if usuario.delegacion:
            delegacion = usuario.delegacion.nombre
        form = UsuarioEditarForm(instance=usuario, initial={'rol': rol_actual, 'delegacion': delegacion})

    data = {
        'form': form,
        'object': usuario,
        'cargos': Cargo.objects.filter(estado='ACTIVO'),
    }
    return render(request, 'users/usuario_form.html', data)
