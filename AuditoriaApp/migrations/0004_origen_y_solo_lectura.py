from django.db import migrations, models


def copiar_usuario(apps, schema_editor):
    """Los registros anteriores guardan el nombre y RUT de su usuario. Su origen no se registró: canal vacío
    (la tabla lo muestra como "No registrado") e IP nula."""
    Auditoria = apps.get_model('AuditoriaApp', 'Auditoria')
    for registro in Auditoria.objects.select_related('usuario').exclude(usuario=None):
        usuario = registro.usuario
        nombre = f"{usuario.first_name} {usuario.last_name}".strip() or usuario.username
        Auditoria.objects.filter(pk=registro.pk).update(usuario_texto=f"{nombre} ({usuario.username})")


class Migration(migrations.Migration):

    dependencies = [
        ("AuditoriaApp", "0003_eventos_inicio_sesion"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditoria",
            name="usuario_texto",
            field=models.CharField(blank=True, default="", max_length=200, verbose_name="Usuario (al registrar)"),
        ),
        migrations.AddField(
            model_name="auditoria",
            name="ip",
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name="IP de origen"),
        ),
        # Los registros que ya existían quedan con canal vacío; los nuevos parten en EXTERNO
        migrations.AddField(
            model_name="auditoria",
            name="canal",
            field=models.CharField(blank=True, default="", max_length=10, verbose_name="Canal",
                                   choices=[("SGR", "Sistema SGR"), ("ADMIN", "Django Admin"), ("EXTERNO", "Externo")]),
        ),
        migrations.AlterField(
            model_name="auditoria",
            name="canal",
            field=models.CharField(blank=True, default="EXTERNO", max_length=10, verbose_name="Canal",
                                   choices=[("SGR", "Sistema SGR"), ("ADMIN", "Django Admin"), ("EXTERNO", "Externo")]),
        ),
        migrations.RunPython(copiar_usuario, migrations.RunPython.noop),
    ]
