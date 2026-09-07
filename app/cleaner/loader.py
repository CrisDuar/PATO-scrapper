import csv
import json
import logging

from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from app.cleaner.db import (
    get_connection,
    get_or_create_geographic_area,
    get_or_create_geographic_area_by_code,
    get_or_create_indicator,
    insert_household_records,
    transaction,
    upsert_household_deprivations,
    upsert_ipm_statistics,
)
from app.cleaner.household_mapper import row_to_household
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

# dashboard_02 no se carga al esquema estrella (geographic_area /
# indicator / ipm_statistic) sino al esquema normalizado de
# microdato: household_record / household_deprivation (ver
# household_mapper.py y la vista de referencia "Base de hogares").
HOUSEHOLD_TABLE = "dashboard_02"


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

                report[HOUSEHOLD_TABLE] = _load_household_table(
                    cursor,
                    mapped_tables.get(HOUSEHOLD_TABLE, []),
                )

        for spec in ALL_TABLES:

            if spec.name in LOADABLE_TABLES or spec.name == HOUSEHOLD_TABLE:
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
            for table_name in (*LOADABLE_TABLES, HOUSEHOLD_TABLE)
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


def _load_household_table(cursor, rows: list[dict]) -> dict:
    """
    Carga dashboard_02 (perfiles de hogar del microdato del DANE) al
    esquema normalizado household_record / household_deprivation. A
    diferencia de _load_table, cada fila requiere resolver dos
    niveles de geographic_area (región -> departamento, vía
    parent_id) y produce N filas de household_deprivation por hogar
    (una por variable de privación presente).

    Solo hay 39 áreas geográficas posibles (6 regiones + 33
    departamentos) y 15 indicadores de privación fijos, así que se
    resuelven una sola vez y se cachean en memoria — sin esto, un
    archivo de ~18.700 hogares dispara cientos de miles de
    round-trips redundantes a la base de datos (uno por privación por
    hogar) para resolver siempre los mismos 15 códigos.
    """

    if not rows:
        return {"insertadas": 0, "rechazadas": 0}

    rejected = 0

    geo_cache: dict[tuple[str, str], str] = {}

    indicator_cache: dict[str, str] = {}

    households: list[dict] = []

    for row in rows:

        household = row_to_household(row)

        if household is None:
            rejected += 1
            continue

        households.append(household)

    # Fase 1: resolver geographic_area (región/departamento) e
    # indicator una sola vez por código distinto, no por hogar.
    for household in households:

        region_id = None

        if household["region_code"] is not None:

            region_key = ("region", household["region_code"])

            region_id = geo_cache.get(region_key)

            if region_id is None:

                region_id = get_or_create_geographic_area_by_code(
                    cursor,
                    level="region",
                    official_code=household["region_code"],
                    name=household["region_name"],
                )

                geo_cache[region_key] = region_id

        departamento_key = ("departamento", household["departamento_code"])

        departamento_id = geo_cache.get(departamento_key)

        if departamento_id is None:

            departamento_id = get_or_create_geographic_area_by_code(
                cursor,
                level="departamento",
                official_code=household["departamento_code"],
                name=household["departamento_name"],
                parent_id=region_id,
            )

            geo_cache[departamento_key] = departamento_id

        household["_geographic_area_id"] = departamento_id

        for deprivation in household["deprivations"]:

            indicator_code = deprivation["indicator_code"]

            if indicator_code in indicator_cache:
                continue

            indicator_cache[indicator_code] = get_or_create_indicator(
                cursor,
                code=indicator_code,
                name=deprivation["indicator_name"],
                category=deprivation["indicator_category"],
            )

    # Fase 2: insertar todos los household_record en un solo batch
    # (sin buscar coincidencias previas, ver insert_household_records)
    # y usar los ids devueltos, en el mismo orden, para construir las
    # filas de household_deprivation.
    household_record_ids = insert_household_records(
        cursor,
        [
            {
                "geographic_area_id": household["_geographic_area_id"],
                "period": household["period"],
                "household_size": household["household_size"],
                "ipm_value": household["ipm_value"],
                "is_poor": household["is_poor"],
                "source": household["source"],
                "extracted_at": household["extracted_at"],
            }
            for household in households
        ],
    )

    all_deprivation_rows = [
        {
            "household_record_id": household_record_id,
            "indicator_id": indicator_cache[deprivation["indicator_code"]],
            "has_deprivation": deprivation["has_deprivation"],
        }
        for household, household_record_id in zip(households, household_record_ids)
        for deprivation in household["deprivations"]
    ]

    inserted_deprivations = upsert_household_deprivations(
        cursor, all_deprivation_rows
    )

    return {
        "insertadas": len(household_record_ids),
        "rechazadas": rejected,
        "privaciones_insertadas": inserted_deprivations,
    }


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
