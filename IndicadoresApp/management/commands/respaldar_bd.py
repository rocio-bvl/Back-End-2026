"""python manage.py respaldar_bd: respaldo de la base de datos y de las fotografías subidas.

Deja en RESPALDO_DIR un archivo sgr_AAAAMMDD_HHMM.sql.gz (mysqldump) y uno media_AAAAMMDD_HHMM.zip, y borra los
más antiguos para guardar solo los últimos RESPALDO_CANTIDAD. La clave de la base se entrega a mysqldump por la
variable MYSQL_PWD, no en la línea de comandos, para que no aparezca en la lista de procesos.
Se programa una vez al día. Para restaurar: gunzip -c archivo.sql.gz | mysql -u USUARIO -p BASE
"""
import gzip
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


def borrar_antiguos(carpeta, patron, cantidad):
    archivos = sorted(carpeta.glob(patron))
    for viejo in archivos[:-cantidad] if cantidad > 0 else []:
        viejo.unlink()


class Command(BaseCommand):
    help = "Respalda la base de datos (mysqldump comprimido) y la carpeta media."

    def handle(self, *args, **options):
        base = settings.DATABASES['default']
        carpeta = Path(settings.RESPALDO_DIR)
        carpeta.mkdir(parents=True, exist_ok=True)
        marca = timezone.localtime().strftime('%Y%m%d_%H%M')

        destino = carpeta / f"sgr_{marca}.sql.gz"
        comando = [settings.MYSQLDUMP, '--single-transaction', '--routines', '--default-character-set=utf8mb4',
                   '-h', base['HOST'] or 'localhost', '-P', str(base['PORT'] or 3306), '-u', base['USER'], base['NAME']]
        entorno = dict(os.environ, MYSQL_PWD=base['PASSWORD'] or '')
        try:
            proceso = subprocess.run(comando, capture_output=True, env=entorno, check=False)
        except FileNotFoundError:
            raise CommandError(f"No se encontró mysqldump ({settings.MYSQLDUMP}). Indique la ruta en MYSQLDUMP del .env.")
        if proceso.returncode != 0:
            raise CommandError("mysqldump falló: " + proceso.stderr.decode(errors='replace')[:500])
        with gzip.open(destino, 'wb') as salida:
            salida.write(proceso.stdout)

        media = Path(settings.MEDIA_ROOT)
        if media.is_dir():
            shutil.make_archive(str(carpeta / f"media_{marca}"), 'zip', media)

        borrar_antiguos(carpeta, 'sgr_*.sql.gz', settings.RESPALDO_CANTIDAD)
        borrar_antiguos(carpeta, 'media_*.zip', settings.RESPALDO_CANTIDAD)
        self.stdout.write(self.style.SUCCESS(f"Respaldo listo: {destino}"))
