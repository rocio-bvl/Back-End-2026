from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from AuditoriaApp.registro import registrar_auditoria
from django.db.models import Q, ProtectedError

from ActividadesApp.models import Territorio
from IndicadoresApp.forms import MetaForm
from IndicadoresApp.models import MetaDesempeno, periodo_vigente
from UsuarioApp.forms import UsuarioCrearForm, UsuarioEditarForm, PerfilForm, DelegacionForm, TerritorioFormSet
from UsuarioApp.funciones import limpiar_rut, acceso_denegado
from UsuarioApp.funciones import opciones_delegacion
from UsuarioApp.models import Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo


def inicio(request):
    if request.user.is_authenticated:
        return redirect('actividades:mi_gestion')
    return redirect('users:login')


def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect('actividades:mi_gestion')

    if request.method == 'POST':
        datos = request.POST.copy()
        datos['username'] = limpiar_rut(datos.get('username', ''))  # acepta 12.345.678-9
        form = AuthenticationForm(request, data=datos)
        if form.is_valid():
            login(request, form.get_user())
            # Al entrar, cada usuario llega a su perfil (Mi Gestión), que se adapta a su rol
            return redirect('actividades:mi_gestion')
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
    # Admin = superusuario; los demás roles no entran a Django Admin
    usuario.sincronizar_acceso_admin()


def metas_agrupadas(periodo, usuario):
    """Metas del periodo agrupadas por alcance (General y cada delegación) y, dentro, por cargo.
    El Delegado ve las generales y las de su delegación."""
    grupos = []
    if periodo is None:
        return grupos
    metas = MetaDesempeno.objects.filter(periodo=periodo).select_related('cargo', 'item', 'delegacion')
    if usuario.es_delegado():
        metas = metas.filter(Q(delegacion__isnull=True) | Q(delegacion_id=usuario.delegacion_id))
    alcance_actual = None
    cargo_actual = None
    for meta in metas.order_by('delegacion__nombre_visible', 'cargo__nombre', 'item__id'):
        alcance = str(meta.delegacion) if meta.delegacion else 'General (toda la municipalidad)'
        if alcance_actual is None or alcance_actual['nombre'] != alcance:
            alcance_actual = {'nombre': alcance, 'general': meta.delegacion is None, 'cargos': []}
            grupos.append(alcance_actual)
            cargo_actual = None
        if cargo_actual is None or cargo_actual['cargo'] != meta.cargo:
            cargo_actual = {'cargo': meta.cargo, 'metas': [], 'total': 0}
            alcance_actual['cargos'].append(cargo_actual)
        meta.editable = usuario.puede_editar_meta(meta)
        cargo_actual['metas'].append(meta)
        cargo_actual['total'] = cargo_actual['total'] + meta.ponderador
    # Las generales primero
    grupos.sort(key=lambda grupo: not grupo['general'])
    return grupos


def delegaciones_con_equipo():
    """Cada delegación con su(s) Delegado(s), sus territorios con los Funcionarios de cada uno, y los
    Funcionarios que todavía no tienen territorio."""
    lista = []
    for delegacion in Delegacion.objects.order_by('nombre_visible'):
        funcionarios = list(delegacion.funcionarios().select_related('territorio', 'cargo'))
        territorios = []
        for territorio in Territorio.objects.filter(delegacion=delegacion).order_by('nombre'):
            territorios.append({'territorio': territorio,
                                'funcionarios': [f for f in funcionarios if f.territorio_id == territorio.pk]})
        lista.append({
            'delegacion': delegacion,
            'delegados': list(delegacion.delegados()),
            'territorios': territorios,
            'sin_territorio': [f for f in funcionarios if f.territorio_id is None],
            'total_funcionarios': len(funcionarios),
        })
    return lista


def administracion(request):
    """Admin: Gestión (delegaciones y usuarios, con todos los cambios) y Metas.
    Coordinador: lo mismo, solo para visualizar (para él la pestaña se llama Usuarios).
    Delegado: los Funcionarios de su delegación (filtra por territorio) y las metas de su delegación."""
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_ver_usuarios():
        return acceso_denegado(request, 'Administración')

    usuario = request.user
    periodo = periodo_vigente()

    # ----- Usuarios, con filtros -----
    filtros = {
        'cargo': request.GET.get('cargo', ''),
        'delegacion': request.GET.get('f_delegacion', ''),
        'territorio': request.GET.get('territorio', ''),
        'q': request.GET.get('q', '').strip(),
    }
    usuarios = usuario.usuarios_visibles()
    if filtros['territorio'].isdigit():
        usuarios = usuarios.filter(territorio_id=filtros['territorio'])
    if not usuario.es_delegado():
        # El Delegado solo filtra por territorio
        if filtros['cargo'].isdigit():
            usuarios = usuarios.filter(cargo_id=filtros['cargo'])
        if filtros['delegacion']:
            usuarios = usuarios.filter(delegacion__nombre=filtros['delegacion'])
        if filtros['q']:
            usuarios = usuarios.filter(Q(username__icontains=filtros['q']) | Q(first_name__icontains=filtros['q'])
                                       | Q(last_name__icontains=filtros['q']) | Q(email__icontains=filtros['q']))
    usuarios = list(usuarios)
    for usr in usuarios:
        usr.editable = usuario.puede_editar_usuario(usr)
        usr.eliminable = usuario.puede_eliminar_usuario(usr)

    territorios = Territorio.objects.filter(estado='ACTIVO').select_related('delegacion').order_by('delegacion__nombre_visible', 'nombre')
    if usuario.es_delegado():
        territorios = territorios.filter(delegacion_id=usuario.delegacion_id)

    if usuario.es_administrador():
        vista = 'admin'
    elif usuario.es_delegado():
        vista = 'delegado'
    else:
        vista = 'coordinador'

    data = {
        'vista': vista,
        'solo_mi_delegacion': usuario.es_delegado(),
        'lista_usuarios': usuarios,
        'filtros': filtros,
        'delegaciones': delegaciones_con_equipo() if vista != 'delegado' else [],
        'territorios': territorios,
        'periodo_activo': periodo,
        'hay_periodo': periodo is not None,
        'cargos': Cargo.objects.filter(estado='ACTIVO'),
        'items_gestion': Catalogo.objects.filter(tipo='ITEM_GESTION', estado='ACTIVO').order_by('id'),
        'metas_agrupadas': metas_agrupadas(periodo, usuario),
        'form_meta': MetaForm(usuario=usuario, periodo=periodo) if usuario.puede_gestionar_metas() else None,
        'roles_asignables': usuario.roles_asignables(),
        'opciones_delegacion': opciones_delegacion(),
        'pestana': request.GET.get('pestana', ''),
    }
    return render(request, 'users/administracion.html', data)


def usuario_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_gestionar_usuarios():
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
        telefono=datos.get('telefono', ''),
        territorio=datos.get('territorio'),
        # 'GENERAL' o vacío no existe como fila: el usuario queda sin delegación (Admin, Coordinador)
        delegacion=Delegacion.objects.filter(nombre=datos.get('delegacion') or '').first(),
    )
    if request.user.es_delegado():
        # El Delegado crea Funcionarios solo para su delegación, elija lo que elija en el formulario
        usuario.delegacion_id = request.user.delegacion_id
        if usuario.territorio is not None and usuario.territorio.delegacion_id != usuario.delegacion_id:
            usuario.territorio = None
    usuario.set_password(datos['password1'])
    usuario.save()
    asignar_rol(usuario, datos['rol'], request.user)

    registrar_auditoria(request.user, 'CREACION', 'Usuario', usuario.pk, '', resumen_usuario(usuario))
    messages.success(request, f"Usuario {usuario.get_full_name()} creado correctamente.")
    return redirect('users:administracion')


def usuario_editar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_gestionar_usuarios():
        return acceso_denegado(request, 'Editar Usuario')

    usuario = get_object_or_404(Usuario, pk=pk)
    if not request.user.puede_editar_usuario(usuario):
        messages.error(request, "Un Delegado solo puede modificar a los Funcionarios de su delegación.")
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
            if request.user.es_delegado():
                usuario.delegacion_id = request.user.delegacion_id  # no puede sacarlo de su delegación
            if usuario.territorio is not None and usuario.territorio.delegacion_id != usuario.delegacion_id:
                usuario.territorio = None
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
        'opciones_delegacion': opciones_delegacion(),
        'territorios': territorios_para_formulario(request.user),
        'solo_mi_delegacion': request.user.es_delegado(),
    }
    return render(request, 'users/usuario_form.html', data)


def territorios_para_formulario(usuario):
    territorios = Territorio.objects.filter(estado='ACTIVO').select_related('delegacion').order_by('delegacion__nombre_visible', 'nombre')
    if usuario.es_delegado():
        territorios = territorios.filter(delegacion_id=usuario.delegacion_id)
    return territorios


def usuario_eliminar(request, pk):
    """Elimina de verdad (solo el Administrador, con confirmación). Si el usuario tiene actividades, validaciones
    u otros registros que dependen de él, la base de datos no deja borrarlo: en ese caso se sugiere desactivarlo."""
    if not request.user.is_authenticated:
        return redirect('users:login')
    usuario = get_object_or_404(Usuario, pk=pk)
    if not request.user.puede_eliminar_usuario(usuario):
        return acceso_denegado(request, 'Eliminar Usuario')
    if request.method != 'POST':
        return redirect('users:administracion')
    antes = resumen_usuario(usuario)
    nombre = usuario.get_full_name() or usuario.username
    try:
        usuario.delete()
    except ProtectedError:
        messages.error(request, f"{nombre} tiene actividades u otros registros a su nombre y no se puede eliminar "
                                "sin perder ese historial. Desactívelo en su lugar.")
        return redirect(reverse('users:administracion') + '?pestana=usuarios')
    registrar_auditoria(request.user, 'ELIMINACION', 'Usuario', pk, antes, '')
    messages.success(request, f"Usuario {nombre} eliminado.")
    return redirect(reverse('users:administracion') + '?pestana=usuarios')


# ---------------------------------------------------------------------------
# Delegaciones (solo el Administrador las agrega, modifica y elimina)
# ---------------------------------------------------------------------------
def delegacion_form(request, delegacion=None):
    if request.method == 'POST':
        form = DelegacionForm(request.POST, instance=delegacion)
        formset = TerritorioFormSet(request.POST, instance=delegacion or Delegacion())
        if form.is_valid():
            antes = '' if delegacion is None else f"{delegacion} ({delegacion.ambito}, {delegacion.estado})"
            nueva = form.save(commit=False)
            formset = TerritorioFormSet(request.POST, instance=nueva)
            if formset.is_valid():
                nueva.save()
                formset.save()
                evento = 'CREACION' if delegacion is None else 'MODIFICACION'
                registrar_auditoria(request.user, evento, 'Delegacion', nueva.pk, antes,
                                    f"{nueva} ({nueva.ambito}, {nueva.estado})")
                messages.success(request, f"Delegación {nueva} guardada.")
                return redirect(reverse('users:administracion') + '?pestana=delegaciones')
    else:
        form = DelegacionForm(instance=delegacion)
        formset = TerritorioFormSet(instance=delegacion or Delegacion())
    return render(request, 'users/delegacion_form.html', {'form': form, 'formset': formset, 'object': delegacion})


def delegacion_crear(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.es_administrador():
        return acceso_denegado(request, 'Agregar Delegación')
    return delegacion_form(request)


def delegacion_editar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.es_administrador():
        return acceso_denegado(request, 'Modificar Delegación')
    return delegacion_form(request, get_object_or_404(Delegacion, pk=pk))


def delegacion_eliminar(request, pk):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.es_administrador():
        return acceso_denegado(request, 'Eliminar Delegación')
    delegacion = get_object_or_404(Delegacion, pk=pk)
    if request.method != 'POST':
        return redirect('users:administracion')
    nombre = str(delegacion)
    try:
        delegacion.delete()
    except ProtectedError:
        messages.error(request, f"La delegación {nombre} tiene usuarios, territorios o metas. Reasígnelos antes de "
                                "eliminarla, o márquela como Inactiva.")
        return redirect(reverse('users:administracion') + '?pestana=delegaciones')
    registrar_auditoria(request.user, 'ELIMINACION', 'Delegacion', pk, nombre, '')
    messages.success(request, f"Delegación {nombre} eliminada.")
    return redirect(reverse('users:administracion') + '?pestana=delegaciones')


def usuario_desactivar(request, pk):
    """Activa o desactiva un usuario (no se borra: conserva su historial de actividades y auditoría)."""
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_gestionar_usuarios():
        return acceso_denegado(request, 'Desactivar Usuario')
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method != 'POST':
        return redirect('users:administracion')
    if usuario.pk == request.user.pk or not request.user.puede_editar_usuario(usuario):
        messages.error(request, "No puede cambiar el estado de ese usuario.")
        return redirect('users:administracion')

    antes = resumen_usuario(usuario)
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=['is_active'])
    registrar_auditoria(request.user, 'MODIFICACION', 'Usuario', usuario.pk, antes, resumen_usuario(usuario))
    estado = "activado" if usuario.is_active else "desactivado"
    messages.success(request, f"Usuario {usuario.get_full_name()} {estado}.")
    return redirect('users:administracion')


def perfil_editar(request):
    """Cada usuario edita su propia foto, teléfono y correo."""
    if not request.user.is_authenticated:
        return redirect('users:login')
    usuario = request.user
    antes = resumen_usuario(usuario)
    if request.method == 'POST':
        form = PerfilForm(request.POST, request.FILES, instance=usuario)
        if form.is_valid():
            if form.cleaned_data.get('quitar_foto') and not request.FILES.get('foto'):
                usuario.foto = ''
            form.save()
            registrar_auditoria(usuario, 'MODIFICACION', 'Usuario', usuario.pk, antes, resumen_usuario(usuario))
            messages.success(request, "Perfil actualizado.")
            return redirect('actividades:mi_gestion')
    else:
        form = PerfilForm(instance=usuario)
    return render(request, 'users/perfil_form.html', {'form': form})
