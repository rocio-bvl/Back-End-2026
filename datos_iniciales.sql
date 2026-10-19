-- ============================================================================
-- SGR Municipalidad de La Serena: DATOS INICIALES (datos de ejemplo)
-- Importar en phpMyAdmin (base "municipalidad") DESPUÉS de ejecutar:
--     python manage.py migrate
-- Importar UNA sola vez. Si se importa dos veces fallará por llaves duplicadas.
--
-- Usuarios de prueba (todos con la contraseña: Serena2026!)
--   11111111-1  Administrador
--   22222222-2  Coordinador
--   33333333-3  Delegado (Las Compañías)
--   44444444-4  Delegado (Rural)
--   55555555-5  Funcionario (Las Compañías)
--   66666666-6  Usuario Consulta
-- ============================================================================

SET NAMES utf8mb4;
START TRANSACTION;

-- ---------------------------------------------------------------------------
-- Roles («enumeration» RolChoices)
-- ---------------------------------------------------------------------------
INSERT INTO `rol` (`id`, `codigo`, `nombre`, `descripcion`) VALUES
(1, 'Admin',       'Administrador',    'Acceso total. Único que puede modificar fechas y horas'),
(2, 'Coordinador', 'Coordinador',      'Mismas funciones que el Administrador, salvo crear Coordinadores o Administradores y modificar fechas'),
(3, 'Delegado',    'Delegado',         'Valida las evidencias de las actividades de su delegación'),
(5, 'Funcionario', 'Funcionario',      'Registra actividades con evidencia o como compromiso en el Tubo (no modifica)'),
(6, 'Consulta',    'Usuario Consulta', 'Solo visualiza tablero, semáforo y resumen');

-- ---------------------------------------------------------------------------
-- Delegaciones (el nombre es el código que usan los <select> de los templates)
-- ---------------------------------------------------------------------------
INSERT INTO `delegacion` (`id`, `nombre`, `ambito`, `estado`) VALUES
(1, 'RURAL',         'Rural',  'ACTIVO'),
(2, 'LAS_COMPANIAS', 'Urbano', 'ACTIVO'),
(3, 'LA_PAMPA',      'Urbano', 'ACTIVO'),
(4, 'LA_ANTENA',     'Urbano', 'ACTIVO'),
(5, 'CENTRO',        'Urbano', 'ACTIVO');

-- ---------------------------------------------------------------------------
-- Catálogo. IMPORTANTE: los ítems 1, 2 y 3 están escritos en actividad_form.html
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
(9, 'TIPO_AJUSTE',      'Permiso o licencia',                        NULL, 'ACTIVO', NULL, NULL);

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
-- Metas por cargo (los ponderadores de cada cargo suman 100)
-- ---------------------------------------------------------------------------
INSERT INTO `meta_desempeno` (`id`, `valor_objetivo`, `unidad`, `ponderador`, `cargo_id`, `item_id`, `periodo_id`) VALUES
(1,  60, 'actividades', 40.00, 1, 1, 1),
(2,  24, 'actividades', 35.00, 1, 2, 1),
(3,  12, 'actividades', 25.00, 1, 3, 1),
(4,  30, 'actividades', 30.00, 2, 1, 1),
(5,  30, 'actividades', 50.00, 2, 2, 1),
(6,   6, 'actividades', 20.00, 2, 3, 1),
(7,  45, 'actividades', 60.00, 3, 1, 1),
(8,  20, 'actividades', 40.00, 3, 2, 1),
(9,  60, 'actividades', 40.00, 1, 1, 2),
(10, 24, 'actividades', 35.00, 1, 2, 2),
(11, 12, 'actividades', 25.00, 1, 3, 2),
(12, 30, 'actividades', 30.00, 2, 1, 2),
(13, 30, 'actividades', 50.00, 2, 2, 2),
(14,  6, 'actividades', 20.00, 2, 3, 2),
(15, 45, 'actividades', 60.00, 3, 1, 2),
(16, 20, 'actividades', 40.00, 3, 2, 2);

-- ---------------------------------------------------------------------------
-- Usuarios de prueba (contraseña: Serena2026!)
-- ---------------------------------------------------------------------------
INSERT INTO `usuario` (`id`, `password`, `last_login`, `is_superuser`, `is_staff`, `rut`, `nombre`, `apellido`,
                    `email`, `activo`, `creado`, `cargo_id`, `delegacion_id`) VALUES
(1, 'pbkdf2_sha256$1000000$oVxLBAwkKjKkwwNuafdnTl$s6SDet+BXDM5Duma3hTPpjM05Shs0sSaDVBGb2IVYkA=', NULL, 1, 1,
    '11111111-1', 'Admin', 'Sistema', 'admin@laserena.cl', 1, UTC_TIMESTAMP(6), NULL, NULL),
(2, 'pbkdf2_sha256$1000000$NU8IyHhhYf0coGRFG1qnXP$hMHE5nfsWUTPst5IBQU/WbpLcROukVTfZDP/STp7s1w=', NULL, 0, 1,
    '22222222-2', 'Coordinación', 'General', 'coordinador@laserena.cl', 1, UTC_TIMESTAMP(6), NULL, NULL),
(3, 'pbkdf2_sha256$1000000$boykguIhx6JzuwVS4JD1Rd$VuxtS7PdwbPiMnl+i+lUqBIsxa/Iq/RMr5qb3ZrNwEk=', NULL, 0, 0,
    '33333333-3', 'Delegado', 'Compañías', 'delegado@laserena.cl', 1, UTC_TIMESTAMP(6), 2, 2),
(4, 'pbkdf2_sha256$1000000$a5ag9Q3cJ0mq1xd4jyL5wb$oVIOTqnPBU/YQRnU3mT8tenW7S0/eUcATELUb7J+O0o=', NULL, 0, 0,
    '44444444-4', 'Delegado', 'Rural', 'delegado.rural@laserena.cl', 1, UTC_TIMESTAMP(6), 2, 1),
(5, 'pbkdf2_sha256$1000000$jUd1K0NrxsETKyyrOnOsKP$NK4EzvOrFzopdtHEagyMtpfjf3Ovk8/d/VdZFgna6iA=', NULL, 0, 0,
    '55555555-5', 'Funcionario', 'Territorial', 'funcionario@laserena.cl', 1, UTC_TIMESTAMP(6), 1, 2),
(6, 'pbkdf2_sha256$1000000$7z7frBXHxlW1lael7gKock$kNIYjQKuWNXxmDE3oX9C1Al32+5w7ajhvFwH1LVwToY=', NULL, 0, 0,
    '66666666-6', 'Usuario', 'Consulta', 'consulta@laserena.cl', 1, UTC_TIMESTAMP(6), NULL, NULL);

INSERT INTO `usuario_rol` (`id`, `fecha_asignacion`, `asignado_por_id`, `rol_id`, `usuario_id`) VALUES
(1, UTC_TIMESTAMP(6), NULL, 1, 1),
(2, UTC_TIMESTAMP(6), 1,    2, 2),
(3, UTC_TIMESTAMP(6), 1,    3, 3),
(4, UTC_TIMESTAMP(6), 1,    3, 4),
(5, UTC_TIMESTAMP(6), 1,    5, 5),
(6, UTC_TIMESTAMP(6), 1,    6, 6);

-- ---------------------------------------------------------------------------
-- Registros de ejemplo para que los listados muestren datos y botones
-- Actividades del funcionario 55555555-5. Sin evidencia (no hay fotos cargadas), por eso están
-- EN_TUBO: son compromisos con fecha límite. Al subir la evidencia pasan a REGISTRADA.
-- ---------------------------------------------------------------------------
INSERT INTO `actividad` (`id`, `fecha`, `solicitud_problema`, `accion`, `contacto`, `telefono`, `territorio`,
                        `ingreso_agenda_colectiva`, `fecha_comprometida`, `estado`, `item_id`, `periodo_id`, `servicio_id`, `usuario_id`) VALUES
(1, '2026-09-22 12:30:00', 'Vecinos solicitan reparación de luminarias en pasaje principal.', 'Gestión con unidad de alumbrado', 'Directiva JJ.VV. Villa Ejemplo', '912345678', 'Sector Alto', 1, '2026-10-15', 'EN_TUBO', 2, 1, NULL, 5),
(2, '2026-09-23 14:00:00', 'Consulta telefónica por patente comercial.',  'Orientación telefónica', 'Vecino sector centro', '987654321', 'Centro', 1, '2026-10-20', 'EN_TUBO', 1, 1, 6, 5),
(3, '2026-09-24 16:00:00', 'Solicitud de apoyo social por emergencia.',   'Atención presencial', 'María Ejemplo', '911112222', 'Las Compañías', 1, '2026-10-10', 'EN_TUBO', 1, 1, NULL, 5);

INSERT INTO `atencion_social` (`id`, `nombre_solicitante`, `rut_solicitante`, `telefono_solicitante`, `requiere_visita`,
                            `actividad_id`, `subtipo_atencion_id`, `tipo_atencion_id`) VALUES
(1, 'María Ejemplo', '12345678-5', '911112222', 1, 3, 8, 7);

INSERT INTO `gestion_social` (`id`, `numero_gestion`, `tipo`, `accion`, `fecha`, `atencion_id`) VALUES
(1, 1, 'VISITA',  'Visita domiciliaria',  '2026-09-25', 1),
(2, 2, 'INFORME', 'Informe social emitido', '2026-09-26', 1);

INSERT INTO `auditoria` (`id`, `evento`, `fecha`, `entidad`, `id_entidad`, `valor_anterior`, `valor_nuevo`, `usuario_id`) VALUES
(1, 'CREACION', '2026-09-22 12:30:00', 'Actividad', '1', '', 'ACT1 - Gestión con unidad de alumbrado [EN_TUBO]', 5),
(2, 'CREACION', '2026-09-23 14:00:00', 'Actividad', '2', '', 'ACT2 - Orientación telefónica [EN_TUBO]', 5);

COMMIT;
