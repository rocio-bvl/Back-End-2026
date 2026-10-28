"""Las delegaciones dejan de ser una lista fija (choices): el Administrador las agrega y edita. Se guarda el
nombre que se lee (nombre_visible) aparte del código. Además, cada Funcionario puede tener un territorio."""

from django.db import migrations, models
import django.db.models.deletion

NOMBRES = {
    'RURAL': 'Rural',
    'LAS_COMPANIAS': 'Las Compañías',
    'LA_PAMPA': 'La Pampa',
    'LA_ANTENA': 'La Antena',
    'CENTRO': 'Centro',
}


def poner_nombres(apps, schema_editor):
    Delegacion = apps.get_model('UsuarioApp', 'Delegacion')
    for delegacion in Delegacion.objects.all():
        delegacion.nombre_visible = NOMBRES.get(delegacion.nombre, delegacion.nombre.replace('_', ' ').title())
        delegacion.save(update_fields=['nombre_visible'])


class Migration(migrations.Migration):

    dependencies = [
        ("ActividadesApp", "0006_solicitud_social_sin_contacto"),
        ("UsuarioApp", "0004_perfil_y_sin_rol_consulta"),
    ]

    operations = [
        migrations.AddField(
            model_name="delegacion",
            name="nombre_visible",
            field=models.CharField(default="", max_length=100, verbose_name="Nombre"),
        ),
        migrations.RunPython(poner_nombres, migrations.RunPython.noop),
        migrations.AddField(
            model_name="usuario",
            name="territorio",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="funcionarios",
                to="ActividadesApp.territorio",
                verbose_name="Territorio",
            ),
        ),
        migrations.AlterField(
            model_name="delegacion",
            name="nombre",
            field=models.CharField(max_length=100, unique=True, verbose_name="Código"),
        ),
    ]
