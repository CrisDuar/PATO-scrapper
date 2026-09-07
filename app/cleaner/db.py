import logging

from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from app.config import DATABASE_URL


logger = logging.getLogger("cleaner.db")


def get_connection():

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL no está configurada. "
            "Define esa variable en el .env para poder cargar a PostgreSQL."
        )

    return psycopg2.connect(DATABASE_URL)


@contextmanager
def transaction(conn):
    """
    Envuelve un bloque de trabajo en una única transacción: hace
    commit si todo sale bien, o rollback completo si cualquier
    excepción se propaga dentro del bloque (atomicidad por job de
    carga, en vez de dejar la conexión en un estado a medio commitear).
    """

    try:
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise


def get_or_create_geographic_area(
    cursor,
    name: str,
    level: str,
) -> str:
    """
    Resuelve el id de geographic_area por (name, level); lo crea si
    no existe todavía. geographic_area no tiene una restricción
    UNIQUE de negocio, así que la deduplicación la hace la
    aplicación vía SELECT-then-INSERT dentro de la misma transacción.
    """

    cursor.execute(
        "SELECT id FROM geographic_area WHERE name = %s AND level = %s",
        (name, level),
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO geographic_area (level, name) "
        "VALUES (%s, %s) RETURNING id",
        (level, name),
    )

    return cursor.fetchone()[0]


def get_or_create_indicator(
    cursor,
    code: str,
    name: str,
    category: str,
) -> str:
    """
    Resuelve el id de indicator por su código único; lo crea si no
    existe. indicator.code sí tiene UNIQUE, así que aquí se puede
    usar ON CONFLICT de forma segura.
    """

    cursor.execute(
        """
        INSERT INTO indicator (code, name, category)
        VALUES (%s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            category = EXCLUDED.category
        RETURNING id
        """,
        (code, name, category),
    )

    return cursor.fetchone()[0]


def upsert_ipm_statistics(cursor, rows: list[dict]) -> int:
    """
    Inserta/actualiza filas de ipm_statistic, idempotente por la
    clave UNIQUE real de la tabla
    (geographic_area_id, indicator_id, period, breakdown_type,
    breakdown_value).
    """

    if not rows:
        return 0

    insert_sql = """
        INSERT INTO ipm_statistic (
            geographic_area_id, indicator_id, period,
            breakdown_type, breakdown_value,
            value, source, extracted_at
        )
        VALUES %s
        ON CONFLICT (
            geographic_area_id, indicator_id, period,
            breakdown_type, breakdown_value
        ) DO UPDATE SET
            value = EXCLUDED.value,
            source = EXCLUDED.source,
            extracted_at = EXCLUDED.extracted_at,
            loaded_at = now()
    """

    values = [
        (
            row["geographic_area_id"],
            row["indicator_id"],
            row["period"],
            row.get("breakdown_type", "none"),
            row.get("breakdown_value", "none"),
            row["value"],
            row["source"],
            row["extracted_at"],
        )
        for row in rows
    ]

    psycopg2.extras.execute_values(cursor, insert_sql, values)

    return len(rows)


def upsert_rows(
    conn,
    table_name: str,
    rows: list[dict],
    natural_key: tuple[str, ...],
) -> int:
    """
    Inserta `rows` en `table_name`, actualizando la fila existente
    cuando su clave natural (`natural_key`) ya está presente
    (UPSERT idempotente vía ON CONFLICT). Uso genérico para tablas
    planas con clave natural propia; no aplica a ipm_statistic (usa
    upsert_ipm_statistics, que resuelve las FK primero).
    """

    if not rows:
        return 0

    columns = list(rows[0].keys())

    update_columns = [
        column
        for column in columns
        if column not in natural_key
    ]

    insert_sql = (
        f'INSERT INTO {table_name} ({", ".join(columns)}) '
        f'VALUES %s '
        f'ON CONFLICT ({", ".join(natural_key)}) DO UPDATE SET '
        + ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in update_columns
        )
    )

    values = [
        tuple(row[column] for column in columns)
        for row in rows
    ]

    with conn.cursor() as cursor:

        psycopg2.extras.execute_values(
            cursor,
            insert_sql,
            values,
        )

    return len(rows)


def get_or_create_geographic_area_by_code(
    cursor,
    level: str,
    official_code: str,
    name: str,
    parent_id: str | None = None,
) -> str:
    """
    Resuelve el id de geographic_area por (level, official_code); lo
    crea si no existe. Se usa para jerarquías con código oficial DANE
    (región/departamento del microdato de hogares), separado de
    get_or_create_geographic_area (que resuelve por nombre, usado por
    el esquema estrella de dominios) porque las filas creadas por uno
    y otro camino no comparten la misma clave de búsqueda.
    """

    cursor.execute(
        "SELECT id FROM geographic_area WHERE level = %s AND official_code = %s",
        (level, official_code),
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO geographic_area (level, official_code, name, parent_id) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (level, official_code, name, parent_id),
    )

    return cursor.fetchone()[0]


def insert_household_records(
    cursor,
    rows: list[dict],
) -> list[str]:
    """
    Inserta filas nuevas en household_record en un solo batch y
    devuelve sus ids en el mismo orden de `rows`. household_record no
    tiene restricción UNIQUE — cada fila representa un perfil de
    hogar (geo + tamaño + IPM + pobre + su conjunto de privaciones)
    ya deduplicado río arriba por table_mapper._dedupe_rows usando la
    clave natural completa de dashboard_02 (que sí incluye las 15
    privaciones). Deduplicar aquí solo por
    (geographic_area_id, period, household_size, ipm_value, is_poor)
    —sin las privaciones— colapsaría hogares distintos que comparten
    esos cinco campos pero difieren en qué privaciones sufren, así
    que se inserta siempre en vez de buscar coincidencias previas;
    recargar el mismo job duplica los perfiles, igual que duplicaría
    filas en el CSV de origen si se reprocesara sin deduplicar.
    Cada dict de `rows` debe traer: geographic_area_id, period,
    household_size, ipm_value, is_poor, source, extracted_at.
    """

    if not rows:
        return []

    insert_sql = """
        INSERT INTO household_record (
            geographic_area_id, period, household_size,
            ipm_value, is_poor, source, extracted_at
        )
        VALUES %s
        RETURNING id
    """

    values = [
        (
            row["geographic_area_id"],
            row["period"],
            row["household_size"],
            row["ipm_value"],
            row["is_poor"],
            row["source"],
            row["extracted_at"],
        )
        for row in rows
    ]

    ids = psycopg2.extras.execute_values(
        cursor, insert_sql, values, fetch=True
    )

    return [row[0] for row in ids]


def upsert_household_deprivations(
    cursor,
    rows: list[dict],
) -> int:
    """
    Inserta/actualiza filas de household_deprivation, idempotente por
    la clave primaria compuesta (household_record_id, indicator_id).
    """

    if not rows:
        return 0

    insert_sql = """
        INSERT INTO household_deprivation (
            household_record_id, indicator_id, has_deprivation
        )
        VALUES %s
        ON CONFLICT (household_record_id, indicator_id) DO UPDATE SET
            has_deprivation = EXCLUDED.has_deprivation
    """

    values = [
        (
            row["household_record_id"],
            row["indicator_id"],
            row["has_deprivation"],
        )
        for row in rows
    ]

    psycopg2.extras.execute_values(cursor, insert_sql, values)

    return len(rows)
