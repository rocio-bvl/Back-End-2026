"""python manage.py crear_grupos: crea los 4 grupos con sus permisos y deja a cada usuario en el suyo.
Se puede correr las veces que se quiera."""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from UsuarioApp.choices import PERMISOS_POR_GRUPO
from UsuarioApp.models import Usuario


class Command(BaseCommand):
    help = "Crea los grupos Administrador, Supervisor, Delegado y Administrativo con sus permisos."

    def handle(self, *args, **options):
        for nombre_grupo, permisos in PERMISOS_POR_GRUPO.items():
            grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
            encontrados = []
            for texto in permisos:
                app, codigo = texto.split('.')
                permiso = Permission.objects.filter(content_type__app_label=app, codename=codigo).first()
                if permiso is None:
                    self.stdout.write(self.style.WARNING(f"  Falta el permiso {texto}: se omite por ahora."))
                    continue
                encontrados.append(permiso)
            grupo.permissions.set(encontrados)
            self.stdout.write(f"{nombre_grupo}: {len(encontrados)} permisos")
        for usuario in Usuario.objects.all():
            usuario.sincronizar_grupo()
        self.stdout.write(self.style.SUCCESS("Grupos listos"))