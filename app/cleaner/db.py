import psycopg2
import psycopg2.extras

from app.config import DATABASE_URL


def get_connection():

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL no está configurada. "
            "Define esa variable en el .env para poder cargar a PostgreSQL."
        )

    return psycopg2.connect(DATABASE_URL)


def upsert_rows(
    conn,
    table_name: str,
    rows: list[dict],
    natural_key: tuple[str, ...],
) -> int:
    """
    Inserta `rows` en `table_name`, actualizando la fila existente
    cuando su clave natural (`natural_key`) ya está presente
    (UPSERT idempotente vía ON CONFLICT).
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

    conn.commit()

    return len(rows)
