# La tabla "organizacion" pasa a ActividadesApp (gestión social). Aquí solo se quita del estado de UsuarioApp:
# la tabla y sus datos no se tocan; ActividadesApp 0012 la toma tal como está.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('UsuarioApp', '0008_organizaciones'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name='Organizacion')],
            database_operations=[],
        ),
    ]
