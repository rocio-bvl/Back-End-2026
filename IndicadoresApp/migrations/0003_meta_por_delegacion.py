"""Metas por delegacion: vacio = meta general de la municipalidad (solo el Administrador)."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("UsuarioApp", "0005_delegacion_editable_territorio_usuario"),
        ("IndicadoresApp", "0002_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="metadesempeno",
            options={
                "ordering": ["delegacion__nombre", "cargo__nombre", "item__id"],
                "verbose_name": "Meta de desempeño",
                "verbose_name_plural": "Metas de desempeño",
            },
        ),
        migrations.AddField(
            model_name="metadesempeno",
            name="delegacion",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="metas",
                to="UsuarioApp.delegacion",
                verbose_name="Delegación (vacío = general)",
            ),
        ),
    ]
