from app.cleaner.block_extractor import DataBlock


DASHBOARD_01 = "Dashboard_01"
DASHBOARD_02 = "Dashboard_02"
DASHBOARD_03 = "Dashboard_03"
SIN_CLASIFICAR = "Sin_Clasificar"


DEPARTAMENTO_KEYS = {"departamento", "region"}

PAIS_KEYS = {"pais", "area_geografica"}

DOMINIO_KEYS = {"dominio"}


def classify_block(block: DataBlock) -> str:
    """
    Decide a qué hoja del formato estándar pertenece un bloque,
    a partir de las columnas que contiene:

    - Dashboard_01: indicadores nacionales/por dominio (Colombia).
    - Dashboard_02: indicadores a nivel departamental (Colombia).
    - Dashboard_03: indicadores comparativos entre países (Latam).
    """

    header_keys = set(
        block.extra.get("header_keys", [])
    )

    if header_keys & PAIS_KEYS:
        return DASHBOARD_03

    if header_keys & DEPARTAMENTO_KEYS:
        return DASHBOARD_02

    if header_keys & DOMINIO_KEYS:
        return DASHBOARD_01

    return SIN_CLASIFICAR


def classify_blocks(
    blocks: list[DataBlock],
) -> dict[str, list[DataBlock]]:

    grouped: dict[str, list[DataBlock]] = {
        DASHBOARD_01: [],
        DASHBOARD_02: [],
        DASHBOARD_03: [],
        SIN_CLASIFICAR: [],
    }

    for block in blocks:

        sheet = classify_block(block)

        grouped[sheet].append(block)

    return grouped
