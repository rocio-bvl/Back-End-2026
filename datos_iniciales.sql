-- ============================================================================
-- SGR Municipalidad de La Serena: DATOS INICIALES (datos de ejemplo, todos ficticios)
-- Importar en phpMyAdmin (base "municipalidad") DESPUÉS de ejecutar:
--     python manage.py migrate
-- Importar UNA sola vez en una base vacía. Si se importa dos veces fallará por llaves duplicadas.
--
-- Usuarios de prueba (todos con la contraseña: Serena2026!)
--   11111111-1  Administrador
--   22222222-2  Coordinador (solo visualiza)
--   33333333-3  Delegada de Las Compañías (Patricia Vega)
--   44444444-4  Delegado de Rural (Rodrigo Araya)
--   14141414-3  Delegada de La Pampa (Carolina Navarro)
--   55555555-5  Funcionaria de Las Compañías, territorio Sector Alto (Camila Rojas)
--   66666666-6  Funcionario de Las Compañías, territorio Villa Ejemplo (Diego Muñoz)
--   y 8 Funcionarios más en Las Compañías, Rural, La Pampa, La Antena y Centro (ver tabla usuario)
-- ============================================================================

SET NAMES utf8mb4;
START TRANSACTION;

-- ---------------------------------------------------------------------------
-- Roles (enumeración RolChoices)
-- ---------------------------------------------------------------------------
INSERT INTO `rol` (`id`, `codigo`, `nombre`, `descripcion`) VALUES
(1, 'Admin',       'Administrador',    'Acceso total: usuarios, delegaciones, metas y corrección de fechas'),
(2, 'Coordinador', 'Coordinador',      'Visualiza actividades, usuarios, delegaciones y metas de todas las delegaciones; asigna encargados'),
(3, 'Delegado',    'Delegado',         'Gestiona los Funcionarios y las metas de su delegación, valida actividades y asigna encargados'),
(5, 'Funcionario', 'Funcionario',      'Registra actividades y atenciones sociales');

-- ---------------------------------------------------------------------------
-- Delegaciones (nombre = código que viaja en las direcciones; nombre_visible = lo que se lee).
-- El Administrador agrega más desde Administración > Gestión > Delegaciones.
-- ---------------------------------------------------------------------------
INSERT INTO `delegacion` (`id`, `nombre`, `nombre_visible`, `ambito`, `estado`) VALUES
(1, 'RURAL',         'Rural',         'Rural',  'ACTIVO'),
(2, 'LAS_COMPANIAS', 'Las Compañías', 'Urbano', 'ACTIVO'),
(3, 'LA_PAMPA',      'La Pampa',      'Urbano', 'ACTIVO'),
(4, 'LA_ANTENA',     'La Antena',     'Urbano', 'ACTIVO'),
(5, 'CENTRO',        'Centro',        'Urbano', 'ACTIVO');

-- ---------------------------------------------------------------------------
-- Territorios: alimentan la lista desplegable del formulario de actividades (cada uno pertenece a una delegación)
-- ---------------------------------------------------------------------------
INSERT INTO `territorio` (`id`, `nombre`, `estado`, `delegacion_id`) VALUES
(1,  'Sector Alto',        'ACTIVO', 2),
(2,  'Sector Bajo',        'ACTIVO', 2),
(3,  'Villa Ejemplo',      'ACTIVO', 2),
(4,  'Las Compañías Centro','ACTIVO', 2),
(5,  'Localidad Norte',    'ACTIVO', 1),
(6,  'Localidad Sur',      'ACTIVO', 1),
(7,  'La Pampa Alta',      'ACTIVO', 3),
(8,  'La Pampa Baja',      'ACTIVO', 3),
(9,  'La Antena Oriente',  'ACTIVO', 4),
(10, 'La Antena Poniente', 'ACTIVO', 4),
(11, 'Casco Histórico',    'ACTIVO', 5),
(12, 'Barrio Centro',      'ACTIVO', 5);

-- ---------------------------------------------------------------------------
-- Catálogo: los ITEM_GESTION activos son las opciones de "Ítem / comisión" del formulario de actividades
-- ---------------------------------------------------------------------------
INSERT INTO `catalogo` (`id`, `tipo`, `nombre`, `valor`, `estado`, `area_id`, `padre_id`) VALUES
(1, 'ITEM_GESTION',     'Atención de Usuario Teléfono y Presencial', NULL, 'ACTIVO', NULL, NULL),
(2, 'ITEM_GESTION',     'Visitas, Reuniones con Organizaciones',     NULL, 'ACTIVO', NULL, NULL),
(3, 'ITEM_GESTION',     'Fiscalizaciones de Terreno',                NULL, 'ACTIVO', NULL, NULL),
(4, 'AREA',             'ORG COM',                                   NULL, 'ACTIVO', NULL, NULL),
(5, 'AREA',             'ÁREA SOCIAL',                               NULL, 'ACTIVO', NULL, NULL),
(6, 'SERVICIO',         'Orientación y derivación',                  NULL, 'ACTIVO', NULL, NULL),
(7, 'TIPO_ATENCION',    'Ayuda social',                              NULL, 'ACTIVO', 5,    NULL),
(8, 'SUBTIPO_ATENCION', 'Canasta familiar',                          NULL, 'ACTIVO', 5,    7),
(9, 'TIPO_AJUSTE',      'Permiso o licencia',                        NULL, 'ACTIVO', NULL, NULL),
(10, 'TIPO_ATENCION',   'Orientación social',                        NULL, 'ACTIVO', 5,    NULL),
(11, 'SUBTIPO_ATENCION', 'Postulación a subsidio habitacional',      NULL, 'ACTIVO', 5,    10);

-- ---------------------------------------------------------------------------
-- Cargos
-- ---------------------------------------------------------------------------
INSERT INTO `cargo` (`id`, `codigo`, `nombre`, `vigencia_inicio`, `vigencia_fin`, `estado`, `area_id`) VALUES
(1, 'TERR-OOCC', 'Territorial OO.CC.',      '2026-01-01', NULL, 'ACTIVO', 4),
(2, 'DELEGADO',  'Delegado Territorial',    '2026-01-01', NULL, 'ACTIVO', 4),
(3, 'SOCIAL',    'Profesional Área Social', '2026-01-01', NULL, 'ACTIVO', 5);

-- ---------------------------------------------------------------------------
-- Periodos trimestrales (días computables = días corridos del trimestre)
-- ---------------------------------------------------------------------------
INSERT INTO `periodo` (`id`, `nombre`, `fecha_inicio`, `fecha_termino`, `dias_computables`, `estado`,
                    `umbral_verde`, `umbral_ambar`, `umbral_colectivo`, `tope_cumplimiento`) VALUES
(1, 'T3 - 2026', '2026-07-01', '2026-09-30', 92, 'ACTIVO', 100.00, 60.00, 80.00, 150.00),
(2, 'T4 - 2026', '2026-10-01', '2026-12-31', 92, 'ACTIVO', 100.00, 60.00, 80.00, 150.00);

-- ---------------------------------------------------------------------------
-- Metas por cargo (los ponderadores de cada cargo suman 100).
-- delegacion_id NULL = meta general de la municipalidad (solo el Administrador).
-- Las metas 17 a 19 son propias de Las Compañías: para el cargo 1 reemplazan a las generales en esa delegación.
-- ---------------------------------------------------------------------------
INSERT INTO `meta_desempeno` (`id`, `valor_objetivo`, `unidad`, `ponderador`, `cargo_id`, `item_id`, `periodo_id`, `delegacion_id`) VALUES
(1,  60, 'actividades', 40.00, 1, 1, 1, NULL),
(2,  24, 'actividades', 35.00, 1, 2, 1, NULL),
(3,  12, 'actividades', 25.00, 1, 3, 1, NULL),
(4,  30, 'actividades', 30.00, 2, 1, 1, NULL),
(5,  30, 'actividades', 50.00, 2, 2, 1, NULL),
(6,   6, 'actividades', 20.00, 2, 3, 1, NULL),
(7,  45, 'actividades', 60.00, 3, 1, 1, NULL),
(8,  20, 'actividades', 40.00, 3, 2, 1, NULL),
(9,  60, 'actividades', 40.00, 1, 1, 2, NULL),
(10, 24, 'actividades', 35.00, 1, 2, 2, NULL),
(11, 12, 'actividades', 25.00, 1, 3, 2, NULL),
(12, 30, 'actividades', 30.00, 2, 1, 2, NULL),
(13, 30, 'actividades', 50.00, 2, 2, 2, NULL),
(14,  6, 'actividades', 20.00, 2, 3, 2, NULL),
(15, 45, 'actividades', 60.00, 3, 1, 2, NULL),
(16, 20, 'actividades', 40.00, 3, 2, 2, NULL),
(17, 50, 'actividades', 30.00, 1, 1, 2, 2),
(18, 30, 'actividades', 50.00, 1, 2, 2, 2),
(19, 10, 'actividades', 20.00, 1, 3, 2, 2);

-- ---------------------------------------------------------------------------
-- Usuarios de prueba (contraseña: Serena2026!). Solo los Funcionarios tienen territorio.
-- ---------------------------------------------------------------------------
INSERT INTO `usuario` (`id`, `password`, `last_login`, `is_superuser`, `is_staff`, `rut`, `nombre`, `apellido`,
                    `email`, `telefono`, `foto`, `activo`, `creado`, `cargo_id`, `delegacion_id`, `territorio_id`) VALUES
(1, 'pbkdf2_sha256$1000000$oVxLBAwkKjKkwwNuafdnTl$s6SDet+BXDM5Duma3hTPpjM05Shs0sSaDVBGb2IVYkA=', NULL, 1, 1,
    '11111111-1', 'Admin', 'Sistema', 'admin@laserena.cl', '', '', 1, UTC_TIMESTAMP(6), NULL, NULL, NULL),
(2, 'pbkdf2_sha256$1000000$NU8IyHhhYf0coGRFG1qnXP$hMHE5nfsWUTPst5IBQU/WbpLcROukVTfZDP/STp7s1w=', NULL, 0, 0,
    '22222222-2', 'Coordinación', 'General', 'coordinador@laserena.cl', '', '', 1, UTC_TIMESTAMP(6), NULL, NULL, NULL),
(3, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '33333333-3', 'Patricia', 'Vega Rojas', 'delegado@laserena.cl', '912000003', '', 1, UTC_TIMESTAMP(6), 2, 2, NULL),
(4, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '44444444-4', 'Rodrigo', 'Araya Díaz', 'delegado.rural@laserena.cl', '912000004', '', 1, UTC_TIMESTAMP(6), 2, 1, NULL),
(5, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '55555555-5', 'Camila', 'Rojas Pizarro', 'funcionario@laserena.cl', '912000005', '', 1, UTC_TIMESTAMP(6), 1, 2, 1),
(6, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '66666666-6', 'Diego', 'Muñoz Castillo', 'funcionaria.apoyo@laserena.cl', '912000006', '', 1, UTC_TIMESTAMP(6), 1, 2, 3),
(7, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '77777777-7', 'Valentina', 'Torres Cortés', 'valentina.torres@laserena.cl', '912000007', '', 1, UTC_TIMESTAMP(6), 1, 2, 2),
(8, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '88888888-8', 'Matías', 'González Alfaro', 'matias.gonzalez@laserena.cl', '912000008', '', 1, UTC_TIMESTAMP(6), 1, 2, 4),
(9, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '99999999-9', 'Fernanda', 'Herrera Olivares', 'fernanda.herrera@laserena.cl', '912000009', '', 1, UTC_TIMESTAMP(6), 1, 1, 5),
(10, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '10101010-4', 'Ignacio', 'Pérez Contreras', 'ignacio.perez@laserena.cl', '912000010', '', 1, UTC_TIMESTAMP(6), 1, 1, 6),
(11, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '12121212-9', 'Javiera', 'Castro Bravo', 'javiera.castro@laserena.cl', '912000011', '', 1, UTC_TIMESTAMP(6), 1, 3, 7),
(12, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '13131313-6', 'Sebastián', 'Fuentes Lagos', 'sebastian.fuentes@laserena.cl', '912000012', '', 1, UTC_TIMESTAMP(6), 1, 3, 8),
(13, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '14141414-3', 'Carolina', 'Navarro Silva', 'delegado.pampa@laserena.cl', '912000013', '', 1, UTC_TIMESTAMP(6), 2, 3, NULL),
(14, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '15151515-0', 'Tomás', 'Espinoza Vera', 'tomas.espinoza@laserena.cl', '912000014', '', 1, UTC_TIMESTAMP(6), 1, 4, 9),
(15, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '16161616-8', 'Antonia', 'Reyes Gallardo', 'antonia.reyes@laserena.cl', '912000015', '', 1, UTC_TIMESTAMP(6), 3, 5, 11);

INSERT INTO `usuario_rol` (`id`, `fecha_asignacion`, `asignado_por_id`, `rol_id`, `usuario_id`) VALUES
(1, UTC_TIMESTAMP(6), NULL, 1, 1),
(2, UTC_TIMESTAMP(6), 1, 2, 2),
(3, UTC_TIMESTAMP(6), 1, 3, 3),
(4, UTC_TIMESTAMP(6), 1, 3, 4),
(5, UTC_TIMESTAMP(6), 1, 5, 5),
(6, UTC_TIMESTAMP(6), 1, 5, 6),
(7, UTC_TIMESTAMP(6), 1, 5, 7),
(8, UTC_TIMESTAMP(6), 1, 5, 8),
(9, UTC_TIMESTAMP(6), 1, 5, 9),
(10, UTC_TIMESTAMP(6), 1, 5, 10),
(11, UTC_TIMESTAMP(6), 1, 5, 11),
(12, UTC_TIMESTAMP(6), 1, 5, 12),
(13, UTC_TIMESTAMP(6), 1, 3, 13),
(14, UTC_TIMESTAMP(6), 1, 5, 14),
(15, UTC_TIMESTAMP(6), 1, 5, 15);

-- ---------------------------------------------------------------------------
-- Solicitudes sociales (las registra un funcionario; después se les vinculan actividades)
--   SOC1: En proceso (las actividades ACT3 y ACT6 la atienden). SOC2 y SOC3: Pendientes.
--   Las acciones de una solicitud son las actividades vinculadas a ella (una o varias).
-- ---------------------------------------------------------------------------
INSERT INTO `atencion_social` (`id`, `fecha`, `nombre_solicitante`, `rut_solicitante`, `telefono_solicitante`, `requiere_visita`,
                            `tipo_atencion_id`, `subtipo_atencion_id`, `usuario_id`) VALUES
(1, '2026-10-22 13:00:00', 'María Ejemplo',  '12345678-5', '911112222', 1, 7,  8,    5),
(2, '2026-10-23 15:30:00', 'Juan Ficticio',  '11222333-9', '922223333', 0, 10, 11,   6),
(3, '2026-10-24 12:00:00', 'Rosa Prueba',    '9876543-3',  '933334444', 1, 7,  NULL, 9);

-- ---------------------------------------------------------------------------
-- Actividades de ejemplo:
--   1 PROGRAMADA (compromiso con fecha futura), a cargo de Diego Muñoz.
--   2 EN_TUBO sin fecha de ejecución (depende de factores externos).
--   3 REGISTRADA (ejecutada, espera validación), vinculada a la solicitud social SOC1.
--   4 En el Tubo, con fecha de ejecución ya agregada (PROGRAMADA).
--   5 PROGRAMADA en la delegación Rural.
--   6 PROGRAMADA, segunda actividad de la solicitud SOC1 (visita domiciliaria), a cargo de Diego Muñoz.
-- ---------------------------------------------------------------------------
INSERT INTO `actividad` (`id`, `fecha`, `solicitud_problema`, `accion`, `territorio_id`, `depende_externos`,
                        `fecha_realizacion`, `estado`, `item_id`, `periodo_id`, `servicio_id`, `usuario_id`,
                        `encargado_id`, `solicitud_id`) VALUES
(1, '2026-10-20 12:30:00', 'Reunión con la junta de vecinos por luminarias en pasaje principal.', 'Reunión con organización', 3, 0, '2026-11-15', 'PROGRAMADA', 2, 2, NULL, 5, 6, NULL),
(2, '2026-10-21 14:00:00', 'Poda de árboles que tapan luminarias: depende de la respuesta de la empresa eléctrica.', 'Gestión con unidad de alumbrado', 1, 1, NULL, 'EN_TUBO', 2, 2, NULL, 5, NULL, NULL),
(3, '2026-10-22 16:00:00', 'Solicitud de apoyo social por emergencia.', 'Atención presencial', 4, 0, '2026-10-22', 'REGISTRADA', 1, 2, NULL, 5, NULL, 1),
(4, '2026-10-23 10:00:00', 'Limpieza de microbasural: depende del camión municipal.', 'Coordinación con aseo y ornato', 2, 1, '2026-11-10', 'PROGRAMADA', 3, 2, NULL, 7, NULL, NULL),
(5, '2026-10-24 09:00:00', 'Reunión con comité de agua potable rural.', 'Reunión con organización', 5, 0, '2026-11-05', 'PROGRAMADA', 2, 2, NULL, 9, NULL, NULL),
(6, '2026-10-25 11:00:00', 'Visita domiciliaria para evaluar la ayuda social solicitada.', 'Visita domiciliaria', 4, 0, '2026-11-04', 'PROGRAMADA', 2, 2, NULL, 5, 6, 1);

INSERT INTO `evidencia` (`id`, `version`, `imagen`, `comentario`, `fecha`, `estado_revision`, `actividad_id`, `reemplaza_a_id`) VALUES
(1, 1, '', 'Se atendió a la vecina y se derivó al área social para evaluar la ayuda.', '2026-10-22 16:30:00', 'PENDIENTE', 3, NULL);

INSERT INTO `comentario_actividad` (`id`, `texto`, `fecha`, `actividad_id`, `usuario_id`) VALUES
(1, 'Se envió el correo a la empresa eléctrica; se espera respuesta.', '2026-10-23 13:00:00', 2, 5),
(2, 'La directiva confirmó asistencia para la fecha programada.', '2026-10-24 12:15:00', 1, 5);

INSERT INTO `auditoria` (`id`, `evento`, `fecha`, `entidad`, `id_entidad`, `valor_anterior`, `valor_nuevo`, `usuario_id`) VALUES
(1, 'CREACION', '2026-10-20 12:30:00', 'Actividad', '1', '', 'ACT1 - Reunión con organización [PROGRAMADA]', 5),
(2, 'CREACION', '2026-10-21 14:00:00', 'Actividad', '2', '', 'ACT2 - Gestión con unidad de alumbrado [EN_TUBO]', 5),
(3, 'CREACION', '2026-10-22 13:00:00', 'AtencionSocial', '1', '', 'SOC1 - María Ejemplo', 5),
(4, 'CREACION', '2026-10-22 16:00:00', 'Actividad', '3', '', 'ACT3 - Atención presencial [REGISTRADA]', 5);

COMMIT;
