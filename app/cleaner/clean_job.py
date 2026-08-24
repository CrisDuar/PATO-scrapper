from pathlib import Path

from app.cleaner.block_extractor import (
    DataBlock,
    extract_blocks_from_csv,
    extract_blocks_from_workbook,
)
from app.cleaner.exporter import export_to_workbook
from app.cleaner.normalizer import normalize_blocks
from app.cleaner.sheet_classifier import classify_blocks


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

OUTPUT_FILENAME = "datos_limpios.xlsx"


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
    que contienen, las normaliza y las exporta al formato estándar
    (mismo layout de 'Formato de Datos.xlsx') en
    <job_dir>/datos_limpios.xlsx.
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

    grouped_blocks = classify_blocks(normalized_blocks)

    output_path = job_dir / OUTPUT_FILENAME

    export_to_workbook(
        grouped_blocks,
        str(output_path),
    )

    return {
        "archivos_procesados": processed_files,
        "bloques_detectados": len(normalized_blocks),
        "bloques_por_hoja": {
            sheet_name: len(blocks)
            for sheet_name, blocks in grouped_blocks.items()
        },
        "archivo_salida": output_path.name,
    }
