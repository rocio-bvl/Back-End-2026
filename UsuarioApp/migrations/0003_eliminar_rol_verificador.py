# El rol Verificador se elimina: sus funciones pasan al Delegado.
# Los usuarios que eran Verificador quedan como Delegado y se borra el rol.
# Además, el Coordinador pasa a ser staff (entra a Django Admin con permisos restringidos).

from django.db import migrations, models


def verificador_a_delegado(apps, schema_editor):
    Rol = apps.get_model('UsuarioApp', 'Rol')
    UsuarioRol = apps.get_model('UsuarioApp', 'UsuarioRol')
    Usuario = apps.get_model('UsuarioApp', 'Usuario')

    verificador = Rol.objects.filter(codigo='Verificador').first()
    if verificador is not None:
        delegado, creado = Rol.objects.get_or_create(
            codigo='Delegado', defaults={'nombre': 'Delegado', 'descripcion': 'Supervisa su delegación y valida evidencias'})
        for asignacion in UsuarioRol.objects.filter(rol=verificador):
            if UsuarioRol.objects.filter(usuario_id=asignacion.usuario_id, rol=delegado).exists():
                asignacion.delete()
            else:
                asignacion.rol = delegado
                asignacion.save()
        verificador.delete()

    # Coordinadores: is_staff = True (antes solo el Admin era staff)
    ids = UsuarioRol.objects.filter(rol__codigo='Coordinador').values_list('usuario_id', flat=True)
    Usuario.objects.filter(pk__in=list(ids), is_superuser=False).update(is_staff=True)


def no_revertir(apps, schema_editor):
    # Al revertir no se puede saber quién era Verificador: se deja como está
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("UsuarioApp", "0002_delete_codigootp"),
    ]

    operations = [
        migrations.RunPython(verificador_a_delegado, no_revertir),
        migrations.AlterField(
            model_name="rol",
            name="codigo",
            field=models.CharField(
                choices=[
                    ("Admin", "Administrador"),
                    ("Coordinador", "Coordinador"),
                    ("Delegado", "Delegado"),
                    ("Funcionario", "Funcionario"),
                    ("Consulta", "Usuario Consulta"),
                ],
                max_length=20,
                unique=True,
                verbose_name="Código",
            ),
        ),
    ]
