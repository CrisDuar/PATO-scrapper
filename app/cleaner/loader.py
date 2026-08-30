import csv
import json
import logging

from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from app.cleaner.db import (
    get_connection,
    get_or_create_geographic_area,
    get_or_create_indicator,
    transaction,
    upsert_ipm_statistics,
)
from app.cleaner.schema import ALL_TABLES, ColumnSpec
from app.cleaner.star_schema_mapper import get_star_mapping, row_to_statistic


logger = logging.getLogger("cleaner.loader")

LOG_FILE_NAME = "carga_log.json"

# Solo estas sub-tablas tienen una convención de indicator.code
# acordada con el equipo (ver vw_ipm_by_domain, vw_average_deprivations,
# vw_deprivations_by_variable, vw_incidence_by_dimension,
# vw_incidence_by_household_head_sex, vw_incidence_by_person_sex). El
# resto se sigue exportando a CSV/Excel pero no se carga a PostgreSQL
# hasta que se defina su mapeo.
LOADABLE_TABLES = (
    "ipm_por_dominio",
    "proporcion_privaciones",
    "privaciones_por_hogar",
    "contribuciones_incidencia",
    "incidencia_por_sexo_jefe_hogar",
    "incidencia_por_sexo_persona",
)


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

            row["fuente"] = raw_row.get("fuente")
            row["fecha_extraccion"] = raw_row.get("fecha_extraccion")

            rows.append(row)

    return rows


def load_tables_from_dir(clean_dir: Path, job_id: str | None = None) -> dict:
    """
    Lee los CSV generados por clean_job_files() en `clean_dir`
    (uno por sub-tabla) y carga a PostgreSQL las sub-tablas que ya
    tienen mapeo acordado al esquema estrella (LOADABLE_TABLES),
    usando UPSERT idempotente. Requiere que DATABASE_URL esté
    configurada en el .env. Registra el resultado en
    <clean_dir>/carga_log.json.
    """

    mapped_tables = {
        spec.name: read_table_csv(clean_dir / f"{spec.name}.csv", spec)
        for spec in ALL_TABLES
    }

    report = load_tables(mapped_tables)

    _write_load_log(clean_dir, job_id, report)

    return report


def load_tables(mapped_tables: dict[str, list[dict]]) -> dict:
    """
    Carga a PostgreSQL las sub-tablas con mapeo definido al esquema
    estrella (geographic_area / indicator / ipm_statistic), todo
    dentro de una única transacción: si una tabla falla, se revierte
    toda la carga del job (atomicidad), evitando estados parciales
    en la base de datos compartida. Requiere que DATABASE_URL esté
    configurada en el .env.
    """

    report = {}

    conn = get_connection()

    try:

        with transaction(conn):

            with conn.cursor() as cursor:

                for table_name in LOADABLE_TABLES:

                    rows = mapped_tables.get(table_name, [])

                    report[table_name] = _load_table(cursor, table_name, rows)

        for spec in ALL_TABLES:

            if spec.name in LOADABLE_TABLES:
                continue

            rows = mapped_tables.get(spec.name, [])

            report[spec.name] = {
                "insertadas": 0,
                "rechazadas": 0,
                "omitidas": len(rows),
                "motivo": (
                    "Sin mapeo acordado al esquema de PostgreSQL; "
                    "disponible solo en el CSV/Excel exportado."
                ),
            }

    except (psycopg2.Error, RuntimeError) as exc:

        logger.error("Error cargando el job a PostgreSQL: %s", exc)

        report = {
            table_name: {
                "insertadas": 0,
                "rechazadas": len(mapped_tables.get(table_name, [])),
                "error": str(exc),
            }
            for table_name in LOADABLE_TABLES
        }

    finally:
        conn.close()

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

    return report


def _load_table(cursor, table_name: str, rows: list[dict]) -> dict:

    if not rows:
        return {"insertadas": 0, "rechazadas": 0}

    mapping = get_star_mapping(table_name)

    if mapping is None:
        return {
            "insertadas": 0,
            "rechazadas": len(rows),
            "error": f"No hay mapeo de esquema estrella para '{table_name}'.",
        }

    statistics = []

    rejected = 0

    for row in rows:

        statistic = row_to_statistic(row, mapping)

        if statistic is None:
            rejected += 1
            continue

        statistics.append(statistic)

    resolved_rows = []

    for statistic in statistics:

        geo_id = get_or_create_geographic_area(
            cursor,
            name=statistic["geo_name"],
            level=statistic["geo_level"],
        )

        indicator_id = get_or_create_indicator(
            cursor,
            code=statistic["indicator_code"],
            name=statistic["indicator_name"],
            category=statistic["indicator_category"],
        )

        resolved_rows.append(
            {
                "geographic_area_id": geo_id,
                "indicator_id": indicator_id,
                "period": statistic["period"],
                "value": statistic["value"],
                "breakdown_type": statistic["breakdown_type"],
                "breakdown_value": statistic["breakdown_value"],
                "source": statistic["source"],
                "extracted_at": statistic["extracted_at"],
            }
        )

    inserted = upsert_ipm_statistics(cursor, resolved_rows)

    return {"insertadas": inserted, "rechazadas": rejected}


def _write_load_log(clean_dir: Path, job_id: str | None, report: dict) -> Path:
    """
    Registra el resultado de la carga en <clean_dir>/carga_log.json,
    acumulando un historial de intentos (uno por ejecución) para que
    quede auditoría local de cuántas filas se insertaron/rechazaron
    y qué errores ocurrieron en cada carga del job.
    """

    log_path = clean_dir / LOG_FILE_NAME

    history = []

    if log_path.exists():

        try:
            history = json.loads(log_path.read_text(encoding="utf-8"))

        except (json.JSONDecodeError, OSError):
            history = []

    total_insertadas = sum(
        table_report.get("insertadas", 0) for table_report in report.values()
    )

    total_rechazadas = sum(
        table_report.get("rechazadas", 0) for table_report in report.values()
    )

    entry = {
        "job_id": job_id,
        "fecha_carga": datetime.now(timezone.utc).isoformat(),
        "total_insertadas": total_insertadas,
        "total_rechazadas": total_rechazadas,
        "exito": total_rechazadas == 0
        and not any("error" in table_report for table_report in report.values()),
        "detalle": report,
    }

    history.append(entry)

    log_path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return log_path
