from dataclasses import dataclass, field

import openpyxl

from app.cleaner.text_utils import normalize_text


@dataclass
class DataBlock:
    """
    Representa una tabla individual dentro de una hoja: un título
    opcional, una fila de encabezados y las filas de datos asociadas.
    """

    title: str
    headers: list[str]
    rows: list[list]
    source_sheet: str = ""
    source_file: str = ""
    extra: dict = field(default_factory=dict)


def _row_is_empty(row: tuple) -> bool:

    return all(
        cell is None or normalize_text(cell) == ""
        for cell in row
    )


def _looks_like_header(row: tuple) -> bool:
    """
    Una fila de encabezado tiene casi todas sus celdas no vacías
    y en su mayoría son texto (no números), a diferencia de las
    filas de datos que suelen mezclar texto con números/años.
    """

    values = [
        normalize_text(cell)
        for cell in row
        if normalize_text(cell) != ""
    ]

    if len(values) < 2:
        return False

    non_numeric = sum(
        1
        for value in values
        if not _is_numeric(value)
    )

    return non_numeric >= len(values) - 1


def _is_numeric(value: str) -> bool:

    try:
        float(value.replace(",", "."))
        return True

    except ValueError:
        return False


def extract_blocks_from_sheet(
    rows: list[tuple],
    sheet_name: str,
    source_file: str,
) -> list[DataBlock]:
    """
    Recorre una hoja fila por fila detectando el patrón:
    [fila(s) vacías] -> [título opcional] -> [encabezado] -> [filas de datos]
    y devuelve un DataBlock por cada tabla encontrada.
    """

    blocks: list[DataBlock] = []

    pending_title = ""

    headers: list[str] | None = None

    current_rows: list[list] = []

    def flush():
        if headers and current_rows:
            blocks.append(
                DataBlock(
                    title=pending_title,
                    headers=headers,
                    rows=[row[:] for row in current_rows],
                    source_sheet=sheet_name,
                    source_file=source_file,
                )
            )

    for row in rows:

        trimmed = _trim_row(row)

        if _row_is_empty(trimmed):

            flush()

            headers = None
            current_rows = []
            continue

        non_empty = [
            normalize_text(cell)
            for cell in trimmed
            if normalize_text(cell) != ""
        ]

        if headers is None:

            if len(non_empty) == 1:
                flush()
                pending_title = non_empty[0]
                headers = None
                current_rows = []
                continue

            if _looks_like_header(trimmed):
                flush()
                headers = [
                    normalize_text(cell)
                    for cell in trimmed
                ]
                current_rows = []
                continue

            continue

        current_rows.append(list(trimmed))

    flush()

    return blocks


def _trim_row(row: tuple) -> tuple:
    """
    Quita columnas vacías al principio/final de la fila (las hojas
    del formato de referencia suelen dejar una columna en blanco
    antes de empezar los datos reales).
    """

    values = list(row)

    while values and normalize_text(values[0]) == "":
        values.pop(0)

    while values and normalize_text(values[-1]) == "":
        values.pop()

    return tuple(values)


def extract_blocks_from_workbook(path: str) -> list[DataBlock]:

    workbook = openpyxl.load_workbook(
        path,
        data_only=True,
    )

    blocks: list[DataBlock] = []

    for sheet in workbook.worksheets:

        rows = list(
            sheet.iter_rows(values_only=True)
        )

        blocks.extend(
            extract_blocks_from_sheet(
                rows,
                sheet_name=sheet.title,
                source_file=path,
            )
        )

    return blocks


def extract_blocks_from_csv(path: str) -> list[DataBlock]:

    import csv

    with open(
        path,
        "r",
        encoding="utf-8",
        errors="replace",
        newline="",
    ) as handle:

        reader = csv.reader(handle)

        rows = [tuple(row) for row in reader]

    return extract_blocks_from_sheet(
        rows,
        sheet_name="csv",
        source_file=path,
    )
