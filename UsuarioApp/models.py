from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from UsuarioApp.choices import (roles, orden_roles, estados_registro, delegaciones, tipos_catalogo)


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

    def validar_ponderadores(self, periodo):
        total = 0
        for meta in self.metas.filter(periodo=periodo):
            total = total + meta.ponderador
        return total

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
        codigos = []
        for asignacion in self.roles_asignados.all():
            codigos.append(asignacion.rol.codigo)
        return codigos

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