"""RAG del chatbot: documentos internos y datos agregados del SGR.

Sin dependencias nuevas (solo stdlib + Django). No usa embeddings: puntúa por coincidencia de
palabras clave, título y contenido. El contexto de datos se arma con consultas predefinidas y
filtradas por el alcance del rol; nunca con SQL generado por la IA y nunca con datos personales.
"""
import re
import unicodedata

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from ActividadesApp.choices import estados_actividad
from ActividadesApp.models import Actividad, AtencionSocial
from ChatbotApp.models import DocumentoConocimiento
from IndicadoresApp.models import Ausencia, IndicadorDesempeno, MetaDesempeno, periodo_vigente
from UsuarioApp.models import Delegacion, Usuario, UsuarioRol

# Stopwords españolas simples: se descartan al puntuar para no dar peso a palabras vacías.
STOPWORDS = {
    'a', 'al', 'algo', 'algunas', 'algunos', 'ante', 'antes', 'como', 'con', 'contra', 'cual',
    'cuales', 'cuando', 'de', 'del', 'desde', 'donde', 'dos', 'el', 'ella', 'ellas', 'ellos',
    'en', 'entre', 'era', 'es', 'esa', 'esas', 'ese', 'eso', 'esos', 'esta', 'estas', 'este',
    'esto', 'estos', 'fue', 'ha', 'hasta', 'hay', 'la', 'las', 'le', 'les', 'lo', 'los', 'mas',
    'me', 'mi', 'mis', 'mucho', 'muy', 'no', 'nos', 'o', 'otra', 'otras', 'otro', 'otros',
    'para', 'pero', 'poco', 'por', 'porque', 'que', 'quien', 'quienes', 'se', 'ser', 'si',
    'sin', 'sobre', 'su', 'sus', 'te', 'tiene', 'tu', 'tus', 'un', 'una', 'unas', 'uno', 'unos',
    'y', 'ya', 'yo', 'puedo', 'debo', 'hacer', 'donde', 'cuanto', 'cuanta',
}

ESTADOS_ACTIVIDAD = dict(estados_actividad)


def normalizar(texto):
    """Minúsculas, sin tildes y con espacios colapsados (para comparar en español)."""
    texto = unicodedata.normalize('NFKD', str(texto or ''))
    texto = ''.join(caracter for caracter in texto if not unicodedata.combining(caracter))
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9ñ\s]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


def _tokens(texto):
    return {palabra for palabra in normalizar(texto).split()
            if len(palabra) > 2 and palabra not in STOPWORDS}


def _roles_documento(documento):
    return [normalizar(rol) for rol in (documento.roles_permitidos or '').split(',') if rol.strip()]


def recuperar_documentos(pregunta, usuario, top=3):
    """Devuelve los documentos activos más relevantes para la pregunta y el rol del usuario.

    Puntaje: palabra clave (3) + título (2) + contenido (1). El superusuario ve todos los
    documentos; `roles_permitidos` vacío significa disponible para todos los roles del chatbot.
    """
    tokens = _tokens(pregunta)
    if not tokens:
        return []

    es_superusuario = bool(getattr(usuario, 'is_superuser', False))
    rol = normalizar(usuario.rol()) if usuario is not None and hasattr(usuario, 'rol') else ''

    candidatos = []
    for documento in DocumentoConocimiento.objects.filter(activo=True):
        permitidos = _roles_documento(documento)
        if not es_superusuario and permitidos and rol not in permitidos:
            continue

        palabras = normalizar(documento.palabras_clave)
        titulo = normalizar(documento.titulo)
        contenido = normalizar(documento.contenido)

        puntaje = 0
        for token in tokens:
            if token in palabras:
                puntaje += 3
            if token in titulo:
                puntaje += 2
            if token in contenido:
                puntaje += 1
        if puntaje > 0:
            candidatos.append((puntaje, documento))

    # A igual puntaje, gana el documento actualizado más recientemente.
    candidatos.sort(key=lambda par: (-par[0], -par[1].actualizado.timestamp()))
    return [documento for _, documento in candidatos[:top]]


def _alcance(usuario):
    """(texto del alcance, delegación o None, sin_alcance) según la convención del proyecto.

    Un Delegado sin delegación asignada no recibe datos: se falla cerrado para no exponer
    información de toda la municipalidad por un dato incompleto del usuario.
    """
    if getattr(usuario, 'is_superuser', False):
        return "toda la municipalidad", None, False
    if usuario is not None and hasattr(usuario, 'rol') and usuario.rol() == 'Delegado':
        if usuario.delegacion_id:
            nombre = usuario.delegacion.nombre_visible or usuario.delegacion.nombre
            return f"delegación {nombre}", usuario.delegacion, False
        return "sin delegación asignada (no hay datos disponibles)", None, True
    return "toda la municipalidad", None, False


def _formatear_actividades(actividades):
    por_estado = ", ".join(
        f"{ESTADOS_ACTIVIDAD.get(fila['estado'], fila['estado'])}={fila['total']}"
        for fila in actividades.values('estado').annotate(total=Count('id')).order_by('estado')
    )
    partes = [f"Actividades por estado: {por_estado or 'sin actividades registradas'}."]
    pendientes = actividades.filter(estado='EVIDENCIA_INGRESADA').count()
    partes.append(f"Pendientes de validación (evidencia ingresada): {pendientes}.")
    partes.append("Últimas 10 actividades (sin datos personales):")
    recientes = actividades.select_related('item', 'territorio', 'usuario__delegacion').order_by('-fecha')[:10]
    for actividad in recientes:
        territorio = actividad.territorio.nombre if actividad.territorio else "sin territorio"
        delegacion = actividad.usuario.delegacion.nombre_visible if actividad.usuario and actividad.usuario.delegacion else "sin delegación"
        item = actividad.item.nombre if actividad.item else "sin ítem"
        realizacion = actividad.fecha_realizacion.strftime('%d/%m/%Y') if actividad.fecha_realizacion else "sin fecha"
        partes.append(
            f"- ACT{actividad.pk}: {item} | territorio: {territorio} | delegación: {delegacion} | "
            f"estado: {actividad.get_estado_display()} | realización: {realizacion}"
        )
    return "\n".join(partes)


def _formatear_metas(delegacion):
    periodo = periodo_vigente()
    if periodo is None:
        return "No hay un periodo vigente configurado."
    metas = MetaDesempeno.objects.filter(periodo=periodo)
    if delegacion is not None:
        metas = metas.filter(Q(delegacion__isnull=True) | Q(delegacion=delegacion))
    metas = metas.select_related('cargo', 'item', 'delegacion')
    avances = dict(IndicadorDesempeno.objects.filter(meta__in=metas).values_list('meta_id', 'avance_actual'))
    partes = [f"Metas del periodo vigente ({periodo.nombre_completo()}):"]
    for meta in metas:
        alcance = meta.delegacion.nombre_visible if meta.delegacion else "general"
        avance = avances.get(meta.pk)
        detalle_avance = f"avance registrado: {avance}" if avance is not None else "avance: ver Semáforo"
        partes.append(
            f"- {meta.cargo.nombre} / {meta.item.nombre}: objetivo {meta.valor_objetivo} {meta.unidad}, "
            f"ponderador {meta.ponderador}%, alcance {alcance}, {detalle_avance}"
        )
    if len(partes) == 1:
        partes.append("- Sin metas configuradas para el periodo.")
    partes.append("El cumplimiento exacto y el color del Semáforo se consultan en la pantalla del Semáforo "
                  "(el asistente no recalcula indicadores).")
    return "\n".join(partes)


def _formatear_atenciones(delegacion):
    atenciones = AtencionSocial.objects.all()
    if delegacion is not None:
        atenciones = atenciones.filter(usuario__delegacion=delegacion)
    atenciones = atenciones.prefetch_related('actividades')
    conteo = {'PENDIENTE': 0, 'EN_PROCESO': 0, 'ATENDIDA': 0}
    for atencion in atenciones:
        conteo[atencion.estado()] = conteo.get(atencion.estado(), 0) + 1
    partes = [
        "Atenciones sociales: "
        f"Pendientes={conteo['PENDIENTE']}, En proceso={conteo['EN_PROCESO']}, Atendidas={conteo['ATENDIDA']}.",
    ]
    if delegacion is None:
        from ActividadesApp.models import Solicitante
        partes.append(f"Solicitantes registrados en el sistema: {Solicitante.objects.count()}.")
    return "\n".join(partes)


def _formatear_usuarios(delegacion):
    usuarios = Usuario.objects.all()
    if delegacion is not None:
        usuarios = usuarios.filter(delegacion=delegacion)
    partes = [
        f"Usuarios: {usuarios.count()} en total, {usuarios.filter(is_active=True).count()} activos.",
    ]
    roles = (UsuarioRol.objects.filter(usuario__in=usuarios)
             .values('rol__codigo').annotate(total=Count('id')).order_by('rol__codigo'))
    if roles:
        partes.append("Por rol: " + ", ".join(f"{fila['rol__codigo']}={fila['total']}" for fila in roles) + ".")
    if delegacion is None:
        activas = Delegacion.objects.filter(estado='ACTIVO').count()
        partes.append(f"Delegaciones activas: {activas}.")
    return "\n".join(partes)


def _formatear_ausencias(delegacion):
    hoy = timezone.localdate()
    ausencias = Ausencia.objects.filter(desde__lte=hoy, hasta__gte=hoy)
    if delegacion is not None:
        ausencias = ausencias.filter(usuario__delegacion=delegacion)
    return f"Ausencias activas hoy (vacaciones, administrativos o licencias): {ausencias.count()}."


def contexto_datos(usuario):
    """Contexto compacto con datos reales del SGR, filtrado por el alcance del rol.

    Devuelve `(texto, errores)`. Cada bloque falla de forma silenciosa: si una consulta lanza una
    excepción se omite y se registra el tipo de error (sin datos sensibles) para el evento.
    """
    alcance, delegacion, sin_alcance = _alcance(usuario)
    if sin_alcance:
        return f"Alcance de los datos: {alcance}.", []

    actividades = Actividad.objects.all()
    if delegacion is not None:
        actividades = actividades.filter(usuario__delegacion=delegacion)

    bloques = [
        ("actividades", lambda: _formatear_actividades(actividades)),
        ("metas", lambda: _formatear_metas(delegacion)),
        ("atenciones", lambda: _formatear_atenciones(delegacion)),
        ("usuarios", lambda: _formatear_usuarios(delegacion)),
        ("ausencias", lambda: _formatear_ausencias(delegacion)),
    ]

    errores = []
    partes = [f"Alcance de los datos: {alcance}."]
    for nombre, constructor in bloques:
        try:
            partes.append(constructor())
        except Exception as exc:  # el chat nunca muere por el RAG de datos
            errores.append(f"{nombre}: {type(exc).__name__}")
    return "\n".join(partes), errores


def construir_contexto(pregunta, usuario):
    """Combina documentos relevantes + datos del SGR en un contexto acotado.

    Devuelve `(contexto, titulos_documentos, errores)`; el contexto se recorta al presupuesto
    `CHATBOT_RAG_MAX_CARACTERES`.
    """
    alcance, _, _ = _alcance(usuario)
    documentos = recuperar_documentos(pregunta, usuario)
    datos, errores = contexto_datos(usuario)

    partes = [
        f"ALCANCE DECLARADO: {alcance}. No entregues información fuera de este alcance.",
        "DOCUMENTACIÓN INTERNA RELEVANTE:",
    ]
    if documentos:
        for documento in documentos:
            partes.append(f"- {documento.titulo}: {documento.contenido}")
    else:
        partes.append("- Sin documentos internos coincidentes.")

    partes.append("DATOS DEL SGR (agregados, sin datos personales):")
    partes.append(datos)

    contexto = "\n".join(partes)
    presupuesto = settings.CHATBOT_RAG_MAX_CARACTERES
    if len(contexto) > presupuesto:
        contexto = contexto[:presupuesto].rstrip() + " […]"
    return contexto, [documento.titulo for documento in documentos], errores
