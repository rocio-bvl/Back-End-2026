import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def territorios_a_tabla(apps, schema_editor):
    """El territorio deja de ser texto libre: cada texto distinto pasa a ser una fila de la tabla territorio,
    asociada a la delegación del funcionario que registró la actividad."""
    Actividad = apps.get_model('ActividadesApp', 'Actividad')
    Territorio = apps.get_model('ActividadesApp', 'Territorio')
    for actividad in Actividad.objects.exclude(territorio_texto='').select_related('usuario'):
        nombre = actividad.territorio_texto.strip()[:150]
        if not nombre:
            continue
        territorio, _ = Territorio.objects.get_or_create(nombre=nombre, delegacion_id=actividad.usuario.delegacion_id)
        actividad.territorio = territorio
        actividad.save(update_fields=['territorio'])


def reclasificar_estados(apps, schema_editor):
    """Nuevo flujo: el Tubo es solo para lo que depende de factores externos.
    - Los compromisos antiguos (EN_TUBO con fecha límite) pasan a PROGRAMADA con esa fecha.
    - Los que no tenían fecha se quedan EN_TUBO (esperan factores externos).
    - Las actividades ya ejecutadas toman como fecha de realización el día en que se registraron."""
    Actividad = apps.get_model('ActividadesApp', 'Actividad')
    for actividad in Actividad.objects.all():
        if actividad.estado == 'EN_TUBO':
            if actividad.fecha_realizacion is not None:
                actividad.estado = 'PROGRAMADA'
                actividad.depende_externos = False
            else:
                actividad.depende_externos = True
        else:
            actividad.depende_externos = False
            if actividad.fecha_realizacion is None:
                actividad.fecha_realizacion = actividad.fecha.date()
        actividad.save(update_fields=['estado', 'depende_externos', 'fecha_realizacion'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("UsuarioApp", "0004_perfil_y_sin_rol_consulta"),
        ("ActividadesApp", "0004_actividad_absorbe_compromiso"),
    ]

    operations = [
        # 1. Tabla nueva de territorios
        migrations.CreateModel(
            name="Territorio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=150, verbose_name="Nombre")),
                ("estado", models.CharField(choices=[("ACTIVO", "Activo"), ("INACTIVO", "Inactivo")], default="ACTIVO", max_length=10, verbose_name="Estado")),
                ("delegacion", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="territorios", to="UsuarioApp.delegacion", verbose_name="Delegación")),
            ],
            options={
                "verbose_name": "Territorio",
                "verbose_name_plural": "Territorios",
                "db_table": "territorio",
                "ordering": ["delegacion__nombre", "nombre"],
            },
        ),
        migrations.AddConstraint(
            model_name="territorio",
            constraint=models.UniqueConstraint(fields=("nombre", "delegacion"), name="territorio_unico_por_delegacion"),
        ),
        # 2. actividad.territorio: de texto a llave foránea (se conservan los textos que ya había)
        migrations.RenameField(model_name="actividad", old_name="territorio", new_name="territorio_texto"),
        migrations.AddField(
            model_name="actividad",
            name="territorio",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="actividades", to="ActividadesApp.territorio", verbose_name="Territorio / sector"),
        ),
        migrations.RunPython(territorios_a_tabla, migrations.RunPython.noop),
        migrations.RemoveField(model_name="actividad", name="territorio_texto"),
        # 3. Fecha de realización, Tubo por factores externos y encargado
        migrations.RenameField(model_name="actividad", old_name="fecha_comprometida", new_name="fecha_realizacion"),
        migrations.RenameField(model_name="actividad", old_name="ingreso_agenda_colectiva", new_name="depende_externos"),
        migrations.AlterField(
            model_name="actividad",
            name="fecha_realizacion",
            field=models.DateField(blank=True, null=True, verbose_name="Fecha de realización"),
        ),
        migrations.AlterField(
            model_name="actividad",
            name="depende_externos",
            field=models.BooleanField(default=False, verbose_name="¿Depende de factores externos? (Tubo de Trabajo)"),
        ),
        migrations.AddField(
            model_name="actividad",
            name="encargado",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="actividades_a_cargo", to=settings.AUTH_USER_MODEL, verbose_name="Encargado"),
        ),
        migrations.AlterField(
            model_name="actividad",
            name="estado",
            field=models.CharField(choices=[("PROGRAMADA", "Programada (compromiso)"), ("EN_TUBO", "En Tubo de Trabajo (sin fecha)"), ("REGISTRADA", "Ejecutada (en revisión)"), ("RECHAZADA", "Rechazada (volver a registrar)"), ("VALIDADA", "Validada (completada)")], default="REGISTRADA", max_length=15, verbose_name="Estado"),
        ),
        migrations.AlterField(
            model_name="actividad",
            name="fecha",
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name="Fecha de registro"),
        ),
        migrations.AlterField(
            model_name="actividad",
            name="accion",
            field=models.CharField(max_length=255, verbose_name="Acción"),
        ),
        migrations.AlterField(
            model_name="actividad",
            name="usuario",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="actividades", to=settings.AUTH_USER_MODEL, verbose_name="Registrada por"),
        ),
        migrations.RunPython(reclasificar_estados, migrations.RunPython.noop),
        # 4. La fotografía pasa a ser opcional; el comentario de ejecución, obligatorio
        migrations.AlterField(
            model_name="evidencia",
            name="imagen",
            field=models.ImageField(blank=True, default="", upload_to="evidencias/", verbose_name="Fotografía (opcional, JPG/PNG, máx. 5 MB)"),
        ),
        migrations.AlterField(
            model_name="evidencia",
            name="comentario",
            field=models.TextField(verbose_name="Comentario de ejecución"),
        ),
        migrations.AlterField(
            model_name="validacion",
            name="decision",
            field=models.CharField(choices=[("APROBAR", "Aprobar"), ("RECHAZAR", "Rechazar (volver a registrar la ejecución)")], max_length=10, verbose_name="Decisión"),
        ),
        # 5. Bitácora de comentarios con fecha
        migrations.CreateModel(
            name="ComentarioActividad",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("texto", models.TextField(verbose_name="Comentario")),
                ("fecha", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Fecha de ingreso")),
                ("actividad", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comentarios", to="ActividadesApp.actividad", verbose_name="Actividad")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="comentarios_actividad", to=settings.AUTH_USER_MODEL, verbose_name="Escrito por")),
            ],
            options={
                "verbose_name": "Comentario de actividad",
                "verbose_name_plural": "Comentarios de actividad",
                "db_table": "comentario_actividad",
                "ordering": ["-fecha"],
            },
        ),
    ]
