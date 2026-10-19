from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from UsuarioApp.choices import (roles, orden_roles, estados_registro, delegaciones, tipos_catalogo,
                                ROLES_ADMINISTRACION, ROLES_REGISTRO, ROLES_VERIFICACION, ROLES_RESERVADOS)


class Catalogo(models.Model):
    tipo = models.CharField(max_length=20, choices=tipos_catalogo, verbose_name="Tipo")
    nombre = models.CharField(max_length=150, verbose_name="Nombre")
    valor = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Valor")
    estado = models.CharField(max_length=10, choices=estados_registro, default='ACTIVO', verbose_name="Estado")
    area = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='opciones_del_area', verbose_name="Área (vacío = todas)")
    padre = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='hijos', verbose_name="Catálogo padre")

    def __str__(self):
        return self.nombre

    def activar(self):
        self.estado = 'ACTIVO'
        self.save()

    def desactivar(self):
        self.estado = 'INACTIVO'
        self.save()

    class Meta:
        db_table = "catalogo"
        verbose_name = "Catálogo"
        verbose_name_plural = "Catálogos"
        ordering = ["tipo", "nombre"]


def opciones_catalogo(tipo, area=None):
    opciones = Catalogo.objects.filter(tipo=tipo, estado='ACTIVO')
    if area is not None:
        opciones = opciones.filter(models.Q(area=area) | models.Q(area__isnull=True))
    return opciones


class Rol(models.Model):
    codigo = models.CharField(max_length=20, unique=True, choices=roles, verbose_name="Código")
    nombre = models.CharField(max_length=60, verbose_name="Nombre")
    descripcion = models.CharField(max_length=255, blank=True, default="", verbose_name="Descripción")

    def __str__(self):
        return self.nombre

    class Meta:
        db_table = "rol"
        verbose_name = "Rol"
        verbose_name_plural = "Roles"
        ordering = ["id"]


class Cargo(models.Model):
    codigo = models.CharField(max_length=30, unique=True, verbose_name="Código")
    nombre = models.CharField(max_length=150, verbose_name="Nombre del cargo")
    vigencia_inicio = models.DateField(default=timezone.now, verbose_name="Vigencia desde")
    vigencia_fin = models.DateField(null=True, blank=True, verbose_name="Vigencia hasta")
    estado = models.CharField(max_length=10, choices=estados_registro, default='ACTIVO', verbose_name="Estado")
    area = models.ForeignKey(Catalogo, on_delete=models.PROTECT, null=True, blank=True, limit_choices_to={'tipo': 'AREA'}, related_name='cargos', verbose_name="Área")

    def __str__(self):
        return self.nombre

    def total_ponderadores(self, periodo, excluir=None):
        """Suma de los ponderadores de las metas del cargo en el periodo.
        'excluir' deja fuera una meta (la que se está modificando)."""
        metas = self.metas.filter(periodo=periodo)
        if excluir is not None and excluir.pk is not None:
            metas = metas.exclude(pk=excluir.pk)
        total = 0
        for meta in metas:
            total = total + meta.ponderador
        return total

    def validar_ponderadores(self, periodo):
        """True si las metas del cargo en el periodo suman exactamente 100%."""
        return self.total_ponderadores(periodo) == 100

    class Meta:
        db_table = "cargo"
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"
        ordering = ["nombre"]


class Delegacion(models.Model):
    nombre = models.CharField(max_length=100, unique=True, choices=delegaciones, verbose_name="Nombre")
    ambito = models.CharField(max_length=100, blank=True, default="", verbose_name="Ámbito")
    estado = models.CharField(max_length=10, choices=estados_registro, default='ACTIVO', verbose_name="Estado")

    def __str__(self):
        return self.get_nombre_display()

    class Meta:
        db_table = "delegacion"
        verbose_name = "Delegación"
        verbose_name_plural = "Delegaciones"
        ordering = ["nombre"]


class Usuario(AbstractUser):
    username = models.CharField(max_length=12, unique=True, db_column='rut', verbose_name="RUT", error_messages={'unique': "Ya existe un usuario con ese RUT."})
    first_name = models.CharField(max_length=100, blank=True, db_column='nombre', verbose_name="Nombre")
    last_name = models.CharField(max_length=100, blank=True, db_column='apellido', verbose_name="Apellido")
    email = models.EmailField(max_length=254, unique=True, verbose_name="Correo electrónico")
    is_active = models.BooleanField(default=True, db_column='activo', verbose_name="Activo")
    date_joined = models.DateTimeField(default=timezone.now, db_column='creado', verbose_name="Creado")
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, null=True, blank=True, related_name='usuarios', verbose_name="Cargo")
    delegacion = models.ForeignKey(Delegacion, on_delete=models.PROTECT, null=True, blank=True, related_name='usuarios', verbose_name="Delegación")

    def __str__(self):
        nombre = self.get_full_name()
        if nombre:
            return nombre
        return self.username

    def rut(self):
        return self.username

    def codigos_rol(self):
        # Una sola consulta (JOIN con rol). Se guarda en el objeto para no repetirla en la misma petición.
        if not hasattr(self, '_codigos_rol'):
            self._codigos_rol = list(self.roles_asignados.values_list('rol__codigo', flat=True))
        return self._codigos_rol

    def tiene_rol(self, lista_roles):
        if self.is_superuser:
            return True
        for codigo in self.codigos_rol():
            if codigo in lista_roles:
                return True
        return False

    def rol(self):
        codigos = self.codigos_rol()
        for codigo in orden_roles:
            if codigo in codigos:
                return codigo
        return ""

    # ----- permisos por rol (los usan las views y los templates: request.user.puede_administrar) -----
    def es_administrador(self):
        return self.tiene_rol(['Admin'])

    def puede_administrar(self):
        """Admin y Coordinador: usuarios, metas, auditoría, modificar y eliminar."""
        return self.tiene_rol(ROLES_ADMINISTRACION)

    def puede_registrar(self):
        """Admin, Coordinador y Funcionario: agregan actividades y compromisos."""
        return self.tiene_rol(ROLES_REGISTRO)

    def puede_verificar(self):
        """Admin, Coordinador y Delegado (este último, solo en su delegación)."""
        return self.tiene_rol(ROLES_VERIFICACION)

    def roles_asignables(self):
        """Roles que este usuario puede asignar al crear o editar usuarios.
        El Coordinador no puede crear Coordinadores ni Administradores."""
        if self.es_administrador():
            return list(roles)
        return [(codigo, nombre) for codigo, nombre in roles if codigo not in ROLES_RESERVADOS]

    def puede_editar_usuario(self, otro):
        """El Admin edita a todos. El Coordinador no edita a Administradores ni a otros Coordinadores."""
        if self.es_administrador():
            return True
        if not self.puede_administrar():
            return False
        if otro.pk == self.pk:
            return True
        return not (otro.is_superuser or otro.tiene_rol(ROLES_RESERVADOS))

    def sincronizar_acceso_admin(self):
        """Django Admin: el Admin es superusuario; el Coordinador entra como staff con permisos
        restringidos (ver UsuarioApp/admin_sgr.py). Un superusuario sin roles (createsuperuser) no se toca."""
        if hasattr(self, '_codigos_rol'):
            del self._codigos_rol
        codigos = self.codigos_rol()
        if not codigos:
            return
        self.is_superuser = 'Admin' in codigos
        self.is_staff = self.is_superuser or 'Coordinador' in codigos
        self.save(update_fields=['is_superuser', 'is_staff'])

    def area(self):
        if self.cargo and self.cargo.area:
            return self.cargo.area.nombre
        return ""

    class Meta:
        db_table = "usuario"
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ["first_name", "last_name"]


class UsuarioRol(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='roles_asignados', verbose_name="Usuario")
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name='asignaciones', verbose_name="Rol")
    fecha_asignacion = models.DateTimeField(default=timezone.now, verbose_name="Fecha de asignación")
    asignado_por = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='roles_que_asigno', verbose_name="Asignado por")

    def __str__(self):
        return f"{self.usuario} - {self.rol}"

    class Meta:
        db_table = "usuario_rol"
        verbose_name = "Rol de usuario"
        verbose_name_plural = "Roles de usuario"