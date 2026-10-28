"""El Coordinador solo visualiza: deja de ser staff y ya no entra a Django Admin.
Solo cambia datos: quita is_staff a quienes tienen rol Coordinador y no son superusuarios."""
from django.db import migrations


def quitar_staff_coordinador(apps, schema_editor):
    Usuario = apps.get_model('UsuarioApp', 'Usuario')
    Usuario.objects.filter(roles_asignados__rol__codigo='Coordinador', is_superuser=False,
                           is_staff=True).update(is_staff=False)


def devolver_staff_coordinador(apps, schema_editor):
    Usuario = apps.get_model('UsuarioApp', 'Usuario')
    Usuario.objects.filter(roles_asignados__rol__codigo='Coordinador', is_superuser=False).update(is_staff=True)


class Migration(migrations.Migration):

    dependencies = [
        ('UsuarioApp', '0005_delegacion_editable_territorio_usuario'),
    ]

    operations = [
        migrations.RunPython(quitar_staff_coordinador, devolver_staff_coordinador),
    ]
