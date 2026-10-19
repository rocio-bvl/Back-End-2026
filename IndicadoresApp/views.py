from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone

from ActividadesApp.models import Actividad
from AuditoriaApp.registro import registrar_auditoria
from IndicadoresApp.calculos import seguimiento_usuario
from IndicadoresApp.models import MetaDesempeno, periodo_vigente
from UsuarioApp.funciones import delegacion_seleccionada, acceso_denegado
from UsuarioApp.models import Usuario, Cargo, Catalogo


def usuarios_evaluados(delegacion):
    usuarios = Usuario.objects.filter(is_active=True, cargo__isnull=False).select_related('cargo', 'cargo__area')
    if delegacion is not None:
        usuarios = usuarios.filter(delegacion=delegacion)
    return usuarios


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('users:login')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)

    # Compromisos pendientes = actividades que siguen en el Tubo (sin evidencia)
    compromisos = Actividad.objects.filter(estado='EN_TUBO')
    if delegacion is not None:
        compromisos = compromisos.filter(usuario__delegacion=delegacion)

    avance = Decimal('0')
    semaforo = 'Sin periodo vigente'
    if periodo is not None:
        filas = []
        for usuario in usuarios_evaluados(delegacion):
            filas.append(seguimiento_usuario(usuario, periodo, hoy))
        if filas:
            suma = Decimal('0')
            for fila in filas:
                suma = suma + fila['avance_logrado']
            avance = round(suma / len(filas), 1)
        objetivo = periodo.porcentaje_transcurrido(hoy)
        if objetivo > 0:
            color = periodo.calcular_semaforo(avance * 100 / objetivo)
        else:
            color = 'VERDE'
        semaforo = {'VERDE': 'Verde', 'AMBAR': 'Ámbar', 'ROJO': 'Rojo'}[color]

    data = {
        'delegacion_actual': f"Delegación {nombre}",
        'compromisos_pendientes_count': compromisos.count(),
        'avance_periodo_porcentaje': f"{avance}%",
        'semaforo_estado': semaforo,
    }
    return render(request, 'indicadores/dashboard.html', data)


def semaforo(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Consulta']):
        return acceso_denegado(request, 'Semáforo')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    hoy = timezone.localdate()
    periodo = periodo_vigente(hoy)

    seguimiento = []
    dias_transcurridos = 0
    porcentaje_esperado = 0
    if periodo is not None:
        dias_transcurridos = periodo.calcular_dias_transcurridos(hoy)
        porcentaje_esperado = periodo.porcentaje_transcurrido(hoy)
        for usuario in usuarios_evaluados(delegacion):
            seguimiento.append(seguimiento_usuario(usuario, periodo, hoy))
    else:
        messages.warning(request, "No hay un periodo vigente para la fecha de hoy.")

    data = {
        'seguimiento': seguimiento,
        'dias_transcurridos': dias_transcurridos,
        'porcentaje_esperado': porcentaje_esperado,
        'periodo': periodo,
    }
    return render(request, 'indicadores/semaforo.html', data)


def resumen_delegacion(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.tiene_rol(['Admin', 'Coordinador', 'Delegado', 'Consulta']):
        return acceso_denegado(request, 'Resumen de Delegación')

    codigo, delegacion, nombre = delegacion_seleccionada(request)
    periodo = periodo_vigente()
    equipo = usuarios_evaluados(delegacion)

    comisiones = []
    if periodo is not None:
        # Una fila por cada meta de cada cargo presente en el equipo
        cargos = Cargo.objects.filter(usuarios__in=equipo).distinct()
        for cargo in cargos:
            integrantes = equipo.filter(cargo=cargo)
            cantidad = integrantes.count()
            for meta in MetaDesempeno.objects.filter(cargo=cargo, periodo=periodo).select_related('item'):
                meta_total = meta.valor_objetivo * cantidad
                avance = Actividad.objects.filter(usuario__in=integrantes, item=meta.item, periodo=periodo, estado='VALIDADA').count()
                if meta_total > 0:
                    porcentaje = round(Decimal(avance) * 100 / meta_total, 1)
                else:
                    porcentaje = Decimal('0')
                if porcentaje > periodo.tope_cumplimiento:
                    porcentaje = periodo.tope_cumplimiento
                comisiones.append({
                    'id': meta.pk,
                    'cargo': cargo.nombre,
                    'nombre': meta.item.nombre,
                    'ponderacion': meta.ponderador,
                    'meta': meta_total,
                    'avance': avance,
                    'porcentaje_cumplimiento': porcentaje,
                    'total_ponderado': round(porcentaje * meta.ponderador / 100, 1),
                })

    data = {
        'delegacion_nombre': f"Delegación {nombre}",
        'comisiones': comisiones,
        'equipo': equipo,
    }
    return render(request, 'indicadores/resumen_delegacion.html', data)


def url_metas():
    """Vuelve al panel de administración con la pestaña de metas abierta."""
    return reverse('users:administracion') + '#goals'


def guardar_metas(request):
    if not request.user.is_authenticated:
        return redirect('users:login')
    if not request.user.puede_administrar():
        return acceso_denegado(request, 'Parametrización de Metas')
    if request.method != 'POST':
        return redirect(url_metas())

    periodo = periodo_vigente()
    id_cargo = request.POST.get('cargo', '')
    id_item = request.POST.get('item', '')
    # isdigit evita un error 500 si llega un valor que no es número
    cargo = Cargo.objects.filter(pk=id_cargo, estado='ACTIVO').first() if id_cargo.isdigit() else None
    item = Catalogo.objects.filter(pk=id_item, tipo='ITEM_GESTION', estado='ACTIVO').first() if id_item.isdigit() else None
    valor = request.POST.get('valor_objetivo', '').strip()
    ponderador = request.POST.get('ponderador', '').strip()

    if periodo is None or cargo is None or item is None or not valor.isdigit() or ponderador == '':
        if periodo is None:
            messages.error(request, "No hay un periodo vigente. Créelo en Django Admin (Periodos) antes de definir metas.")
        else:
            messages.error(request, "Complete cargo, ítem, meta (número entero) y ponderador.")
        return redirect(url_metas())

    # El ponderador debe ser un número entre 0 (excluido) y 100. Se acepta coma decimal: 33,5
    try:
        ponderador = Decimal(ponderador.replace(',', '.'))
    except InvalidOperation:
        messages.error(request, "El ponderador debe ser un número (por ejemplo 40 o 33.5).")
        return redirect(url_metas())
    if ponderador <= 0 or ponderador > 100:
        messages.error(request, "El ponderador debe ser mayor que 0 y no puede superar 100%.")
        return redirect(url_metas())

    meta = MetaDesempeno.objects.filter(cargo=cargo, item=item, periodo=periodo).first()
    if meta is None:
        meta = MetaDesempeno(cargo=cargo, item=item, periodo=periodo)
        evento = 'CREACION'
        antes = ''
    else:
        evento = 'MODIFICACION'
        antes = f"{meta} = {meta.valor_objetivo} ({meta.ponderador}%)"

    # Las metas de un cargo en el periodo no pueden sumar más de 100%
    total = cargo.total_ponderadores(periodo, excluir=meta) + ponderador
    if total > 100:
        messages.error(request, f"Con esta meta los ponderadores del cargo {cargo} sumarían {total}%. "
                                "El total no puede superar 100%.")
        return redirect(url_metas())

    meta.valor_objetivo = int(valor)
    meta.ponderador = ponderador
    meta.save()
    registrar_auditoria(request.user, evento, 'MetaDesempeno', meta.pk, antes, f"{meta} = {meta.valor_objetivo} ({meta.ponderador}%)")
    messages.success(request, "Meta guardada correctamente.")
    if total < 100:
        messages.warning(request, f"Los ponderadores del cargo {cargo} suman {total}%. Faltan {100 - total}% para completar 100%.")
    return redirect(url_metas())
