from decimal import Decimal

from IndicadoresApp.models import IndicadorDesempeno, dias_ausencia


def indicadores_usuario(usuario, periodo, fecha, datos=None):
    """Indicadores de cada meta del usuario. datos (DatosMedicion) trae del periodo lo necesario en pocas consultas;
    si no viene, se crea. No se guarda nada: el indicador se calcula al vuelo en cada pantalla."""
    if periodo is None or usuario.cargo_id is None:
        return []
    datos = datos or DatosMedicion(periodo)
    lista = []
    for meta in datos.metas_de(usuario.cargo_id, usuario.delegacion_id):
        indicador = datos.indicador(usuario, meta, fecha)
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


def seguimiento_usuario(usuario, periodo, fecha, datos=None):
    indicadores = indicadores_usuario(usuario, periodo, fecha, datos)
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
    fila['sin_medir'] = (datos or DatosMedicion(periodo)).estado(usuario.cargo_id, usuario.delegacion_id) if usuario.cargo_id else ''
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
    datos = DatosMedicion(periodo)  # una sola carga para todos los del cargo
    for par in pares:
        seguimiento = seguimiento_usuario(par, periodo, fecha, datos)
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


# ---------------------------------------------------------------------------
# Datos de la medición en pocas consultas (evita el problema N+1)
# ---------------------------------------------------------------------------
class DatosMedicion:
    """Carga UNA vez por pantalla todo lo que se necesita para medir a muchos funcionarios en un periodo:
    ponderaciones, metas, avance por responsable e ítem, ajustes y quiénes tienen ausencias. Antes cada funcionario
    hacía unas 40 consultas; ahora son unas 6 por pantalla, más una por funcionario con ausencias.
    Aplica las mismas reglas que calcular_avance, metas_aplicables y estado_medicion (models.py)."""

    def __init__(self, periodo, hasta=None):
        """hasta (fecha): mide como si fuera ese día, contando solo lo realizado hasta entonces (tendencia semanal)."""
        from django.db.models import Count, Q, Sum
        from django.db.models.functions import Coalesce
        from ActividadesApp.models import Actividad
        from IndicadoresApp.models import Ponderacion, MetaDesempeno, Ausencia, AjusteDesempeno
        self.periodo = periodo
        # Ponderación: {cargo: {ítem: ponderador}}
        self.ponderaciones = {}
        for p in Ponderacion.objects.filter(periodo=periodo).order_by('item_id'):
            self.ponderaciones.setdefault(p.cargo_id, {})[p.item_id] = p.ponderador
        # Metas: {(cargo, ítem, delegación o None): meta}, con el ponderador ya puesto (no consulta otra vez)
        self.metas = {}
        for meta in MetaDesempeno.objects.filter(periodo=periodo).select_related('item', 'periodo'):
            meta.__dict__['_ponderador'] = self.ponderaciones.get(meta.cargo_id, {}).get(meta.item_id, Decimal('0'))
            self.metas[(meta.cargo_id, meta.item_id, meta.delegacion_id)] = meta
        # Avance: la misma regla de calcular_avance, agrupada por responsable (encargado o quien registró) e ítem
        validas = Actividad.objects.filter(periodo=periodo, estado='VALIDADA', es_gestion=False).exclude(
            evidencias__validacion__decision='APROBAR', evidencias__validacion__otorga_puntaje=False)
        limite = None
        if hasta is not None:
            # Fin del día de corte como fecha y hora local (no se usa __date: en MySQL depende de sus tablas de
            # zonas horarias, que WAMP no trae cargadas)
            from datetime import datetime, time, timedelta
            from django.utils import timezone
            limite = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min))
            # Cuenta en la semana en que se realizó (validada después o no); sin fecha de realización, la de ingreso
            validas = validas.filter(Q(fecha_realizacion__lte=hasta) |
                                     Q(fecha_realizacion__isnull=True, fecha__lt=limite))
        self.avances = {(f['responsable'], f['item_id']): f['n'] for f in validas.annotate(
            responsable=Coalesce('encargado_id', 'usuario_id')).values('responsable', 'item_id').annotate(
            n=Count('id', distinct=True))}
        # Ajustes (felicitaciones): suma por funcionario
        ajustes = AjusteDesempeno.objects.filter(periodo=periodo)
        if limite is not None:
            ajustes = ajustes.filter(fecha__lt=limite)
        self.ajustes = {f['usuario_id']: f['total'] for f in ajustes.values('usuario_id').annotate(total=Sum('valor'))}
        # Solo quienes tienen alguna ausencia en el periodo necesitan contar sus días. Con hasta, solo las ausencias
        # ya registradas al cierre de ese día (fecha_registro): la meta ajustada queda como el semáforo la mostró
        ausencias = Ausencia.objects.filter(desde__lte=periodo.fecha_termino, hasta__gte=periodo.fecha_inicio)
        if limite is not None:
            ausencias = ausencias.filter(fecha_registro__lt=limite)
        self.con_ausencia = set(ausencias.values_list('usuario_id', flat=True))
        self.limite = limite
        self.dias = {}

    def metas_aplicables(self, cargo_id, delegacion_id):
        """{ítem: meta}: por cada ítem ponderado, la meta de la delegación si existe; si no, la general."""
        aplicables = {}
        for item_id in self.ponderaciones.get(cargo_id, {}):
            meta = self.metas.get((cargo_id, item_id, delegacion_id)) if delegacion_id else None
            meta = meta or self.metas.get((cargo_id, item_id, None))
            if meta is not None:
                aplicables[item_id] = meta
        return aplicables

    def estado(self, cargo_id, delegacion_id=None):
        """'' si el cargo se mide; si no, el motivo (mismos mensajes que estado_medicion)."""
        ponderados = self.ponderaciones.get(cargo_id, {})
        total = sum(ponderados.values(), Decimal('0'))
        if total != 100:
            return f"La ponderación de este cargo suma {total}% y debe sumar 100%: todavía no se mide."
        aplicables = self.metas_aplicables(cargo_id, delegacion_id)
        faltan = [item_id for item_id in ponderados if item_id not in aplicables]
        if faltan:
            from UsuarioApp.models import Catalogo
            nombres = ', '.join(Catalogo.objects.filter(pk__in=faltan).order_by('id').values_list('nombre', flat=True))
            return f"Falta la meta de: {nombres}. Este cargo todavía no se mide."
        return ''

    def metas_de(self, cargo_id, delegacion_id):
        if self.estado(cargo_id, delegacion_id):
            return []
        aplicables = self.metas_aplicables(cargo_id, delegacion_id)
        return [aplicables[item_id] for item_id in sorted(aplicables)]

    def indicador(self, usuario, meta, fecha):
        """Indicador sin guardar, con los datos ya cargados: calcular() no vuelve a consultar."""
        indicador = IndicadorDesempeno(usuario=usuario, meta=meta, fecha_calculo=fecha)
        indicador._avance = self.avances.get((usuario.pk, meta.item_id), 0)
        indicador._ajustes = self.ajustes.get(usuario.pk, Decimal('0'))
        if usuario.pk not in self.dias:  # los días de ausencia se cuentan una vez por funcionario
            self.dias[usuario.pk] = (dias_ausencia(usuario, self.periodo, self.limite)
                                     if usuario.pk in self.con_ausencia else 0)
        indicador._dias_ausencia = self.dias[usuario.pk]
        return indicador



# ---------------------------------------------------------------------------
# Tendencia semanal (Mi Gestión): avance contra lo esperado al cierre de cada semana del periodo
# ---------------------------------------------------------------------------
def cortes_semanales(periodo, hoy):
    """Fechas de corte: cada domingo del periodo hasta hoy, más hoy (o el término, si el periodo ya terminó)."""
    from datetime import timedelta
    ultimo = min(hoy, periodo.fecha_termino)
    if ultimo < periodo.fecha_inicio:
        return []
    cortes = []
    dia = periodo.fecha_inicio + timedelta(days=(6 - periodo.fecha_inicio.weekday()))  # primer domingo
    while dia < ultimo:
        cortes.append(dia)
        dia += timedelta(days=7)
    cortes.append(ultimo)
    return cortes


def tendencia_semanal(periodo, hoy, usuarios):
    """Una fila por corte semanal: avance (cumplimiento ponderado del funcionario, o el promedio de los usuarios
    medidos si son varios, igual que el puntaje colectivo) y esperado (porcentaje del periodo transcurrido).
    Cada corte usa las mismas reglas del semáforo: una actividad cuenta en la semana en que se realizó (aunque se haya
    validado después), y las ausencias y felicitaciones, desde el día en que se registraron. El último punto (hoy)
    es igual al avance que muestran Mi Gestión y el Semáforo."""
    if periodo is None:
        return []
    usuarios = list(usuarios)
    puntos = []
    for corte in cortes_semanales(periodo, hoy):
        datos = DatosMedicion(periodo, hasta=corte)
        filas = [seguimiento_usuario(u, periodo, corte, datos) for u in usuarios if u.cargo_id]
        filas = [f for f in filas if not f['sin_medir']]
        if not filas:
            continue
        avance = round(sum((f['avance_logrado'] for f in filas), Decimal('0')) / len(filas), 1)
        puntos.append({'fecha': corte.isoformat(), 'etiqueta': corte.strftime('%d/%m'), 'avance': float(avance),
                       'esperado': float(periodo.porcentaje_transcurrido(corte))})
    return puntos
