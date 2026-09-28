# SGR: Sistema de Gestión y Control, Municipalidad de La Serena

Aplicación web en Django para registrar la gestión territorial de los funcionarios municipales: actividades diarias con evidencia fotográfica, compromisos del Tubo de Trabajo, gestión social, verificación de evidencias, metas trimestrales con semáforo de cumplimiento y auditoría de cambios.

Asignatura: Programación Back End (TI3041), Evaluación Sumativa 2.

## Tecnologías

- Python 3.12 y Django 4.2 LTS (compatible con MariaDB 10.4 de XAMPP y con MariaDB 10.11 de Ubuntu)
- MariaDB / MySQL (mysqlclient)
- Bootstrap 5.3 y framework visual de la Municipalidad de La Serena
- python-dotenv para las variables de entorno

## Estructura

```
config/            settings.py y urls.py del proyecto
UsuarioApp/        Usuario, Rol, UsuarioRol, Cargo, Delegacion, Catalogo, CodigoOTP
IndicadoresApp/    Periodo, MetaDesempeno, IndicadorDesempeno, AjusteDesempeno
ActividadesApp/    Actividad, Evidencia, Validacion, Compromiso, HistorialCompromiso,
                   AtencionSocial, GestionSocial
AuditoriaApp/      Auditoria
templates/         base.html, components/ y una carpeta por app
static/css/        styles.css (paleta municipal)
media/             fotografías de evidencia (se crea sola, no se sube a GitHub)
datos_iniciales.sql  roles, delegaciones, catálogo, periodos, metas y usuarios de prueba
.env.example       plantilla de las variables de entorno
```

## Variables de entorno

La configuración sensible (clave secreta, datos de la base de datos, hosts permitidos) está en un archivo `.env` junto a `manage.py`, que no se sube a GitHub. Para crearlo, copia `.env.example` como `.env` y completa los valores.

## Instalación local (Windows)

```
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        (y editar los valores)
python manage.py migrate
```

Después, en phpMyAdmin: base `municipalidad` > Importar > `datos_iniciales.sql` (una sola vez, después de migrar). Luego ejecuta `python manage.py runserver` y entra a http://127.0.0.1:8000.

La base `municipalidad` debe estar vacía antes del primer `migrate`, porque el proyecto usa un usuario personalizado (tabla `usuario`).

## Usuarios de prueba

Todos con la contraseña `Serena2026!`. El RUT se puede escribir con o sin puntos.

| RUT | Rol |
|---|---|
| 11111111-1 | Administrador (también entra a Django Admin) |
| 22222222-2 | Coordinador |
| 33333333-3 | Delegado (Las Compañías) |
| 44444444-4 | Verificador |
| 55555555-5 | Funcionario (Las Compañías) |
| 66666666-6 | Usuario Consulta |

Django Admin: http://127.0.0.1:8000/admin (todas las entidades registradas, con búsqueda).

## Listados y botones

Cada listado tiene los botones Agregar, Modificar, Eliminar y Buscar. Por ahora enlazan a Django Admin; el CRUD desde la propia interfaz corresponde a la siguiente evaluación. En Auditoría, Agregar, Modificar y Eliminar están deshabilitados a propósito: un registro de trazabilidad no se edita a mano.

## Pruebas automáticas

```
python manage.py test
```

Django crea la base `test_municipalidad`, así que el usuario de la base necesita permiso para crearla (en phpMyAdmin: privilegios de `admin_muni` sobre `test_municipalidad`, o CREATE y DROP globales).

## Despliegue en AWS EC2 (Ubuntu 24.04)

### 1. Crear la instancia

- AMI: Ubuntu Server 24.04 LTS, tipo t2.micro o t3.micro.
- Par de claves: descarga el archivo `.pem`.
- Grupo de seguridad, reglas de entrada:
  - SSH, puerto 22: Mi IP
  - TCP personalizado, puerto 8000: 0.0.0.0/0 (la aplicación)
  - HTTP, puerto 80: Mi IP (phpMyAdmin; no lo dejes abierto a todo internet)

### 2. Conectarse

```
ssh -i "clave.pem" ubuntu@IP_PUBLICA
```

En Windows, si SSH reclama por los permisos del `.pem`: clic derecho > Propiedades > Seguridad, y deja solo a tu usuario con permiso de lectura.

### 3. Instalar paquetes

```
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-dev default-libmysqlclient-dev build-essential pkg-config git mariadb-server
sudo systemctl enable --now mariadb
```

### 4. Crear la base de datos y el usuario

```
sudo mysql
```

```sql
CREATE DATABASE municipalidad CHARACTER SET utf8mb4 COLLATE utf8mb4_spanish_ci;
CREATE USER 'admin_muni'@'localhost' IDENTIFIED BY 'Ventana$123';
GRANT ALL PRIVILEGES ON municipalidad.* TO 'admin_muni'@'localhost';
GRANT ALL PRIVILEGES ON test_municipalidad.* TO 'admin_muni'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 5. Instalar phpMyAdmin

```
sudo apt install -y phpmyadmin
```

Durante la instalación, marca `apache2` con la barra espaciadora y responde "Sí" a dbconfig-common. Luego entra a `http://IP_PUBLICA/phpmyadmin` con `admin_muni`.

### 6. Clonar el proyecto y crear el entorno virtual

```
git clone https://github.com/TU_USUARIO/TU_REPOSITORIO.git
cd TU_REPOSITORIO
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 7. Crear el .env en el servidor

```
cp .env.example .env
nano .env
```

Completa `DB_PASSWORD` y una `SECRET_KEY` nueva, y agrega la IP pública a `ALLOWED_HOSTS`, por ejemplo: `ALLOWED_HOSTS=127.0.0.1,localhost,54.123.45.67`. Guarda con Ctrl+O, Enter, Ctrl+X.

### 8. Migrar y cargar los datos

```
python manage.py migrate
mysql -u admin_muni -p municipalidad < datos_iniciales.sql
```

### 9. Ejecutar

```
python manage.py runserver 0.0.0.0:8000
```

Abre `http://IP_PUBLICA:8000`. Para que siga funcionando al cerrar la terminal:

```
nohup python manage.py runserver 0.0.0.0:8000 > servidor.log 2>&1 &
```

Para detenerlo: `pkill -f runserver`.

La IP pública cambia cada vez que la instancia se detiene y se vuelve a iniciar. Si cambia, actualiza `ALLOWED_HOSTS` en `.env`, o asocia una IP elástica a la instancia.
