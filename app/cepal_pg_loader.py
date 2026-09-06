
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from urllib.parse import urlparse, unquote, parse_qsl

import psycopg2
from psycopg2.extras import execute_values

from app.cepal_dimensions_export import (
    build_records,
    CepalDimensionsError,
)


class CepalLoadError(Exception):
    """Error al cargar datos de CEPALSTAT a PostgreSQL."""

INDICATOR_TABLE_CONFIG: dict[int, dict[str, Any]] = {
    5554: {
        "table": "cepal_deprivation_contribution",
        "dimension_map": {
            "Country__ESTANDAR": "country",
            "Years__ESTANDAR": "period",
            "Deprivation": "deprivation",
        },
    },
    4079: {
        "table": "cepal_poverty_measure",
        "dimension_map": {
            "Country__ESTANDAR": "country",
            "Geographical area": "geographical_area",
            "Years__ESTANDAR": "period",
            "Multidimensional poverty measures": "measure",
        },
    },
}


_INTEGER_COLUMNS = {"period"}


def _get_connection():

    dsn = os.environ.get("DATABASE_URL")

    if not dsn:

        raise CepalLoadError(
            "DATABASE_URL no está configurada. Definila en tu .env antes "
            "de cargar datos a PostgreSQL."
        )


    try:
        parsed = urlparse(dsn)

        if parsed.scheme not in ("postgresql", "postgres"):
            raise ValueError(
                f"esquema '{parsed.scheme}' inválido (debe ser "
                "postgresql:// o postgres://)"
            )

        port = parsed.port  # esto ya valida que sea un entero
        host = parsed.hostname
        dbname = parsed.path.lstrip("/")

        if not host or not dbname:
            raise ValueError("falta el host o el nombre de la base de datos")

        conn_kwargs = {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": unquote(parsed.username) if parsed.username else None,
            "password": unquote(parsed.password) if parsed.password else None,
        }

        conn_kwargs.update(dict(parse_qsl(parsed.query)))

    except ValueError as exc:


        safe_dsn = dsn
        if parsed.password:
            safe_dsn = dsn.replace(parsed.password, "***")

        raise CepalLoadError(
            f"DATABASE_URL no es una cadena de conexión válida: {exc}. "
            f"Valor recibido (password oculto): {safe_dsn!r}. "
            "Formato esperado: "
            "postgresql://usuario:password@host:puerto/basededatos -- si "
            "tu password tiene @, :, / u otros caracteres especiales, deben "
            "ir URL-encoded (por ejemplo @ -> %40, : -> %3A)."
        ) from exc

    try:
        return psycopg2.connect(**conn_kwargs)

    except psycopg2.OperationalError as exc:

        raise CepalLoadError(
            f"No se pudo conectar a PostgreSQL en {host}:{port}/{dbname}: "
            f"{exc}"
        ) from exc


def _clean_optional(value: Any) -> Any:


    if value is None:
        return None

    if isinstance(value, str) and value.strip() == "":
        return None

    return value


def _build_rows_for_indicator(
    indicator_id: int,
) -> tuple[list[str], list[tuple]]:


    config = INDICATOR_TABLE_CONFIG.get(indicator_id)

    if config is None:

        raise CepalLoadError(
            f"El indicador {indicator_id} no tiene una configuración de "
            f"carga definida. Indicadores soportados: "
            f"{list(INDICATOR_TABLE_CONFIG)}"
        )

    dimension_map: dict[str, str] = config["dimension_map"]

    try:
        records = build_records(indicator_id)

    except CepalDimensionsError as exc:

        raise CepalLoadError(str(exc)) from exc

    if not records:

        raise CepalLoadError(
            f"El indicador {indicator_id} no devolvió datos."
        )

    # Si CEPALSTAT cambia el nombre de alguna dimensión, mejor fallar fuerte
    # que insertar filas con columnas en NULL silenciosamente.
    dimensiones_disponibles = [
        k for k in records[0]
        if k not in ("value", "source_id", "notes_ids", "iso3")
    ]

    faltantes = [
        dim_name
        for dim_name in dimension_map
        if dim_name not in records[0]
    ]

    if faltantes:

        raise CepalLoadError(
            f"El indicador {indicator_id} no trae las dimensiones "
            f"esperadas {faltantes}. Dimensiones disponibles ahora: "
            f"{dimensiones_disponibles}"
        )

    extracted_at = datetime.now(timezone.utc)

    fixed_columns = ["value", "source_id", "notes_ids", "iso3"]
    dim_columns = list(dimension_map.values())
    columns = fixed_columns + dim_columns + ["extracted_at"]

    rows: list[tuple] = []

    for record in records:

        row: list[Any] = [
            record.get("value"),
            record.get("source_id"),
            _clean_optional(record.get("notes_ids")),
            _clean_optional(record.get("iso3")),
        ]

        for dim_name, column_name in dimension_map.items():

            raw_value = record.get(dim_name)

            if column_name in _INTEGER_COLUMNS and raw_value is not None:

                try:
                    raw_value = int(raw_value)

                except (TypeError, ValueError):

                    raise CepalLoadError(
                        f"No se pudo convertir '{raw_value}' de la "
                        f"dimensión '{dim_name}' a entero para la "
                        f"columna '{column_name}'."
                    )

            row.append(raw_value)

        row.append(extracted_at)

        rows.append(tuple(row))

    return columns, rows


def load_indicator_to_postgres(indicator_id: int) -> dict[str, Any]:


    config = INDICATOR_TABLE_CONFIG.get(indicator_id)

    if config is None:

        raise CepalLoadError(
            f"El indicador {indicator_id} no tiene una configuración de "
            f"carga definida. Indicadores soportados: "
            f"{list(INDICATOR_TABLE_CONFIG)}"
        )

    table = config["table"]

    columns, rows = _build_rows_for_indicator(indicator_id)

    insert_sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s"

    conn = _get_connection()

    try:

        with conn:

            with conn.cursor() as cur:

                execute_values(cur, insert_sql, rows, page_size=1000)

    except psycopg2.Error as exc:

        raise CepalLoadError(
            f"Error insertando en la tabla '{table}': {exc}"
        ) from exc

    finally:

        conn.close()

    return {
        "indicator_id": indicator_id,
        "tabla": table,
        "filas_insertadas": len(rows),
        "columnas": columns,
    }