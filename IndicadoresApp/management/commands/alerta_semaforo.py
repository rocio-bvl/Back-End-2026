"""python manage.py alerta_semaforo: envía a cada Delegado la lista de funcionarios de su delegación que están en
rojo en el Semáforo. Se programa una vez por semana (cron en AWS o Programador de tareas en Windows).
Usa filas_semaforo, la misma función de la pantalla, para que el correo y el Semáforo digan lo mismo."""
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from IndicadoresApp.models import periodo_vigente
from IndicadoresApp.views import filas_semaforo
from UsuarioApp.models import Delegacion


def cuerpo_alerta(delegacion, periodo, hoy, rojos):
    lineas = [f"Semáforo de {delegacion} al {hoy:%d-%m-%Y} ({periodo}).",
              f"Funcionarios en rojo: {len(rojos)}.", ""]
    for fila in rojos:
        lineas.append(f"- {fila['responsable']}: avance {fila['avance_logrado']}%, "
                      f"esperado {fila['objetivo_hoy']}%, mínimo {fila['minimo']}%")
    lineas += ["", "Revise el detalle en el Semáforo del SGR."]
    return "\n".join(lineas)


class Command(BaseCommand):
    help = "Envía por correo a los Delegados los funcionarios de su delegación que están en rojo."

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        periodo = periodo_vigente(hoy)
        if periodo is None:
            self.stdout.write("No hay periodo vigente: no se envía nada.")
            return
        enviados = 0
        for delegacion in Delegacion.objects.all():
            rojos = [fila for fila in filas_semaforo(delegacion, periodo, hoy) if fila['color'] == 'ROJO']
            correos = [d.email for d in delegacion.delegados().filter(is_active=True) if d.email]
            if not rojos or not correos:
                continue
            send_mail(f"SGR: {len(rojos)} funcionario(s) en rojo en {delegacion}",
                      cuerpo_alerta(delegacion, periodo, hoy, rojos), None, correos)
            enviados += 1
        self.stdout.write(self.style.SUCCESS(f"Alertas enviadas: {enviados} delegación(es)."))
