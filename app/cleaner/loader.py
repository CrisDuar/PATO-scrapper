import csv
import logging

from pathlib import Path

from app.cleaner.db import get_connection, upsert_rows
from app.cleaner.schema import ALL_TABLES, ColumnSpec


logger = logging.getLogger("cleaner.loader")


def _coerce_csv_value(value: str, column: ColumnSpec):

    if value is None or value == "":
        return None

    if column.dtype == "boolean":
        return value.strip().lower() in {"true", "1"}

    if column.dtype == "int":
        return int(float(value))

    if column.dtype == "float":
        return float(value)

    return value


def read_table_csv(csv_path: Path, spec) -> list[dict]:

    if not csv_path.exists():
        return []

    with open(csv_path, "r", newline="", encoding="utf-8") as handle:

        reader = csv.DictReader(handle)

        rows = []

        for raw_row in reader:

            row = {
                column.name: _coerce_csv_value(
                    raw_row.get(column.name), column
                )
                for column in spec.columns
            }

            rows.append(row)

    return rows


def load_tables_from_dir(clean_dir: Path) -> dict:
    """
    Lee los CSV generados por clean_job_files() en `clean_dir`
    (uno por sub-tabla) y los carga a PostgreSQL con UPSERT
    idempotente por clave natural. Requiere que DATABASE_URL esté
    configurada en el .env.
    """

    mapped_tables = {
        spec.name: read_table_csv(clean_dir / f"{spec.name}.csv", spec)
        for spec in ALL_TABLES
    }

    return load_tables(mapped_tables)


def load_tables(mapped_tables: dict[str, list[dict]]) -> dict:
    """
    Carga a PostgreSQL cada sub-tabla mapeada (ver table_mapper.py),
    usando UPSERT idempotente por clave natural. Requiere que
    DATABASE_URL esté configurada en el .env.
    """

    report = {}

    conn = get_connection()

    try:

        for spec in ALL_TABLES:

            rows = mapped_tables.get(spec.name, [])

            if not rows:
                report[spec.name] = {"insertadas": 0, "rechazadas": 0}
                continue

            try:
                inserted = upsert_rows(
                    conn,
                    table_name=spec.name,
                    rows=rows,
                    natural_key=spec.natural_key,
                )

                report[spec.name] = {
                    "insertadas": inserted,
                    "rechazadas": 0,
                }

            except Exception as exc:

                conn.rollback()

                logger.error(
                    "Error cargando tabla '%s': %s",
                    spec.name,
                    exc,
                )

                report[spec.name] = {
                    "insertadas": 0,
                    "rechazadas": len(rows),
                    "error": str(exc),
                }

        unmatched = mapped_tables.get("sin_clasificar", [])

        if unmatched:

            logger.warning(
                "%s bloques quedaron sin clasificar y no se cargaron "
                "a la base de datos (revisión manual pendiente).",
                len(unmatched),
            )

            report["sin_clasificar"] = {
                "insertadas": 0,
                "rechazadas": len(unmatched),
            }

    finally:
        conn.close()

    return report
