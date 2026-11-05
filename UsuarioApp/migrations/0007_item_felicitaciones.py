from django.db import migrations

NOMBRE = 'Felicitaciones de usuarios'


def crear_item(apps, schema_editor):
    """Ítem de gestión de las felicitaciones de usuarios: solo el Delegado las informa a nombre del funcionario.
    Se crea con id 12 (o el siguiente libre) para no chocar con los ids 1 a 11 de datos_iniciales.sql."""
    Catalogo = apps.get_model('UsuarioApp', 'Catalogo')
    if Catalogo.objects.filter(tipo='ITEM_GESTION', nombre=NOMBRE).exists():
        return
    ultimo = Catalogo.objects.order_by('-id').values_list('id', flat=True).first() or 0
    Catalogo.objects.create(id=max(ultimo, 11) + 1, tipo='ITEM_GESTION', nombre=NOMBRE, estado='ACTIVO')


def quitar_item(apps, schema_editor):
    Catalogo = apps.get_model('UsuarioApp', 'Catalogo')
    Catalogo.objects.filter(tipo='ITEM_GESTION', nombre=NOMBRE, actividades_item__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('UsuarioApp', '0006_coordinador_sin_staff'),
    ]

    operations = [
        migrations.RunPython(crear_item, quitar_item),
    ]
