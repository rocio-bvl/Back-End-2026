from decimal import Decimal

from IndicadoresApp.models import MetaDesempeno, IndicadorDesempeno


def indicadores_usuario(usuario, periodo, fecha):
    lista = []
    if periodo is None or usuario.cargo_id is None:
        return lista
    metas = MetaDesempeno.objects.filter(cargo_id=usuario.cargo_id, periodo=periodo).select_related('item', 'periodo')
    for meta in metas:
        indicador = IndicadorDesempeno.objects.filter(usuario=usuario, meta=meta, fecha_calculo=fecha).first()
        if indicador is None:
            indicador = IndicadorDesempeno(usuario=usuario, meta=meta, fecha_calculo=fecha)
        indicador.calcular()
        lista.append(indicador)
    return lista


def total_ponderado(indicadores):
    total = Decimal('0')
    for indicador in indicadores:
        total = total + indicador.cumplimiento_ponderado
    return round(total, 1)


def seguimiento_usuario(usuario, periodo, fecha):
    indicadores = indicadores_usuario(usuario, periodo, fecha)
    avance = total_ponderado(indicadores)
    objetivo_hoy = periodo.porcentaje_transcurrido(fecha)
    minimo = round(objetivo_hoy * periodo.umbral_ambar / 100, 1)
    if objetivo_hoy > 0:
        logrado = avance * 100 / objetivo_hoy
    else:
        logrado = Decimal('100')
    return {
        'id': usuario.pk,
        'area': usuario.area() or '-',
        'responsable': usuario.get_full_name() or usuario.username,
        'objetivo_hoy': objetivo_hoy,
        'minimo': minimo,
        'avance_logrado': avance,
        'color': periodo.calcular_semaforo(logrado),
    }
