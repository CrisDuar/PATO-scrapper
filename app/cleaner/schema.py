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
    header_key_aliases={"valor": "ipm"},
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
    header_key_aliases={"valor": "ipm", "indicador": "variable"},
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
    header_key_aliases={"valor": "porcentaje"},
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
    required_header_keys=("dominio", "sexo_jefe_hogar", "porcentaje"),
    header_key_aliases={
        "sexo_jefe_hogar": "sexo",
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
    natural_key=(
        "anio",
        "region",
        "departamento",
        "personas_hogar",
        *PRIVACION_COLUMNS,
        "ipm",
        "pobre",
    ),
    required_header_keys=("anio", "region", "departamento", "ipm", "pobre"),
    header_key_aliases={},
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
    header_key_aliases={"valor": "valor_porcentaje"},
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
    header_key_aliases={"valor": "valor_porcentaje"},
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
