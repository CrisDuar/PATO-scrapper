-- DDL de referencia para las sub-tablas descritas en
-- Contexto_Limpieza_Datos_Scraper.md. Ejecutar una vez contra la
-- base de datos PostgreSQL del proyecto (DATABASE_URL en .env).

-- ==========================================================
-- Dashboard 01: Colombia Nacional / Región
-- ==========================================================

CREATE TABLE IF NOT EXISTS ipm_por_dominio (
    anio INTEGER NOT NULL,
    dominio TEXT NOT NULL,
    ipm DOUBLE PRECISION,
    fuente TEXT,
    fecha_extraccion TIMESTAMPTZ,
    fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, dominio)
);

CREATE TABLE IF NOT EXISTS privaciones_por_hogar (
    anio INTEGER NOT NULL,
    dominio TEXT NOT NULL,
    variable TEXT NOT NULL,
    ipm DOUBLE PRECISION,
    fuente TEXT,
    fecha_extraccion TIMESTAMPTZ,
    fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, dominio, variable)
);

CREATE TABLE IF NOT EXISTS proporcion_privaciones (
    anio INTEGER NOT NULL,
    dominio TEXT NOT NULL,
    porcentaje DOUBLE PRECISION,
    fuente TEXT,
    fecha_extraccion TIMESTAMPTZ,
    fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, dominio)
);

CREATE TABLE IF NOT EXISTS contribuciones_incidencia (
    anio INTEGER NOT NULL,
    dominio TEXT NOT NULL,
    dimension TEXT NOT NULL,
    porcentaje DOUBLE PRECISION,
    fuente TEXT,
    fecha_extraccion TIMESTAMPTZ,
    fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, dominio, dimension)
);

CREATE TABLE IF NOT EXISTS incidencia_por_sexo_persona (
    anio INTEGER NOT NULL,
    dominio TEXT NOT NULL,
    sexo TEXT NOT NULL,
    porcentaje DOUBLE PRECISION,
    fuente TEXT,
    fecha_extraccion TIMESTAMPTZ,
    fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, dominio, sexo)
);

CREATE TABLE IF NOT EXISTS incidencia_por_sexo_jefe_hogar (
    anio INTEGER NOT NULL,
    dominio TEXT NOT NULL,
    sexo TEXT NOT NULL,
    porcentaje DOUBLE PRECISION,
    fuente TEXT,
    fecha_extraccion TIMESTAMPTZ,
    fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, dominio, sexo)
);

-- ==========================================================
-- Dashboard 02: Pobreza Multidimensional Hogares Departamental
-- ==========================================================

CREATE TABLE IF NOT EXISTS dashboard_02 (
    anio INTEGER NOT NULL,
    region INTEGER NOT NULL,
    departamento INTEGER NOT NULL,
    personas_hogar INTEGER NOT NULL,
    priv_bajo_logro_educativo BOOLEAN,
    priv_analfabetismo BOOLEAN,
    priv_inasistencia_escolar BOOLEAN,
    priv_rezago_escolar BOOLEAN,
    priv_atencion_primera_infancia BOOLEAN,
    priv_trabajo_infantil BOOLEAN,
    priv_no_aseguramiento_salud BOOLEAN,
    priv_barreras_acceso_salud BOOLEAN,
    priv_desempleo_larga_duracion BOOLEAN,
    priv_tasa_empleo_formal BOOLEAN,
    priv_no_acceso_agua_mejorada BOOLEAN,
    priv_inadecuada_eliminacion_excretas BOOLEAN,
    priv_material_inadecuado_pisos BOOLEAN,
    priv_material_inadecuado_paredes BOOLEAN,
    priv_hacinamiento_critico BOOLEAN,
    ipm DOUBLE PRECISION NOT NULL,
    pobre BOOLEAN NOT NULL,
    fuente TEXT,
    fecha_extraccion TIMESTAMPTZ,
    fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        anio, region, departamento, personas_hogar,
        priv_bajo_logro_educativo, priv_analfabetismo,
        priv_inasistencia_escolar, priv_rezago_escolar,
        priv_atencion_primera_infancia, priv_trabajo_infantil,
        priv_no_aseguramiento_salud, priv_barreras_acceso_salud,
        priv_desempleo_larga_duracion, priv_tasa_empleo_formal,
        priv_no_acceso_agua_mejorada, priv_inadecuada_eliminacion_excretas,
        priv_material_inadecuado_pisos, priv_material_inadecuado_paredes,
        priv_hacinamiento_critico, ipm, pobre
    )
);

CREATE INDEX IF NOT EXISTS idx_dashboard_02_departamento
    ON dashboard_02 (departamento);

CREATE INDEX IF NOT EXISTS idx_dashboard_02_anio
    ON dashboard_02 (anio);

-- ==========================================================
-- Dashboard 03: Indicadores Latinoamérica
-- ==========================================================

CREATE TABLE IF NOT EXISTS contribucion_relativa_privaciones (
    anio INTEGER NOT NULL,
    privacion TEXT NOT NULL,
    pais TEXT NOT NULL,
    valor_porcentaje DOUBLE PRECISION,
    fuente TEXT,
    fecha_extraccion TIMESTAMPTZ,
    fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, privacion, pais)
);

CREATE TABLE IF NOT EXISTS poblacion_pobreza_multidimensional (
    anio INTEGER NOT NULL,
    area_geografica TEXT NOT NULL,
    pais TEXT NOT NULL,
    tipo_medida TEXT NOT NULL,
    valor_porcentaje DOUBLE PRECISION,
    fuente TEXT,
    fecha_extraccion TIMESTAMPTZ,
    fecha_carga TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (anio, area_geografica, pais, tipo_medida)
);
