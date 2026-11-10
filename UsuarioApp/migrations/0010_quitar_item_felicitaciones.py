# Se quitan las felicitaciones de usuarios: el ítem que creó la migración 0007 se borra. Si alguna actividad ya
# lo usa, no se puede borrar (la actividad lo protege): queda inactivo y deja de aparecer en el formulario.
from django.db import migrations

NOMBRE = 'Felicitaciones de usuarios'


def quitar_item(apps, schema_editor):
    Catalogo = apps.get_model('UsuarioApp', 'Catalogo')
    items = Catalogo.objects.filter(tipo='ITEM_GESTION', nombre=NOMBRE)
    items.filter(actividades_item__isnull=True).delete()
    items.update(estado='INACTIVO')


def volver_item(apps, schema_editor):
    Catalogo = apps.get_model('UsuarioApp', 'Catalogo')
    if Catalogo.objects.filter(tipo='ITEM_GESTION', nombre=NOMBRE).update(estado='ACTIVO') == 0:
        ultimo = Catalogo.objects.order_by('-id').values_list('id', flat=True).first() or 0
        Catalogo.objects.create(id=max(ultimo, 11) + 1, tipo='ITEM_GESTION', nombre=NOMBRE, estado='ACTIVO')


class Migration(migrations.Migration):

    dependencies = [
        ('UsuarioApp', '0009_organizacion_a_actividadesapp'),
    ]

    operations = [
        migrations.RunPython(quitar_item, volver_item),
    ]
