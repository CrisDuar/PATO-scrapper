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
