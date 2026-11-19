from decimal import Decimal

from IndicadoresApp.models import IndicadorDesempeno, metas_para, dias_ausencia, estado_medicion


def indicadores_usuario(usuario, periodo, fecha):
    lista = []
    if periodo is None or usuario.cargo_id is None:
        return lista
    metas = metas_para(usuario.cargo_id, periodo, usuario.delegacion_id)
    for meta in metas:
        indicador = IndicadorDesempeno.objects.filter(usuario=usuario, meta=meta, fecha_calculo=fecha).first()
        if indicador is None:
            indicador = IndicadorDesempeno(usuario=usuario, meta=meta, fecha_calculo=fecha)
        indicador.calcular()
        lista.append(indicador)
    return lista


def total_ponderado(indicadores):
    """Cumplimiento total: la suma de los cumplimientos ponderados, más los ajustes (por ejemplo, las felicitaciones).
    Nunca supera el tope del periodo (120%), aunque los ajustes lo empujen más arriba."""
    total = Decimal('0')
    for indicador in indicadores:
        total = total + indicador.cumplimiento_ponderado
    meta = getattr(indicadores[0], 'meta', None) if indicadores else None
    if meta is not None:
        total = min(total, meta.periodo.tope_cumplimiento)
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
    fila = {
        'id': usuario.pk,
        'area': usuario.area() or '-',
        'responsable': usuario.get_full_name() or usuario.username,
        'objetivo_hoy': objetivo_hoy,
        'minimo': minimo,
        'avance_logrado': avance,
        'color': periodo.calcular_semaforo(logrado),
        'dias_ausencia': indicadores[0].dias_ausencia() if indicadores else dias_ausencia(usuario, periodo),
        'items_en_tope': [ind.meta.item.nombre for ind in indicadores if ind.en_tope()],
    }
    # Si la ponderación de su cargo no suma 100% (o falta una meta), el funcionario no se mide: sin color (RN-001)
    fila['sin_medir'] = estado_medicion(usuario.cargo_id, periodo, usuario.delegacion_id) if usuario.cargo_id else ''
    if fila['sin_medir']:
        fila['color'] = ''
    return fila


def ranking_cargo(usuario, periodo, fecha):
    """Avance Actual de todos los funcionarios activos con el mismo cargo (de todas las delegaciones), de mayor a
    menor. Usa el mismo cálculo de la tarjeta Avance Actual (seguimiento_usuario), así ambos números coinciden.
    Los empates comparten el lugar (dos con 40% quedan 1° y 1°, el siguiente 3°)."""
    from UsuarioApp.models import Usuario
    if periodo is None or usuario.cargo_id is None:
        return []
    pares = Usuario.objects.filter(is_active=True, cargo_id=usuario.cargo_id).select_related('delegacion', 'cargo', 'cargo__area')
    filas = []
    for par in pares:
        seguimiento = seguimiento_usuario(par, periodo, fecha)
        if seguimiento['sin_medir']:
            continue  # cargo con ponderación incompleta: no entra al ranking
        filas.append({
            'id': par.pk,
            'nombre': par.get_full_name() or par.username,
            'delegacion': str(par.delegacion) if par.delegacion_id else 'Sin delegación',
            'avance': seguimiento['avance_logrado'],
            'es_yo': par.pk == usuario.pk,
        })
    filas.sort(key=lambda fila: (-fila['avance'], fila['nombre']))
    for indice, fila in enumerate(filas):
        if indice > 0 and fila['avance'] == filas[indice - 1]['avance']:
            fila['lugar'] = filas[indice - 1]['lugar']
        else:
            fila['lugar'] = indice + 1
    return filas
