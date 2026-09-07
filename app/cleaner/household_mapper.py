"""
Traduce la sub-tabla plana `dashboard_02` (microdato de hogares del
IPM, un perfil de hogar deduplicado por fila) al esquema normalizado
household_record / household_deprivation, según la vista de
referencia compartida por el equipo (vista de "Base de hogares", ver
docs/limpieza_datos.md).

Fuente real de los datos: BDATOS-IPM-<año>.zip, publicado con acceso
directo (sin registro) en microdatos.dane.gov.co, hoja
"HOGARES (DEPARTAMENTAL) <año>".
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorRef:
    code: str
    name: str
    category: str


# Códigos DIVIPOLA (División Político-Administrativa de Colombia),
# estándar oficial y estable del DANE — coinciden exactamente con los
# 33 códigos de DEPARTAMENTO presentes en el microdato de hogares.
DIVIPOLA_DEPARTAMENTOS: dict[str, str] = {
    "5": "Antioquia",
    "8": "Atlántico",
    "11": "Bogotá D.C.",
    "13": "Bolívar",
    "15": "Boyacá",
    "17": "Caldas",
    "18": "Caquetá",
    "19": "Cauca",
    "20": "Cesar",
    "23": "Córdoba",
    "25": "Cundinamarca",
    "27": "Chocó",
    "41": "Huila",
    "44": "La Guajira",
    "47": "Magdalena",
    "50": "Meta",
    "52": "Nariño",
    "54": "Norte de Santander",
    "63": "Quindío",
    "66": "Risaralda",
    "68": "Santander",
    "70": "Sucre",
    "73": "Tolima",
    "76": "Valle del Cauca",
    "81": "Arauca",
    "85": "Casanare",
    "86": "Putumayo",
    "88": "San Andrés, Providencia y Santa Catalina",
    "91": "Amazonas",
    "94": "Guainía",
    "95": "Guaviare",
    "97": "Vaupés",
    "99": "Vichada",
}

# "Grandes regiones" tradicionales de las encuestas de hogares del
# DANE (GEIH/pobreza monetaria y multidimensional). A diferencia de
# DIVIPOLA_DEPARTAMENTOS, esta numeración no viene documentada en el
# diccionario de variables público del microdato descargado; se deja
# explícita aquí para que el equipo la confirme/corrija si alguna
# vez se detecta un dominio mal etiquetado.
GRANDES_REGIONES: dict[str, str] = {
    "1": "Región Atlántica",
    "2": "Región Oriental",
    "3": "Región Central",
    "4": "Región Pacífica",
    "5": "Bogotá D.C.",
    "6": "Región Antioquia",
}


# indicator.code fijo por variable de privación, según la vista de
# referencia de "Base de hogares" compartida por el equipo.
# category='privation_variable', igual que privaciones_por_hogar,
# pero en un namespace de código distinto: aquí cada indicator
# describe una privación a nivel de HOGAR individual (booleano),
# mientras que privaciones_por_hogar la describe como % agregado por
# dominio/año — son entidades conceptualmente distintas aunque casi
# homónimas, así que no deben compartir el mismo indicator.code.
PRIVACION_INDICATOR_REFS: dict[str, IndicatorRef] = {
    "priv_bajo_logro_educativo": IndicatorRef(
        "BAJO_LOGRO_EDUCATIVO", "Privación por Bajo Logro Educativo", "privation_variable"
    ),
    "priv_analfabetismo": IndicatorRef(
        "ANALFABETISMO", "Privación por Analfabetismo", "privation_variable"
    ),
    "priv_inasistencia_escolar": IndicatorRef(
        "INASISTENCIA_ESCOLAR", "Privación por Inasistencia Escolar", "privation_variable"
    ),
    "priv_rezago_escolar": IndicatorRef(
        "REZAGO_ESCOLAR", "Privación por Rezago Escolar", "privation_variable"
    ),
    "priv_atencion_primera_infancia": IndicatorRef(
        "BARRERAS_A_SERVICIOS_PARA_CUIDADO_DE_LA_PRIMERA_IN",
        "Privación por Barreras a Servicios para Cuidado de la Primera Infancia",
        "privation_variable",
    ),
    "priv_trabajo_infantil": IndicatorRef(
        "TRABAJO_INFANTIL", "Privación por Trabajo Infantil", "privation_variable"
    ),
    "priv_no_aseguramiento_salud": IndicatorRef(
        "SIN_ASEGURAMIENTO_EN_SALUD", "Privación por No Aseguramiento en Salud", "privation_variable"
    ),
    "priv_barreras_acceso_salud": IndicatorRef(
        "BARRERAS_DE_ACCESO_A_SERVICIOS_DE_SALUD",
        "Privación por Barreras de Acceso a Servicios de Salud",
        "privation_variable",
    ),
    "priv_desempleo_larga_duracion": IndicatorRef(
        "DESEMPLEO_DE_LARGA_DURACION", "Privación por Desempleo de Larga Duración", "privation_variable"
    ),
    "priv_tasa_empleo_formal": IndicatorRef(
        "TRABAJO_INFORMAL", "Privación por Tasa de Empleo Formal", "privation_variable"
    ),
    "priv_no_acceso_agua_mejorada": IndicatorRef(
        "SIN_ACCESO_A_FUENTE_DE_AGUA_MEJORADA",
        "Privación por No Acceso a Fuente de Agua Mejorada",
        "privation_variable",
    ),
    "priv_inadecuada_eliminacion_excretas": IndicatorRef(
        "INADECUADA_ELIMINACION_DE_EXCRETAS",
        "Privación por Inadecuada Eliminación de Excretas",
        "privation_variable",
    ),
    "priv_material_inadecuado_pisos": IndicatorRef(
        "MATERIAL_INADECUADO_DE_PISOS", "Privación por Material Inadecuado de Pisos", "privation_variable"
    ),
    "priv_material_inadecuado_paredes": IndicatorRef(
        "MATERIAL_INADECUADO_DE_PAREDES_EXTERIORES",
        "Privación por Material Inadecuado de Paredes Exteriores",
        "privation_variable",
    ),
    "priv_hacinamiento_critico": IndicatorRef(
        "HACINAMIENTO_CRITICO", "Privación por Hacinamiento Crítico", "privation_variable"
    ),
}


def row_to_household(row: dict) -> dict | None:
    """
    Convierte una fila de `dashboard_02` en un dict con las claves
    lógicas necesarias para cargar a household_record +
    household_deprivation: region (code/name), departamento
    (code/name), period, household_size, ipm_value, is_poor,
    deprivations (lista de (indicator_code, indicator_name,
    indicator_category, has_deprivation)). Devuelve None si falta
    algún dato mínimo (departamento, período, ipm o pobre).
    """

    departamento_code = row.get("departamento")
    region_code = row.get("region")
    period = row.get("anio")
    household_size = row.get("personas_hogar")
    ipm_value = row.get("ipm")
    is_poor = row.get("pobre")

    if (
        departamento_code is None
        or period is None
        or ipm_value is None
        or is_poor is None
    ):
        return None

    departamento_code = str(int(departamento_code))
    region_code = str(int(region_code)) if region_code is not None else None

    departamento_name = DIVIPOLA_DEPARTAMENTOS.get(
        departamento_code,
        f"Departamento {departamento_code}",
    )

    region_name = (
        GRANDES_REGIONES.get(region_code, f"Región {region_code}")
        if region_code is not None
        else None
    )

    deprivations = []

    for column_name, indicator_ref in PRIVACION_INDICATOR_REFS.items():

        has_deprivation = row.get(column_name)

        if has_deprivation is None:
            continue

        deprivations.append(
            {
                "indicator_code": indicator_ref.code,
                "indicator_name": indicator_ref.name,
                "indicator_category": indicator_ref.category,
                "has_deprivation": bool(has_deprivation),
            }
        )

    return {
        "region_code": region_code,
        "region_name": region_name,
        "departamento_code": departamento_code,
        "departamento_name": departamento_name,
        "period": period,
        "household_size": household_size,
        "ipm_value": ipm_value,
        "is_poor": bool(is_poor),
        "deprivations": deprivations,
        "source": row.get("fuente"),
        "extracted_at": row.get("fecha_extraccion"),
    }
