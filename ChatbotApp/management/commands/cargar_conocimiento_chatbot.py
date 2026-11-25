"""Carga (idempotente) los documentos de conocimiento que alimentan el RAG del chatbot.

Cada documento se identifica por su `titulo`: ejecutar el comando N veces actualiza el contenido
sin duplicar filas. No contiene secretos ni datos personales; el Administrador puede editarlos
después desde Django Admin.
"""
from django.core.management.base import BaseCommand

from ChatbotApp.models import DocumentoConocimiento

DOCUMENTOS = [
    {
        'titulo': 'Registrar una actividad',
        'palabras_clave': 'registrar, actividad, formulario, fecha, evidencia, item, territorio',
        'roles_permitidos': '',
        'contenido': (
            "Para registrar una actividad entra a Mi Gestión y usa el formulario de nueva actividad. "
            "Elige el ítem de gestión, el territorio (dentro de tu delegación) y la fecha de realización. "
            "Si la fecha es hoy o anterior, la actividad queda esperando su evidencia (comentario "
            "obligatorio y foto opcional). Si la fecha es futura, queda como compromiso PROGRAMADA. "
            "Si depende de factores externos, se puede dejar en el Tubo de Trabajo sin fecha. "
            "El Delegado registra gestiones que quedan ingresadas pero no suman puntaje. "
            "El Administrador puede corregir la fecha de ingreso de una actividad."
        ),
    },
    {
        'titulo': 'Estados de una actividad',
        'palabras_clave': 'estado, estados, programada, en tubo, evidencia ingresada, rechazada, validada',
        'roles_permitidos': '',
        'contenido': (
            "Estados de una actividad: PROGRAMADA (compromiso con fecha futura, aún no realizada), "
            "EN_TUBO (depende de terceros y no tiene fecha), EVIDENCIA_INGRESADA (ya se realizó y espera "
            "validación), RECHAZADA (la evidencia fue rechazada y debe reingresarse; la actividad no se "
            "anula) y VALIDADA (completada por el Delegado o el Administrador; cuenta para la meta). "
            "Una actividad pendiente puede tener un encargado que la realice."
        ),
    },
    {
        'titulo': 'Evidencia y validación',
        'palabras_clave': 'evidencia, foto, comentario, validar, validacion, rechazar, version',
        'roles_permitidos': '',
        'contenido': (
            "La evidencia respalda una actividad realizada: lleva un comentario obligatorio y una foto "
            "opcional de hasta 5 MB. Si se reemplaza, queda una nueva versión que indica a cuál reemplaza. "
            "El Delegado o el Administrador revisan la evidencia en Verificación y deciden aprobarla "
            "(la actividad pasa a VALIDADA) o rechazarla (pasa a RECHAZADA para volver a ingresar la "
            "evidencia). En pantallas de solo lectura, como el Coordinador, no se valida."
        ),
    },
    {
        'titulo': 'Tubo de Trabajo',
        'palabras_clave': 'tubo de trabajo, pendiente, externos, sin fecha, asignar fecha',
        'roles_permitidos': '',
        'contenido': (
            "El Tubo de Trabajo reúne las actividades que dependen de factores externos y todavía no "
            "tienen fecha de realización. Se consultan en la pantalla del Tubo; cuando se conoce la fecha "
            "se le asigna y la actividad pasa a PROGRAMADA. El Delegado puede asignar un encargado a las "
            "actividades pendientes de su delegación."
        ),
    },
    {
        'titulo': 'Metas y Semáforo',
        'palabras_clave': 'meta, metas, semaforo, indicador, avance, periodo, ponderador, cumplimiento',
        'roles_permitidos': '',
        'contenido': (
            "Las metas de desempeño se definen por periodo, cargo e ítem de gestión, con un valor objetivo "
            "y un ponderador. El avance se calcula con las actividades validadas del periodo y se compara "
            "con la meta esperada según los días transcurridos. El Semáforo muestra el cumplimiento por "
            "delegación y por cargo con colores verde, ámbar y rojo. El asistente no recalcula indicadores: "
            "para el cumplimiento exacto hay que revisar la pantalla del Semáforo. Solo el Administrador "
            "gestiona las metas generales; el Delegado, las de su delegación."
        ),
    },
    {
        'titulo': 'Gestión social: solicitantes y atenciones',
        'palabras_clave': 'gestion social, atencion, atenciones, solicitante, organizacion, visita, estado',
        'roles_permitidos': '',
        'contenido': (
            "En Registro de Atenciones un funcionario registra la solicitud de una persona natural. La "
            "persona se identifica por RUT: si ya existe, el sistema completa sus datos; si no, se puede "
            "agregar como solicitante y vincularla a una organización. Los datos personales (RUT, nombre y "
            "teléfono) se guardan solo en la ficha del solicitante y no se muestran al asistente. Cada "
            "solicitud tiene estado Pendiente (sin actividades), En proceso (con actividades sin validar) "
            "o Atendida (todas sus actividades validadas). Las acciones que atienden la solicitud son "
            "actividades vinculadas a ella."
        ),
    },
    {
        'titulo': 'Usuarios y roles',
        'palabras_clave': 'usuario, usuarios, rol, roles, admin, coordinador, delegado, funcionario, permisos',
        'roles_permitidos': '',
        'contenido': (
            "Roles del sistema: Administrador (acceso total, gestiona usuarios, delegaciones, metas y "
            "corrección de fechas), Coordinador (visualiza información de todas las delegaciones y asigna "
            "encargados), Delegado (gestiona funcionarios y metas de su delegación, valida actividades) y "
            "Funcionario (registra actividades y atenciones sociales). Cada usuario tiene un RUT como "
            "nombre de usuario, cargo, delegación y, si es funcionario, un territorio. Solo el "
            "Administrador entra a Django Admin."
        ),
    },
    {
        'titulo': 'Delegaciones y territorios',
        'palabras_clave': 'delegacion, delegaciones, territorio, territorios, sector, ambito, rural, urbano',
        'roles_permitidos': '',
        'contenido': (
            "Las delegaciones organizan el trabajo territorial (por ejemplo Rural, Las Compañías, La Pampa, "
            "La Antena y Centro). Cada delegación tiene un código interno (el que viaja en las direcciones), "
            "un nombre visible y un ámbito urbano o rural. Los territorios o sectores pertenecen a una "
            "delegación y alimentan la lista desplegable del formulario de actividades. El Administrador "
            "puede crear y editar delegaciones desde Administración; cada usuario ve solo el alcance que "
            "le corresponde según su rol."
        ),
    },
    {
        'titulo': 'Auditoría',
        'palabras_clave': 'auditoria, registro, eventos, logs, historial, accesos denegados',
        'roles_permitidos': '',
        'contenido': (
            "La Auditoría registra los eventos importantes del sistema (por ejemplo accesos denegados o "
            "cambios relevantes) con usuario, fecha, entidad y valores anterior y nuevo. El Administrador "
            "la revisa desde la pantalla de Auditoría. El asistente no puede modificar ni borrar registros "
            "de auditoría."
        ),
    },
    {
        'titulo': 'Recuperación de contraseña',
        'palabras_clave': 'contrasena, recuperar, olvide, correo, enlace, vencimiento, requisitos',
        'roles_permitidos': '',
        'contenido': (
            "Si olvidaste tu contraseña, usa el enlace '¿Olvidaste tu contraseña?' en el login e ingresa tu "
            "correo. El sistema envía un enlace para crear una contraseña nueva que vence en 2 horas. La "
            "contraseña debe tener mayúscula, minúscula, número y símbolo especial, y no puede ser demasiado "
            "común ni parecida a tus datos. Si el correo no llega, revisa la carpeta de spam o consulta al "
            "Administrador del sistema."
        ),
    },
    {
        'titulo': 'Permisos del asistente',
        'palabras_clave': 'asistente, chatbot, permisos, quien puede, funcionario, alcance, solo lectura',
        'roles_permitidos': '',
        'contenido': (
            "El asistente está disponible para Administrador, Coordinador y Delegado; el Funcionario no ve "
            "el widget y el endpoint le responde 403. El asistente es de solo lectura: explica el sistema y "
            "resume datos, pero no registra, valida, modifica ni elimina información. El Delegado recibe "
            "datos únicamente de su delegación; el Administrador y el Coordinador, de toda la municipalidad. "
            "No entrega datos personales de solicitantes ni usuarios, ni credenciales."
        ),
    },
    {
        'titulo': 'Preguntas frecuentes',
        'palabras_clave': 'faq, preguntas, ayuda, no veo, widget, datos, conversacion, historial, error',
        'roles_permitidos': '',
        'contenido': (
            "Preguntas frecuentes: ¿Por qué no veo el asistente? Solo aparece para Admin, Coordinador y "
            "Delegado. ¿El asistente modifica datos? No, es de solo lectura. ¿Qué información usa? "
            "Documentación interna del SGR y datos agregados según tu rol, sin nombres ni RUT. ¿Guarda la "
            "conversación? Sí, cada usuario tiene su propio historial y puede borrarlo con el botón Nueva. "
            "¿Por qué no responde? Puede estar desactivado o sin proveedor de IA disponible; avisa al "
            "Administrador. ¿Puedo pedir que registre una actividad? No: el asistente solo explica cómo "
            "hacerlo. Para el detalle exacto de metas y avance, revisa el Semáforo."
        ),
    },
]


class Command(BaseCommand):
    help = "Carga o actualiza los documentos de conocimiento del chatbot (idempotente)."

    def handle(self, *args, **opciones):
        creados = 0
        actualizados = 0
        for datos in DOCUMENTOS:
            _, creado = DocumentoConocimiento.objects.update_or_create(
                titulo=datos['titulo'],
                defaults={
                    'contenido': datos['contenido'],
                    'palabras_clave': datos['palabras_clave'],
                    'roles_permitidos': datos['roles_permitidos'],
                    'activo': True,
                },
            )
            if creado:
                creados += 1
            else:
                actualizados += 1
        total = DocumentoConocimiento.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Documentos de conocimiento: {creados} creados, {actualizados} actualizados, {total} en total."
        ))
