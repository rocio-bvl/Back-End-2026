"""La solicitud social pasa a existir por sí misma (la registra un funcionario) y las actividades se vinculan a
ella. Antes cada atención colgaba de una actividad: se copia esa relación al revés antes de borrar el campo.
Además se quitan contacto y teléfono de la actividad (el solicitante queda en la solicitud social)."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def atencion_independiente(apps, schema_editor):
    """Cada atención toma la fecha y el funcionario de su actividad, y la actividad queda vinculada a ella."""
    AtencionSocial = apps.get_model('ActividadesApp', 'AtencionSocial')
    for atencion in AtencionSocial.objects.select_related('actividad'):
        actividad = atencion.actividad
        atencion.fecha = actividad.fecha
        atencion.usuario_id = actividad.usuario_id
        atencion.save(update_fields=['fecha', 'usuario'])
        actividad.solicitud_id = atencion.pk
        actividad.save(update_fields=['solicitud'])



class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ActividadesApp", "0005_territorio_encargado_comentarios"),
    ]

    operations = [
        migrations.AddField(
            model_name="actividad",
            name="solicitud",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="actividades", to="ActividadesApp.atencionsocial",
                verbose_name="Solicitud social vinculada"),
        ),
        migrations.AddField(
            model_name="atencionsocial",
            name="fecha",
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name="Fecha de ingreso"),
        ),
        migrations.AddField(
            model_name="atencionsocial",
            name="usuario",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, related_name="atenciones_registradas",
                to=settings.AUTH_USER_MODEL, verbose_name="Registrada por"),
        ),
        migrations.RunPython(atencion_independiente, migrations.RunPython.noop),
        migrations.RemoveField(model_name="atencionsocial", name="actividad"),
        migrations.RemoveField(model_name="actividad", name="contacto"),
        migrations.RemoveField(model_name="actividad", name="telefono"),
        migrations.AlterModelOptions(
            name="atencionsocial",
            options={"ordering": ["-fecha"], "verbose_name": "Atención social",
                     "verbose_name_plural": "Atenciones sociales"},
        ),
        migrations.AlterField(
            model_name="actividad",
            name="fecha",
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name="Fecha de ingreso"),
        ),
        migrations.AlterField(
            model_name="actividad",
            name="fecha_realizacion",
            field=models.DateField(blank=True, null=True, verbose_name="Fecha de ejecución"),
        ),
    ]
