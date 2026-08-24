from app.cleaner.block_extractor import DataBlock
from app.cleaner.text_utils import normalize_text, slugify_column


YEAR_COLUMN_KEYS = {"ano", "anio", "year"}


def _normalize_value(value, header_key: str):
    """
    Convierte el valor crudo de una celda al tipo correcto:
    años y enteros como int, valores decimales como float,
    y todo lo demás como texto limpio.
    """

    text = normalize_text(value)

    if text == "":
        return None

    numeric = _try_parse_number(text)

    if numeric is None:
        return text

    if header_key in YEAR_COLUMN_KEYS:
        return int(numeric)

    if numeric == int(numeric):
        return int(numeric)

    return numeric


def _try_parse_number(text: str):

    cleaned = text.replace(",", ".").replace("%", "").strip()

    try:
        return float(cleaned)

    except ValueError:
        return None


def normalize_block(block: DataBlock) -> DataBlock:
    """
    Normaliza encabezados y valores de un bloque: repara encoding,
    recorta espacios, homogeniza tipos de dato y elimina filas
    duplicadas o completamente vacías.
    """

    clean_headers = [
        normalize_text(header)
        for header in block.headers
    ]

    header_keys = [
        slugify_column(header)
        for header in clean_headers
    ]

    seen = set()

    clean_rows: list[list] = []

    for row in block.rows:

        padded = list(row) + [None] * (
            len(clean_headers) - len(row)
        )

        padded = padded[: len(clean_headers)]

        normalized_row = [
            _normalize_value(cell, header_keys[index])
            for index, cell in enumerate(padded)
        ]

        if all(cell is None for cell in normalized_row):
            continue

        key = tuple(normalized_row)

        if key in seen:
            continue

        seen.add(key)

        clean_rows.append(normalized_row)

    return DataBlock(
        title=normalize_text(block.title),
        headers=clean_headers,
        rows=clean_rows,
        source_sheet=block.source_sheet,
        source_file=block.source_file,
        extra={
            **block.extra,
            "header_keys": header_keys,
        },
    )


def normalize_blocks(blocks: list[DataBlock]) -> list[DataBlock]:

    return [
        normalize_block(block)
        for block in blocks
        if block.headers and block.rows
    ]
