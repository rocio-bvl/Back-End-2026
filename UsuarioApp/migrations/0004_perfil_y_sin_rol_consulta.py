from django.db import migrations, models


def consulta_a_funcionario(apps, schema_editor):
    """El rol Consulta deja de existir: sus usuarios pasan a Funcionario (nadie pierde acceso ni historial)."""
    Rol = apps.get_model('UsuarioApp', 'Rol')
    UsuarioRol = apps.get_model('UsuarioApp', 'UsuarioRol')
    consulta = Rol.objects.filter(codigo='Consulta').first()
    if consulta is None:
        return
    funcionario, _ = Rol.objects.get_or_create(
        codigo='Funcionario',
        defaults={'nombre': 'Funcionario',
                  'descripcion': 'Registra actividades: ejecutadas, programadas o en el Tubo de Trabajo'})
    UsuarioRol.objects.filter(rol=consulta).update(rol=funcionario)
    consulta.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("UsuarioApp", "0003_eliminar_rol_verificador"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="telefono",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="Teléfono"),
        ),
        migrations.AddField(
            model_name="usuario",
            name="foto",
            field=models.ImageField(blank=True, default="", upload_to="perfiles/", verbose_name="Foto de perfil"),
        ),
        migrations.RunPython(consulta_a_funcionario, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="rol",
            name="codigo",
            field=models.CharField(
                choices=[("Admin", "Administrador"), ("Coordinador", "Coordinador"),
                         ("Delegado", "Delegado"), ("Funcionario", "Funcionario")],
                max_length=20, unique=True, verbose_name="Código"),
        ),
    ]
