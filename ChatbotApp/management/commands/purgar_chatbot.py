"""Purga programada de los datos del chatbot (T-C-04: retención y topes).

Uso:
    python manage.py purgar_chatbot [--mensajes-dias N] [--eventos-dias N]
                                    [--anonimizar-eventos] [--limites]
                                    [--dry-run] [--lote 1000]

- ``MensajeChat`` anteriores al corte se borran por lotes de pk.
- ``EventoChatbot`` anteriores al corte se borran o se anonimizan con
  ``--anonimizar-eventos`` (se conserva la fila y su fecha para métricas).
- ``--limites`` borra las ventanas de ``LimiteConsulta`` anteriores a la actual.
- ``--dry-run`` informa cuántas filas se verían afectadas sin modificar nada.

El comando no programa su propia ejecución: cron/systemd timer es una decisión de Operaciones y
requiere autorización escrita. Es idempotente: una segunda ejecución no encuentra filas pendientes.
"""
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ChatbotApp.models import EventoChatbot, LimiteConsulta, MensajeChat


def _borrar_por_lotes(queryset, lote):
    """Borra el queryset por lotes de pk, de modo que ninguna sentencia bloquee la tabla entera."""
    total = 0
    while True:
        pks = list(queryset.order_by('pk').values_list('pk', flat=True)[:lote])
        if not pks:
            return total
        with transaction.atomic():
            queryset.filter(pk__in=pks).delete()
        total += len(pks)


def _anonimizar_por_lotes(queryset, lote):
    """Vacía los datos personales de los eventos por lotes; conserva la fila y su fecha."""
    total = 0
    while True:
        pks = list(queryset.order_by('pk').values_list('pk', flat=True)[:lote])
        if not pks:
            return total
        with transaction.atomic():
            EventoChatbot.objects.filter(pk__in=pks).update(
                usuario=None,
                pregunta='',
                respuesta='',
                contexto='',
                mensajes_enviados=[],
                error='',
            )
        total += len(pks)


def _eventos_anonimizables(corte):
    """Eventos vencidos que aún conservan usuario o algún texto.

    Se excluyen los ya anonimizados para que una segunda ejecución sea idempotente (0 filas).
    """
    return EventoChatbot.objects.filter(fecha__lt=corte).exclude(
        usuario__isnull=True,
        pregunta='',
        respuesta='',
        contexto='',
        mensajes_enviados=[],
        error='',
    )


def _ventanas_anteriores():
    """Índices de ``LimiteConsulta.ventana`` anteriores a la ventana actual del rate limit."""
    segundos = max(1, settings.CHATBOT_RATE_VENTANA)
    actual = int(time.time() // segundos)
    ventanas = set(
        LimiteConsulta.objects.values_list('ventana', flat=True).distinct())
    anteriores = []
    for ventana in ventanas:
        try:
            indice = int(ventana)
        except (TypeError, ValueError):
            continue  # valor inesperado: no se borra por no poder compararlo
        if indice < actual:
            anteriores.append(ventana)
    return anteriores, actual


class Command(BaseCommand):
    help = ('Purga mensajes y eventos del chatbot según la retención configurada, '
            'anonimiza eventos antiguos y elimina ventanas viejas del rate limit.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--mensajes-dias', type=int, default=None,
            help='Días de retención de MensajeChat (por defecto CHATBOT_RETENCION_MENSAJES_DIAS).',
        )
        parser.add_argument(
            '--eventos-dias', type=int, default=None,
            help='Días de retención de EventoChatbot (por defecto CHATBOT_RETENCION_EVENTOS_DIAS).',
        )
        parser.add_argument(
            '--anonimizar-eventos', action='store_true',
            help='Anonimiza los eventos vencidos en lugar de borrarlos.',
        )
        parser.add_argument(
            '--limites', action='store_true',
            help='Borra las ventanas de LimiteConsulta anteriores a la actual.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Informa cuántas filas se verían afectadas sin borrar ni modificar nada.',
        )
        parser.add_argument(
            '--lote', type=int, default=1000,
            help='Filas por lote de borrado/anonimización (por defecto 1000).',
        )

    def handle(self, *args, **opciones):
        mensajes_dias = opciones['mensajes_dias']
        if mensajes_dias is None:
            mensajes_dias = settings.CHATBOT_RETENCION_MENSAJES_DIAS
        eventos_dias = opciones['eventos_dias']
        if eventos_dias is None:
            eventos_dias = settings.CHATBOT_RETENCION_EVENTOS_DIAS
        lote = opciones['lote']
        if lote < 1:
            raise CommandError('--lote debe ser un entero mayor o igual a 1.')
        if mensajes_dias < 0 or eventos_dias < 0:
            raise CommandError('Los días de retención no pueden ser negativos.')

        dry_run = opciones['dry_run']
        anonimizar = opciones['anonimizar_eventos']
        con_limites = opciones['limites']

        ahora = timezone.now()
        corte_mensajes = ahora - timedelta(days=mensajes_dias)
        corte_eventos = ahora - timedelta(days=eventos_dias)

        mensajes = MensajeChat.objects.filter(fecha__lt=corte_mensajes)
        if anonimizar:
            eventos = _eventos_anonimizables(corte_eventos)
        else:
            eventos = EventoChatbot.objects.filter(fecha__lt=corte_eventos)

        modo = 'dry-run (sin cambios)' if dry_run else 'ejecución'
        self.stdout.write(
            f"purgar_chatbot: {modo}; mensajes_dias={mensajes_dias}, "
            f"eventos_dias={eventos_dias}, lote={lote}"
        )

        if dry_run:
            total_mensajes = mensajes.count()
            total_eventos = eventos.count()
        else:
            total_mensajes = _borrar_por_lotes(mensajes, lote)
            if anonimizar:
                total_eventos = _anonimizar_por_lotes(eventos, lote)
            else:
                total_eventos = _borrar_por_lotes(eventos, lote)

        if dry_run:
            self.stdout.write(f"MensajeChat: {total_mensajes} fila(s) a borrar (dry-run)")
        else:
            self.stdout.write(f"MensajeChat: {total_mensajes} fila(s) borradas")

        if dry_run:
            accion = 'a anonimizar' if anonimizar else 'a borrar'
            self.stdout.write(f"EventoChatbot: {total_eventos} fila(s) {accion} (dry-run)")
        elif anonimizar:
            self.stdout.write(f"EventoChatbot: {total_eventos} fila(s) anonimizadas")
        else:
            self.stdout.write(f"EventoChatbot: {total_eventos} fila(s) borradas")

        if con_limites:
            ventanas, actual = _ventanas_anteriores()
            limites = LimiteConsulta.objects.filter(ventana__in=ventanas)
            if dry_run:
                total_limites = limites.count()
                self.stdout.write(
                    f"LimiteConsulta: {total_limites} fila(s) a borrar (dry-run; "
                    f"ventana actual={actual})"
                )
            else:
                total_limites = _borrar_por_lotes(limites, lote)
                self.stdout.write(
                    f"LimiteConsulta: {total_limites} fila(s) borradas (ventana actual={actual})"
                )
        else:
            self.stdout.write("LimiteConsulta: sin cambios (use --limites para purgar ventanas)")
