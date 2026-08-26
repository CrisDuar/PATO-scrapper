"""
Pruebas de carga e integración del proceso de carga a PostgreSQL
(app/cleaner/loader.py, db.py, star_schema_mapper.py).

Usan la base de datos real definida en DATABASE_URL (.env). El
usuario de servicio (scraper_service) solo tiene permisos
INSERT/SELECT/UPDATE (sin DELETE, por diseño), así que en vez de
limpiar filas al terminar, cada test aísla sus datos con un nombre
de área geográfica único (UUID) para no chocar entre corridas ni con
datos reales; las filas de prueba quedan en la base pero con un
'level' reconocible ('__test__dominio') para poder identificarlas.
Se saltan automáticamente si no hay conexión disponible (ver
tests/conftest.py::requires_db).
"""

import json
import uuid

import pytest

from app.cleaner.db import get_connection
from app.cleaner.loader import load_tables, _write_load_log
from tests.conftest import requires_db


TEST_GEO_LEVEL = "dominio"


def _unique_geo_name() -> str:

    return f"__test__ {uuid.uuid4().hex[:12]}"


def _sample_ipm_por_dominio_rows(geo_name: str) -> list[dict]:

    return [
        {
            "anio": 2025,
            "dominio": geo_name,
            "ipm": 12.5,
            "fuente": "TEST",
            "fecha_extraccion": "2026-08-25T00:00:00+00:00",
        }
    ]


@requires_db
def test_load_tables_inserts_rows():

    geo_name = _unique_geo_name()

    report = load_tables(
        {"ipm_por_dominio": _sample_ipm_por_dominio_rows(geo_name)}
    )

    assert report["ipm_por_dominio"]["insertadas"] == 1
    assert report["ipm_por_dominio"]["rechazadas"] == 0

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT s.value, i.code, ga.name, ga.level
                FROM ipm_statistic s
                JOIN indicator i ON i.id = s.indicator_id
                JOIN geographic_area ga ON ga.id = s.geographic_area_id
                WHERE ga.name = %s
                """,
                (geo_name,),
            )

            rows = cursor.fetchall()

    finally:
        conn.close()

    assert len(rows) == 1

    value, code, name, level = rows[0]

    assert float(value) == 12.5
    assert (code, name, level) == ("MPI", geo_name, TEST_GEO_LEVEL)


@requires_db
def test_load_tables_is_idempotent():
    """
    Cargar el mismo lote dos veces no debe duplicar filas: el UPSERT
    por la clave natural real de ipm_statistic debe actualizar en
    vez de insertar de nuevo.
    """

    geo_name = _unique_geo_name()

    mapped_tables = {"ipm_por_dominio": _sample_ipm_por_dominio_rows(geo_name)}

    load_tables(mapped_tables)
    report = load_tables(mapped_tables)

    assert report["ipm_por_dominio"]["insertadas"] == 1

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "SELECT count(*) FROM geographic_area WHERE name = %s",
                (geo_name,),
            )

            assert cursor.fetchone()[0] == 1

    finally:
        conn.close()


@requires_db
def test_load_tables_updates_value_on_reload():

    geo_name = _unique_geo_name()

    load_tables({"ipm_por_dominio": _sample_ipm_por_dominio_rows(geo_name)})

    updated_rows = _sample_ipm_por_dominio_rows(geo_name)
    updated_rows[0]["ipm"] = 33.3

    load_tables({"ipm_por_dominio": updated_rows})

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT s.value FROM ipm_statistic s
                JOIN geographic_area ga ON ga.id = s.geographic_area_id
                WHERE ga.name = %s
                """,
                (geo_name,),
            )

            assert float(cursor.fetchone()[0]) == 33.3

    finally:
        conn.close()


@requires_db
def test_load_tables_rejects_rows_missing_required_fields():

    mapped_tables = {
        "ipm_por_dominio": [
            {
                "anio": 2025,
                "dominio": None,
                "ipm": 12.5,
                "fuente": "TEST",
                "fecha_extraccion": "2026-08-25T00:00:00+00:00",
            }
        ]
    }

    report = load_tables(mapped_tables)

    assert report["ipm_por_dominio"]["insertadas"] == 0
    assert report["ipm_por_dominio"]["rechazadas"] == 1


@requires_db
def test_load_tables_marks_unmapped_tables_as_omitted():
    """
    Las sub-tablas sin mapeo acordado al esquema estrella (todas
    salvo LOADABLE_TABLES) no deben intentarse cargar; deben
    reportarse como omitidas, no como error.
    """

    mapped_tables = {
        "dashboard_02": [
            {"anio": 2025, "region": 1, "departamento": 5},
        ],
    }

    report = load_tables(mapped_tables)

    assert report["dashboard_02"]["insertadas"] == 0
    assert report["dashboard_02"]["omitidas"] == 1


@requires_db
def test_load_tables_rolls_back_whole_job_on_db_error(monkeypatch):
    """
    Si una tabla falla a mitad de la transacción del job, ninguna
    fila de ese job debe quedar persistida (atomicidad por job).
    """

    from app.cleaner import loader as loader_module

    original_upsert = loader_module.upsert_ipm_statistics

    call_count = {"n": 0}

    def failing_upsert(cursor, rows):

        call_count["n"] += 1

        if call_count["n"] == 2:
            raise RuntimeError("fallo simulado en la segunda tabla")

        return original_upsert(cursor, rows)

    monkeypatch.setattr(loader_module, "upsert_ipm_statistics", failing_upsert)

    geo_name = _unique_geo_name()

    mapped_tables = {
        "ipm_por_dominio": _sample_ipm_por_dominio_rows(geo_name),
        "proporcion_privaciones": [
            {
                "anio": 2025,
                "dominio": geo_name,
                "porcentaje": 40.0,
                "fuente": "TEST",
                "fecha_extraccion": "2026-08-25T00:00:00+00:00",
            }
        ],
    }

    report = load_tables(mapped_tables)

    assert all("error" in entry for entry in report.values())

    conn = get_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                "SELECT count(*) FROM geographic_area WHERE name = %s",
                (geo_name,),
            )

            assert cursor.fetchone()[0] == 0

    finally:
        conn.close()


def test_write_load_log_creates_history(tmp_path):

    report = {
        "ipm_por_dominio": {"insertadas": 3, "rechazadas": 0},
    }

    log_path = _write_load_log(tmp_path, job_id="job-123", report=report)

    assert log_path.exists()

    history = json.loads(log_path.read_text(encoding="utf-8"))

    assert len(history) == 1
    assert history[0]["job_id"] == "job-123"
    assert history[0]["total_insertadas"] == 3
    assert history[0]["exito"] is True


def test_write_load_log_appends_to_existing_history(tmp_path):

    report_ok = {"ipm_por_dominio": {"insertadas": 1, "rechazadas": 0}}
    report_fail = {"ipm_por_dominio": {"insertadas": 0, "rechazadas": 1, "error": "boom"}}

    _write_load_log(tmp_path, job_id="job-123", report=report_ok)
    log_path = _write_load_log(tmp_path, job_id="job-123", report=report_fail)

    history = json.loads(log_path.read_text(encoding="utf-8"))

    assert len(history) == 2
    assert history[0]["exito"] is True
    assert history[1]["exito"] is False
