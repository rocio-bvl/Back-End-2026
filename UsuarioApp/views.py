from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404

from AuditoriaApp.models import Auditoria
from AuditoriaApp.registro import registrar_auditoria
from IndicadoresApp.models import MetaDesempeno, periodo_vigente
from UsuarioApp.forms import UsuarioCrearForm, UsuarioEditarForm
from UsuarioApp.funciones import limpiar_rut, acceso_denegado
from UsuarioApp.choices import opciones_delegacion
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo


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
    # Admin = superusuario; Coordinador = staff con permisos restringidos en Django Admin
    usuario.sincronizar_acceso_admin()


def administracion(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_administrar():
        return acceso_denegado(request, 'Administración')

    periodo = periodo_vigente()

    # Metas del periodo vigente agrupadas por cargo, con la suma de ponderadores (debe ser 100%)
    metas_por_cargo = []
    if periodo is not None:
        cargo_actual = None
        for meta in MetaDesempeno.objects.filter(periodo=periodo).select_related('cargo', 'item').order_by('cargo__nombre', 'item__id'):
            if cargo_actual is None or cargo_actual['cargo'] != meta.cargo:
                cargo_actual = {'cargo': meta.cargo, 'metas': [], 'total': 0}
                metas_por_cargo.append(cargo_actual)
            cargo_actual['metas'].append(meta)
            cargo_actual['total'] = cargo_actual['total'] + meta.ponderador
    if periodo is None:
        periodo = {'nombre': 'Sin periodo vigente'}

    usuarios = list(Usuario.objects.select_related('cargo', 'delegacion').all())
    for usr in usuarios:
        # El Coordinador ve a todos, pero no puede modificar Administradores ni otros Coordinadores
        usr.editable = request.user.puede_editar_usuario(usr)

    data = {
        'lista_usuarios': usuarios,
        'periodo_activo': periodo,
        'cargos': Cargo.objects.filter(estado='ACTIVO'),
        'items_gestion': Catalogo.objects.filter(tipo='ITEM_GESTION', estado='ACTIVO').order_by('id'),
        'metas_por_cargo': metas_por_cargo,
        'hay_periodo': not isinstance(periodo, dict),
        'roles_asignables': request.user.roles_asignables(),
        'opciones_delegacion': opciones_delegacion,
        'logs_auditoria': Auditoria.objects.select_related('usuario')[:50],
    }
    return render(request, 'users/administracion.html', data)


def usuario_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_administrar():
        return acceso_denegado(request, 'Crear Usuario')
    if request.method != 'POST':
        return redirect('users:administracion')

    form = UsuarioCrearForm(request.POST, roles_permitidos=request.user.roles_asignables())
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
        # 'GENERAL' o vacío no existe como fila: el usuario queda sin delegación (Admin, Coordinador)
        delegacion=Delegacion.objects.filter(nombre=datos.get('delegacion') or '').first(),
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
    if not request.user.puede_administrar():
        return acceso_denegado(request, 'Editar Usuario')

    usuario = get_object_or_404(Usuario, pk=pk)
    if not request.user.puede_editar_usuario(usuario):
        messages.error(request, "Un Coordinador no puede modificar Administradores ni a otros Coordinadores.")
        return redirect('users:administracion')
    antes = resumen_usuario(usuario)  # se guarda antes de que el formulario modifique el objeto
    rol_actual = usuario.rol()
    if usuario.is_superuser and rol_actual == '':
        rol_actual = 'Admin'

    # Roles del selector. Si el Coordinador se edita a sí mismo, su rol actual se muestra (no lo puede cambiar)
    roles_permitidos = request.user.roles_asignables()
    if rol_actual and rol_actual not in [codigo for codigo, nombre in roles_permitidos]:
        roles_permitidos = roles_permitidos + [(rol_actual, rol_actual)]

    if request.method == 'POST':
        form = UsuarioEditarForm(request.POST, instance=usuario, roles_permitidos=roles_permitidos)
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
        form = UsuarioEditarForm(instance=usuario, initial={'rol': rol_actual, 'delegacion': delegacion}, roles_permitidos=roles_permitidos)

    data = {
        'form': form,
        'object': usuario,
        'cargos': Cargo.objects.filter(estado='ACTIVO'),
        'roles_permitidos': roles_permitidos,
        'opciones_delegacion': opciones_delegacion,
    }
    return render(request, 'users/usuario_form.html', data)
