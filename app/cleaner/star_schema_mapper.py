"""
Traduce las 3 sub-tablas planas que ya tienen vista de consulta
acordada en la base de datos (ver vw_ipm_by_domain,
vw_average_deprivations, vw_deprivations_by_variable) al esquema
estrella real (geographic_area / indicator / ipm_statistic).

Las otras 6 sub-tablas de app/cleaner/schema.py no tienen todavía
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


STAR_MAPPINGS: tuple[StarMapping, ...] = (
    IPM_POR_DOMINIO,
    PROPORCION_PRIVACIONES,
    PRIVACIONES_POR_HOGAR,
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
    period, value, source, extracted_at. Devuelve None si la fila no
    tiene los datos mínimos requeridos (geo, período o valor nulos).
    """

    geo_name = row.get(mapping.geo_column)

    period = row.get(mapping.period_column)

    value = row.get(mapping.value_column)

    if geo_name in (None, "") or period is None or value is None:
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

        indicator_category = "privation_variable"

    return {
        "geo_name": geo_name,
        "geo_level": mapping.geo_level,
        "indicator_code": indicator_code,
        "indicator_name": indicator_name,
        "indicator_category": indicator_category,
        "period": period,
        "value": value,
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
