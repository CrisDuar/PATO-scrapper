from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    dtype: str  # "int" | "float" | "text" | "boolean"


@dataclass(frozen=True)
class TableSpec:
    name: str
    dashboard: str
    columns: tuple[ColumnSpec, ...]
    natural_key: tuple[str, ...]
    # header_keys (slugificados) que deben estar presentes en el
    # bloque de origen para que se reconozca como esta sub-tabla.
    required_header_keys: tuple[str, ...]
    # Mapea header_key de origen -> nombre de columna destino,
    # para los casos en que el nombre de origen difiere del destino.
    header_key_aliases: dict[str, str]


PRIVACION_COLUMNS = (
    "priv_bajo_logro_educativo",
    "priv_analfabetismo",
    "priv_inasistencia_escolar",
    "priv_rezago_escolar",
    "priv_atencion_primera_infancia",
    "priv_trabajo_infantil",
    "priv_no_aseguramiento_salud",
    "priv_barreras_acceso_salud",
    "priv_desempleo_larga_duracion",
    "priv_tasa_empleo_formal",
    "priv_no_acceso_agua_mejorada",
    "priv_inadecuada_eliminacion_excretas",
    "priv_material_inadecuado_pisos",
    "priv_material_inadecuado_paredes",
    "priv_hacinamiento_critico",
)


IPM_POR_DOMINIO = TableSpec(
    name="ipm_por_dominio",
    dashboard="dashboard_01",
    columns=(
        ColumnSpec("anio", "int"),
        ColumnSpec("dominio", "text"),
        ColumnSpec("ipm", "float"),
    ),
    natural_key=("anio", "dominio"),
    required_header_keys=("anio", "dominio", "ipm"),
    header_key_aliases={
        "ano": "anio",
        "valor": "ipm",
        "principales_dominios": "dominio",
        "regiones": "dominio",
    },
)

PRIVACIONES_POR_HOGAR = TableSpec(
    name="privaciones_por_hogar",
    dashboard="dashboard_01",
    columns=(
        ColumnSpec("anio", "int"),
        ColumnSpec("dominio", "text"),
        ColumnSpec("variable", "text"),
        ColumnSpec("ipm", "float"),
    ),
    natural_key=("anio", "dominio", "variable"),
    required_header_keys=("anio", "dominio", "variable", "ipm"),
    header_key_aliases={"ano": "anio", "valor": "ipm", "indicador": "variable"},
)

PROPORCION_PRIVACIONES = TableSpec(
    name="proporcion_privaciones",
    dashboard="dashboard_01",
    columns=(
        ColumnSpec("anio", "int"),
        ColumnSpec("dominio", "text"),
        ColumnSpec("porcentaje", "float"),
    ),
    natural_key=("anio", "dominio"),
    required_header_keys=("anio", "dominio", "porcentaje"),
    header_key_aliases={
        "ano": "anio",
        "valor": "porcentaje",
        "principales_dominios": "dominio",
        "regiones": "dominio",
    },
)

CONTRIBUCIONES_INCIDENCIA = TableSpec(
    name="contribuciones_incidencia",
    dashboard="dashboard_01",
    columns=(
        ColumnSpec("anio", "int"),
        ColumnSpec("dominio", "text"),
        ColumnSpec("dimension", "text"),
        ColumnSpec("porcentaje", "float"),
    ),
    natural_key=("anio", "dominio", "dimension"),
    required_header_keys=("dominio", "dimension", "porcentaje"),
    header_key_aliases={
        "ano": "anio",
        "valor": "porcentaje",
        "principales_dominios": "dominio",
        "regiones": "dominio",
    },
)

INCIDENCIA_POR_SEXO_PERSONA = TableSpec(
    name="incidencia_por_sexo_persona",
    dashboard="dashboard_01",
    columns=(
        ColumnSpec("anio", "int"),
        ColumnSpec("dominio", "text"),
        ColumnSpec("sexo", "text"),
        ColumnSpec("porcentaje", "float"),
    ),
    natural_key=("anio", "dominio", "sexo"),
    required_header_keys=("dominio", "sexo_persona", "porcentaje"),
    header_key_aliases={
        "ano": "anio",
        "sexo_persona": "sexo",
        "valor": "porcentaje",
        "principales_dominios": "dominio",
        "regiones": "dominio",
    },
)

INCIDENCIA_POR_SEXO_JEFE_HOGAR = TableSpec(
    name="incidencia_por_sexo_jefe_hogar",
    dashboard="dashboard_01",
    columns=(
        ColumnSpec("anio", "int"),
        ColumnSpec("dominio", "text"),
        ColumnSpec("sexo", "text"),
        ColumnSpec("porcentaje", "float"),
    ),
    natural_key=("anio", "dominio", "sexo"),
    required_header_keys=("dominio", "sexo", "porcentaje"),
    header_key_aliases={
        "ano": "anio",
        "sexo_jefe_hogar": "sexo",
        "sexo_persona": "sexo",
        "valor": "porcentaje",
        "principales_dominios": "dominio",
        "regiones": "dominio",
    },
)


DASHBOARD_02_HOGARES = TableSpec(
    name="dashboard_02",
    dashboard="dashboard_02",
    columns=(
        ColumnSpec("anio", "int"),
        ColumnSpec("region", "int"),
        ColumnSpec("departamento", "int"),
        ColumnSpec("personas_hogar", "int"),
        *(ColumnSpec(col, "boolean") for col in PRIVACION_COLUMNS),
        ColumnSpec("ipm", "float"),
        ColumnSpec("pobre", "boolean"),
    ),
    # "region" queda fuera de la clave natural (a diferencia de
    # "departamento") porque el microdato 2024 no la trae: si
    # estuviera aquí, _dedupe_rows descartaría todas sus filas por
    # tener ese campo en None.
    natural_key=(
        "anio",
        "departamento",
        "personas_hogar",
        *PRIVACION_COLUMNS,
        "ipm",
        "pobre",
    ),
    # "region" no está en required_header_keys porque el microdato
    # 2024 solo trae DEPARTAMENTO (sin desagregación de región); ver
    # household_mapper.row_to_household, que ya maneja region_code=None.
    required_header_keys=("departamento", "ipm", "pobre"),
    header_key_aliases={
        # Encabezados reales del microdato de hogares del DANE
        # (BDATOS-IPM-<año>.zip, hoja "HOGARES (DEPARTAMENTAL) <año>"),
        # publicado en microdatos.dane.gov.co. No trae columna de año
        # confiable (PERIODO viene casi siempre en NA); el año se
        # infiere del título del bloque/archivo, igual que en
        # contribuciones_incidencia.
        "ano": "anio",
        "personas": "personas_hogar",
        "logro_educativo": "priv_bajo_logro_educativo",
        "analfabetismo": "priv_analfabetismo",
        # "alfabetismo" (sin el prefijo "an-") es como el DANE nombró
        # esta misma variable en los microdatos de hogares 2010-2023;
        # a partir de 2024 el campo se llama "analfabetismo".
        "alfabetismo": "priv_analfabetismo",
        "inasistencia_escolar": "priv_inasistencia_escolar",
        # Typo de origen en el microdato 2024 ("inansistencia").
        "inansistencia_escolar": "priv_inasistencia_escolar",
        "rezago_escolar": "priv_rezago_escolar",
        "atencion_integral": "priv_atencion_primera_infancia",
        "trabajo_infantil": "priv_trabajo_infantil",
        "aseguramiento_salud": "priv_no_aseguramiento_salud",
        "barreras_acceso_salud": "priv_barreras_acceso_salud",
        "desempleo_larga_duracion": "priv_desempleo_larga_duracion",
        "empleo_formal": "priv_tasa_empleo_formal",
        "acueducto": "priv_no_acceso_agua_mejorada",
        "alcantarillado": "priv_inadecuada_eliminacion_excretas",
        "pisos": "priv_material_inadecuado_pisos",
        "paredes": "priv_material_inadecuado_paredes",
        "hacinamiento": "priv_hacinamiento_critico",
        # Alias heredados por si algún anexo publica encabezados en
        # español largo en vez de los nombres cortos del microdato.
        "privacion_por_bajo_logro_educativo": "priv_bajo_logro_educativo",
        "privacion_por_analfabetismo": "priv_analfabetismo",
        "privacion_por_inasistencia_escolar": "priv_inasistencia_escolar",
        "privacion_por_rezago_escolar": "priv_rezago_escolar",
        "privacion_por_atencion_integral_a_la_primera_infancia": "priv_atencion_primera_infancia",
        "privacion_por_trabajo_infantil": "priv_trabajo_infantil",
        "privacion_por_no_aseguramiento_en_salud": "priv_no_aseguramiento_salud",
        "privacion_por_barreras_de_acceso_a_salud": "priv_barreras_acceso_salud",
        "privacion_por_desempleo_de_larga_duracion": "priv_desempleo_larga_duracion",
        "privacion_por_tasa_de_empleo_formal": "priv_tasa_empleo_formal",
        "privacion_por_no_acceso_a_fuente_de_agua_mejorada": "priv_no_acceso_agua_mejorada",
        "privacion_por_inadecuada_eliminacion_de_excretas": "priv_inadecuada_eliminacion_excretas",
        "privacion_por_inadecuado_material_de_pisos": "priv_material_inadecuado_pisos",
        "privacion_por_inadecuado_material_de_paredes_exteriores": "priv_material_inadecuado_paredes",
        "privacion_por_hacinamiento_critico": "priv_hacinamiento_critico",
        "personas_que_habitan_ese_hogar": "personas_hogar",
    },
)


CONTRIBUCION_RELATIVA_PRIVACIONES = TableSpec(
    name="contribucion_relativa_privaciones",
    dashboard="dashboard_03",
    columns=(
        ColumnSpec("anio", "int"),
        ColumnSpec("privacion", "text"),
        ColumnSpec("pais", "text"),
        ColumnSpec("valor_porcentaje", "float"),
    ),
    natural_key=("anio", "privacion", "pais"),
    required_header_keys=("anio", "privacion", "pais", "valor_porcentaje"),
    header_key_aliases={"ano": "anio", "valor": "valor_porcentaje"},
)

POBLACION_POBREZA_MULTIDIMENSIONAL = TableSpec(
    name="poblacion_pobreza_multidimensional",
    dashboard="dashboard_03",
    columns=(
        ColumnSpec("anio", "int"),
        ColumnSpec("area_geografica", "text"),
        ColumnSpec("pais", "text"),
        ColumnSpec("tipo_medida", "text"),
        ColumnSpec("valor_porcentaje", "float"),
    ),
    natural_key=("anio", "area_geografica", "pais", "tipo_medida"),
    required_header_keys=(
        "anio",
        "area_geografica",
        "pais",
        "tipo_medida",
        "valor_porcentaje",
    ),
    header_key_aliases={"ano": "anio", "valor": "valor_porcentaje"},
)


ALL_TABLES: tuple[TableSpec, ...] = (
    IPM_POR_DOMINIO,
    PRIVACIONES_POR_HOGAR,
    PROPORCION_PRIVACIONES,
    CONTRIBUCIONES_INCIDENCIA,
    INCIDENCIA_POR_SEXO_PERSONA,
    INCIDENCIA_POR_SEXO_JEFE_HOGAR,
    DASHBOARD_02_HOGARES,
    CONTRIBUCION_RELATIVA_PRIVACIONES,
    POBLACION_POBREZA_MULTIDIMENSIONAL,
)


def get_table_spec(name: str) -> TableSpec:

    for spec in ALL_TABLES:

        if spec.name == name:
            return spec

    raise KeyError(f"No existe la tabla '{name}'")
