"""
Traduce las sub-tablas planas que ya tienen vista de consulta
acordada en la base de datos (ver vw_ipm_by_domain,
vw_average_deprivations, vw_deprivations_by_variable,
vw_dimension_contribution, vw_incidence_by_household_head_sex,
vw_incidence_by_person_sex) al esquema estrella real
(geographic_area / indicator / ipm_statistic).

Las sub-tablas restantes de app/cleaner/schema.py no tienen todavía
una convención de indicator.code acordada con el equipo, así que se
excluyen de la carga a PostgreSQL (siguen disponibles como CSV/Excel).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorRef:
    code: str
    name: str
    category: str


@dataclass(frozen=True)
class StarMapping:
    """
    Describe cómo traducir una sub-tabla plana a filas de
    ipm_statistic: qué columna trae el nombre del área geográfica,
    cuál el período, cuál el valor, y cómo resolver el indicador
    (fijo o derivado de una columna, p.ej. una fila por variable).
    """

    table_name: str
    geo_column: str
    geo_level: str
    period_column: str
    value_column: str
    indicator: IndicatorRef | None
    indicator_from_column: str | None = None
    # category asignada al indicator generado cuando indicator_from_column
    # está en uso (indicator es None). Ignorada si indicator no es None.
    indicator_category_from_column: str = "privation_variable"
    # Nombre fijo de breakdown_type para esta tabla ('none' si la
    # vista de referencia no desagrega por ninguna característica).
    breakdown_type: str = "none"
    # Columna de origen que trae el valor de breakdown_value (p. ej.
    # 'dimension' o 'sexo'); None cuando breakdown_type es 'none'.
    breakdown_value_column: str | None = None


# indicator.code = 'MPI' y breakdown_type = 'none', según
# vw_ipm_by_domain.
IPM_POR_DOMINIO = StarMapping(
    table_name="ipm_por_dominio",
    geo_column="dominio",
    geo_level="dominio",
    period_column="anio",
    value_column="ipm",
    indicator=IndicatorRef(
        code="MPI",
        name="Índice de Pobreza Multidimensional",
        category="mpi",
    ),
)

# indicator.code = 'INTENSITY_A' y breakdown_type = 'none', según
# vw_average_deprivations.
PROPORCION_PRIVACIONES = StarMapping(
    table_name="proporcion_privaciones",
    geo_column="dominio",
    geo_level="dominio",
    period_column="anio",
    value_column="porcentaje",
    indicator=IndicatorRef(
        code="INTENSITY_A",
        name="Intensidad promedio de privaciones",
        category="intensity",
    ),
)

# Un indicator por variable (category='privation_variable') y
# breakdown_type = 'none', según vw_deprivations_by_variable.
PRIVACIONES_POR_HOGAR = StarMapping(
    table_name="privaciones_por_hogar",
    geo_column="dominio",
    geo_level="dominio",
    period_column="anio",
    value_column="ipm",
    indicator=None,
    indicator_from_column="variable",
)


# indicator.category = 'dimension' (un indicator por dimensión) y
# breakdown_type = 'none', según vw_dimension_contribution (vista 3).
CONTRIBUCIONES_INCIDENCIA = StarMapping(
    table_name="contribuciones_incidencia",
    geo_column="dominio",
    geo_level="dominio",
    period_column="anio",
    value_column="porcentaje",
    indicator=None,
    indicator_from_column="dimension",
    indicator_category_from_column="dimension",
)

# indicator.code = 'MPI' y breakdown_type = 'household_head_sex',
# según vw_incidence_by_household_head_sex (vista 4).
INCIDENCIA_POR_SEXO_JEFE_HOGAR = StarMapping(
    table_name="incidencia_por_sexo_jefe_hogar",
    geo_column="dominio",
    geo_level="dominio",
    period_column="anio",
    value_column="porcentaje",
    indicator=IndicatorRef(
        code="MPI",
        name="Índice de Pobreza Multidimensional",
        category="mpi",
    ),
    breakdown_type="household_head_sex",
    breakdown_value_column="sexo",
)

# indicator.code = 'MPI' y breakdown_type = 'person_sex', según
# vw_incidence_by_person_sex (vista 5).
INCIDENCIA_POR_SEXO_PERSONA = StarMapping(
    table_name="incidencia_por_sexo_persona",
    geo_column="dominio",
    geo_level="dominio",
    period_column="anio",
    value_column="porcentaje",
    indicator=IndicatorRef(
        code="MPI",
        name="Índice de Pobreza Multidimensional",
        category="mpi",
    ),
    breakdown_type="person_sex",
    breakdown_value_column="sexo",
)


STAR_MAPPINGS: tuple[StarMapping, ...] = (
    IPM_POR_DOMINIO,
    PROPORCION_PRIVACIONES,
    PRIVACIONES_POR_HOGAR,
    CONTRIBUCIONES_INCIDENCIA,
    INCIDENCIA_POR_SEXO_JEFE_HOGAR,
    INCIDENCIA_POR_SEXO_PERSONA,
)


def get_star_mapping(table_name: str) -> StarMapping | None:

    for mapping in STAR_MAPPINGS:

        if mapping.table_name == table_name:
            return mapping

    return None


def row_to_statistic(row: dict, mapping: StarMapping) -> dict | None:
    """
    Convierte una fila de sub-tabla plana en un dict con las claves
    lógicas necesarias para cargar a ipm_statistic: geo_name,
    geo_level, indicator_code, indicator_name, indicator_category,
    period, value, breakdown_type, breakdown_value, source,
    extracted_at. Devuelve None si la fila no tiene los datos mínimos
    requeridos (geo, período, valor o breakdown_value nulos).
    """

    geo_name = row.get(mapping.geo_column)

    period = row.get(mapping.period_column)

    value = row.get(mapping.value_column)

    if geo_name in (None, "") or period is None or value is None:
        return None

    breakdown_value = "none"

    if mapping.breakdown_value_column is not None:

        breakdown_value = row.get(mapping.breakdown_value_column)

        if breakdown_value in (None, ""):
            return None

    if mapping.indicator is not None:

        indicator_code = mapping.indicator.code

        indicator_name = mapping.indicator.name

        indicator_category = mapping.indicator.category

    else:

        variable = row.get(mapping.indicator_from_column)

        if variable in (None, ""):
            return None

        indicator_code = _slug_indicator_code(variable)

        indicator_name = variable

        indicator_category = mapping.indicator_category_from_column

    return {
        "geo_name": geo_name,
        "geo_level": mapping.geo_level,
        "indicator_code": indicator_code,
        "indicator_name": indicator_name,
        "indicator_category": indicator_category,
        "period": period,
        "value": value,
        "breakdown_type": mapping.breakdown_type,
        "breakdown_value": breakdown_value,
        "source": row.get("fuente"),
        "extracted_at": row.get("fecha_extraccion"),
    }


INDICATOR_CODE_MAX_LENGTH = 50


def _slug_indicator_code(variable: str) -> str:
    """
    indicator.code es varchar(50), así que el slug se trunca a ese
    límite de forma determinística (mismo texto de entrada siempre
    produce el mismo code, preservando el UPSERT idempotente).
    """

    import re
    import unicodedata

    text = str(variable).strip().upper()

    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )

    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")

    return text[:INDICATOR_CODE_MAX_LENGTH]
