import openpyxl
from openpyxl.styles import Font

from app.cleaner.block_extractor import DataBlock
from app.cleaner.sheet_classifier import (
    DASHBOARD_01,
    DASHBOARD_02,
    DASHBOARD_03,
    SIN_CLASIFICAR,
)


SHEET_ORDER = [
    DASHBOARD_01,
    DASHBOARD_02,
    DASHBOARD_03,
    SIN_CLASIFICAR,
]

TITLE_FONT = Font(bold=True, size=12)

HEADER_FONT = Font(bold=True)


def write_blocks_to_sheet(sheet, blocks: list[DataBlock]) -> None:

    current_row = 1

    for block in blocks:

        if block.title:

            cell = sheet.cell(
                row=current_row,
                column=1,
                value=block.title,
            )

            cell.font = TITLE_FONT

            current_row += 1

        for column_index, header in enumerate(
            block.headers,
            start=1,
        ):

            cell = sheet.cell(
                row=current_row,
                column=column_index,
                value=header,
            )

            cell.font = HEADER_FONT

        current_row += 1

        for row in block.rows:

            for column_index, value in enumerate(
                row,
                start=1,
            ):

                sheet.cell(
                    row=current_row,
                    column=column_index,
                    value=value,
                )

            current_row += 1

        current_row += 1


def export_to_workbook(
    grouped_blocks: dict[str, list[DataBlock]],
    output_path: str,
) -> str:
    """
    Escribe un Excel con la misma estructura visual del formato de
    referencia: una hoja por dashboard, cada una con sus bloques
    (título en negrita + encabezado en negrita + filas de datos).
    """

    workbook = openpyxl.Workbook()

    workbook.remove(workbook.active)

    for sheet_name in SHEET_ORDER:

        blocks = grouped_blocks.get(sheet_name, [])

        if not blocks:
            continue

        sheet = workbook.create_sheet(title=sheet_name)

        write_blocks_to_sheet(sheet, blocks)

    if not workbook.sheetnames:
        workbook.create_sheet(title=SIN_CLASIFICAR)

    workbook.save(output_path)

    return output_path
