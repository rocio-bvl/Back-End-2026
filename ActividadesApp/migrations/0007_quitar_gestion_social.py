"""Se quitan las gestiones 1, 2 y 3 de la atención social: las acciones que atienden una solicitud son
las actividades vinculadas a ella (Actividad.solicitud), que pueden ser una o varias."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ActividadesApp", "0006_solicitud_social_sin_contacto"),
    ]

    operations = [
        migrations.DeleteModel(
            name="GestionSocial",
        ),
    ]
