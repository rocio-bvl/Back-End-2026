# Gestión social normalizada:
# 1. ActividadesApp toma la tabla "organizacion" (creada en UsuarioApp 0008) sin tocar sus datos y le agrega el tipo.
# 2. Nuevas tablas "solicitante" (persona atendida, una vez por RUT) y "representante" (cargo en una organización).
# 3. Las atenciones y las actividades dejan de repetir nombre, RUT y teléfono: apuntan al solicitante.
#    Antes de borrar esas columnas se crean los solicitantes con los datos que ya había.
import django.db.models.deletion
from django.db import migrations, models


def rut_limpio(rut):
    return (rut or '').replace('.', '').replace(' ', '').upper().strip()


def digitos(telefono):
    return ''.join(c for c in (telefono or '') if c.isdigit())[-8:]


def mover_tipo_de_contenido(apps, schema_editor):
    """Los permisos de Organizacion (si ya se crearon) pasan de UsuarioApp a ActividadesApp."""
    ContentType = apps.get_model('contenttypes', 'ContentType')
    if not ContentType.objects.filter(app_label='ActividadesApp', model='organizacion').exists():
        ContentType.objects.filter(app_label='UsuarioApp', model='organizacion').update(app_label='ActividadesApp')


def devolver_tipo_de_contenido(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(app_label='ActividadesApp', model='organizacion').update(app_label='UsuarioApp')


def crear_solicitantes(apps, schema_editor):
    """Un solicitante por cada RUT de las atenciones (con el nombre y teléfono más recientes). Las actividades
    toman el solicitante de su atención vinculada o, si no tienen, el que coincida por teléfono o nombre."""
    Solicitante = apps.get_model('ActividadesApp', 'Solicitante')
    AtencionSocial = apps.get_model('ActividadesApp', 'AtencionSocial')
    Actividad = apps.get_model('ActividadesApp', 'Actividad')
    for atencion in AtencionSocial.objects.order_by('fecha', 'pk'):
        rut = rut_limpio(atencion.rut_solicitante)
        solicitante, creado = Solicitante.objects.get_or_create(
            rut=rut, defaults={'nombre': atencion.nombre_solicitante, 'telefono': atencion.telefono_solicitante})
        if not creado:  # la atención más reciente trae los datos vigentes
            solicitante.nombre = atencion.nombre_solicitante or solicitante.nombre
            solicitante.telefono = atencion.telefono_solicitante or solicitante.telefono
            solicitante.save()
        atencion.solicitante = solicitante
        atencion.save(update_fields=['solicitante'])
    solicitantes = list(Solicitante.objects.all())
    for actividad in Actividad.objects.all():
        elegido = None
        if actividad.solicitud_id:
            elegido = AtencionSocial.objects.get(pk=actividad.solicitud_id).solicitante
        else:
            fono = digitos(actividad.telefono_usuario)
            nombre = (actividad.nombre_usuario or '').strip().lower()
            coinciden = [s for s in solicitantes
                         if (fono and digitos(s.telefono) == fono) or (nombre and s.nombre.strip().lower() == nombre)]
            if len(coinciden) == 1:
                elegido = coinciden[0]
        if elegido is not None:
            actividad.solicitante = elegido
            actividad.save(update_fields=['solicitante'])


def devolver_datos(apps, schema_editor):
    """Vuelta atrás: copia los datos del solicitante a las columnas de antes."""
    AtencionSocial = apps.get_model('ActividadesApp', 'AtencionSocial')
    Actividad = apps.get_model('ActividadesApp', 'Actividad')
    for atencion in AtencionSocial.objects.select_related('solicitante'):
        atencion.nombre_solicitante = atencion.solicitante.nombre
        atencion.rut_solicitante = atencion.solicitante.rut
        atencion.telefono_solicitante = atencion.solicitante.telefono
        atencion.save()
    for actividad in Actividad.objects.exclude(solicitante=None).select_related('solicitante'):
        actividad.nombre_usuario = actividad.solicitante.nombre
        actividad.telefono_usuario = actividad.solicitante.telefono
        actividad.save()


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('UsuarioApp', '0009_organizacion_a_actividadesapp'),
        ('ActividadesApp', '0011_estado_evidencia_ingresada'),
    ]

    operations = [
        # 1. Organizacion: la tabla ya existe; solo se registra en el estado de ActividadesApp
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Organizacion',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('nombre', models.CharField(max_length=150, verbose_name='Organización')),
                        ('domicilio_legal', models.CharField(blank=True, default='', max_length=200, verbose_name='Domicilio legal')),
                        ('socios_activos', models.PositiveIntegerField(blank=True, null=True, verbose_name='Socios activos')),
                        ('fecha_constitucion', models.DateField(blank=True, null=True, verbose_name='Fecha de constitución')),
                        ('numero_registro_pj', models.CharField(max_length=20, verbose_name='N° registro personalidad jurídica')),
                        ('fecha_inscripcion', models.DateField(verbose_name='Fecha de inscripción en el registro')),
                        ('numero_registro_directorio', models.PositiveIntegerField(blank=True, null=True, verbose_name='N° registro de directorio')),
                        ('delegacion', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='organizaciones', to='UsuarioApp.delegacion', verbose_name='Territorio / delegación')),
                    ],
                    options={
                        'verbose_name': 'Organización',
                        'verbose_name_plural': 'Organizaciones',
                        'db_table': 'organizacion',
                        'ordering': ['nombre'],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(mover_tipo_de_contenido, devolver_tipo_de_contenido),
        migrations.AddField(
            model_name='organizacion',
            name='tipo',
            field=models.CharField(blank=True, choices=[('FUNCIONAL', 'Organización comunitaria funcional'), ('ADULTO_MAYOR', 'Club de adulto mayor'), ('DEPORTIVA', 'Organización deportiva'), ('CULTURAL', 'Centro de madres, centro cultural o agrupación juvenil'), ('COMITE', 'Comité de vecinos, de allegados o de seguridad')], default='', max_length=15, verbose_name='Tipo de organización'),
        ),

        # 2. Solicitantes y representantes
        migrations.CreateModel(
            name='Solicitante',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rut', models.CharField(max_length=12, unique=True, verbose_name='RUT')),
                ('nombre', models.CharField(max_length=200, verbose_name='Nombre')),
                ('telefono', models.CharField(blank=True, default='', max_length=20, verbose_name='Teléfono')),
            ],
            options={
                'verbose_name': 'Solicitante',
                'verbose_name_plural': 'Solicitantes',
                'db_table': 'solicitante',
                'ordering': ['nombre'],
            },
        ),
        migrations.CreateModel(
            name='Representante',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cargo', models.CharField(choices=[('PRESIDENTE', 'Presidente'), ('SECRETARIO', 'Secretario'), ('TESORERO', 'Tesorero')], max_length=10, verbose_name='Cargo')),
                ('organizacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='representantes', to='ActividadesApp.organizacion', verbose_name='Organización')),
                ('solicitante', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cargos', to='ActividadesApp.solicitante', verbose_name='Representante')),
            ],
            options={
                'verbose_name': 'Representante',
                'verbose_name_plural': 'Representantes',
                'db_table': 'representante',
                'constraints': [models.UniqueConstraint(fields=('organizacion', 'cargo'), name='un_cargo_por_organizacion')],
            },
        ),

        # 3. Atenciones y actividades apuntan al solicitante (primero sin exigirlo, para poder llenarlo)
        migrations.AddField(
            model_name='atencionsocial',
            name='solicitante',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='atenciones', to='ActividadesApp.solicitante', verbose_name='Solicitante'),
        ),
        migrations.AddField(
            model_name='actividad',
            name='solicitante',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='actividades', to='ActividadesApp.solicitante', verbose_name='Persona atendida'),
        ),
        migrations.RunPython(crear_solicitantes, devolver_datos),
        migrations.AlterField(
            model_name='atencionsocial',
            name='solicitante',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='atenciones', to='ActividadesApp.solicitante', verbose_name='Solicitante'),
        ),
        migrations.RemoveField(model_name='atencionsocial', name='nombre_solicitante'),
        migrations.RemoveField(model_name='atencionsocial', name='rut_solicitante'),
        migrations.RemoveField(model_name='atencionsocial', name='telefono_solicitante'),
        migrations.RemoveField(model_name='actividad', name='nombre_usuario'),
        migrations.RemoveField(model_name='actividad', name='telefono_usuario'),
    ]
