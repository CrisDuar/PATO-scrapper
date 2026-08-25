from datetime import datetime, timezone
from pathlib import Path

from app.cleaner.block_extractor import (
    DataBlock,
    extract_blocks_from_csv,
    extract_blocks_from_workbook,
)
from app.cleaner.exporter import export_tables
from app.cleaner.normalizer import normalize_blocks
from app.cleaner.table_mapper import map_blocks


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

OUTPUT_DIR_NAME = "datos_limpios"


def _extract_blocks_from_file(path: Path) -> list[DataBlock]:

    extension = path.suffix.lower()

    try:

        if extension == ".csv":
            return extract_blocks_from_csv(str(path))

        if extension in {".xlsx", ".xls"}:
            return extract_blocks_from_workbook(str(path))

    except Exception:
        return []

    return []


def clean_job_files(job_dir: Path) -> dict:
    """
    Recorre los archivos descargados de un job, extrae las tablas
    que contienen, las normaliza, las clasifica en las sub-tablas
    del esquema objetivo (ver Contexto_Limpieza_Datos_Scraper.md) y
    las exporta como CSV listos para cargar a PostgreSQL en
    <job_dir>/datos_limpios/<tabla>.csv.
    """

    if not job_dir.exists():
        raise FileNotFoundError(
            f"No existe el directorio del job: {job_dir}"
        )

    source_files = [
        file
        for file in sorted(job_dir.iterdir())
        if file.is_file()
        and file.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    all_blocks: list[DataBlock] = []

    processed_files: list[str] = []

    for file in source_files:

        blocks = _extract_blocks_from_file(file)

        if blocks:
            processed_files.append(file.name)

        all_blocks.extend(blocks)

    normalized_blocks = normalize_blocks(all_blocks)

    mapped_tables = map_blocks(normalized_blocks)

    output_dir = job_dir / OUTPUT_DIR_NAME

    written_files = export_tables(
        mapped_tables,
        output_dir=output_dir,
        fuente="DANE",
        fecha_extraccion=datetime.now(timezone.utc).isoformat(),
    )

    return {
        "archivos_procesados": processed_files,
        "bloques_detectados": len(normalized_blocks),
        "filas_por_tabla": {
            table_name: len(rows)
            for table_name, rows in mapped_tables.items()
        },
        "archivos_salida": written_files,
    }
