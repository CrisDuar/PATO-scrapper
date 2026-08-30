import re

from app.cleaner.block_extractor import DataBlock
from app.cleaner.schema import ALL_TABLES, ColumnSpec, TableSpec
from app.cleaner.text_utils import slugify_column


def _infer_year_from_title(title: str) -> int | None:
    """
    Algunas tablas (contribuciones, dashboard_03) traen el año como
    parte del título del bloque en vez de como columna, cuando el
    anexo solo reporta el año más reciente (p. ej. 'Principales
    Dominios\\n2025'). Toma el último año de 4 dígitos mencionado.
    """

    matches = re.findall(r"\b\d{4}\b", title)

    plausible = [
        int(match)
        for match in matches
        if 1900 <= int(match) <= 2100
    ]

    return plausible[-1] if plausible else None


TRUE_VALUES = {"1", "si", "sí", "true", "verdadero", "x", "yes"}
FALSE_VALUES = {"0", "no", "false", "falso", ""}


def _coerce_value(value, column: ColumnSpec):

    if value is None:
        return None

    if column.dtype == "boolean":

        if isinstance(value, bool):
            return value

        text = str(value).strip().lower()

        if text in TRUE_VALUES:
            return True

        if text in FALSE_VALUES:
            return False

        return None

    if column.dtype == "int":

        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    if column.dtype == "float":

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return str(value).strip()


# Palabras clave en el título del bloque (comparadas contra su
# versión "slug", sin tildes/mojibake) que desambiguan entre
# sub-tablas que comparten las mismas columnas base (anio, dominio,
# variable/sexo, ipm/porcentaje) pero se distinguen por contexto.
TITLE_HINTS: dict[str, tuple[str, ...]] = {
    "incidencia_por_sexo_jefe_hogar": ("jefe_de_hogar", "jefatura"),
    "incidencia_por_sexo_persona": ("segun_sexo", "por_sexo"),
    "contribuciones_incidencia": ("contribuci", "incidencia_ajustada"),
    "proporcion_privaciones": ("proporcion_de_privaciones", "intensidad"),
    "privaciones_por_hogar": ("privaciones_por_hogar",),
}


def _title_matches(spec_name: str, title: str) -> bool:

    hints = TITLE_HINTS.get(spec_name)

    if not hints:
        return True

    title_slug = slugify_column(title)

    return any(hint in title_slug for hint in hints)


# Palabras clave de título que descartan una spec aunque sus
# columnas (genéricas: dominio/anio/valor) coincidan por accidente
# con otro indicador. P. ej. el DANE publica "Población total -
# Personas" con exactamente las columnas Dominio/Año/Valor, que de
# otro modo matchearía ipm_por_dominio vía el alias "valor" -> "ipm"
# y contaminaría esa tabla con conteos de población en vez de IPM.
TITLE_EXCLUDES: dict[str, tuple[str, ...]] = {
    "ipm_por_dominio": ("poblacion_total", "poblacion_",),
    "proporcion_privaciones": ("poblacion_total", "poblacion_",),
}


def _title_excluded(spec_name: str, title: str) -> bool:

    excludes = TITLE_EXCLUDES.get(spec_name)

    if not excludes:
        return False

    title_slug = slugify_column(title)

    return any(exclude in title_slug for exclude in excludes)


def _resolve_column_source(
    spec: TableSpec,
    header_keys: list[str],
) -> dict[str, int] | None:
    """
    Para cada columna destino de `spec`, busca su índice en los
    encabezados de origen (por header_key directo o por alias).
    Devuelve None si falta alguna columna requerida.
    """

    header_key_set = set(header_keys)

    # spec.header_key_aliases mapea alias_de_origen -> nombre_destino.
    # Para saber si una columna destino requerida está presente en el
    # origen, también hay que aceptar cualquier alias que apunte a ella.
    aliases_for_target: dict[str, list[str]] = {}

    for alias, target in spec.header_key_aliases.items():
        aliases_for_target.setdefault(target, []).append(alias)

    for required_key in spec.required_header_keys:

        candidates = {required_key, *aliases_for_target.get(required_key, [])}

        if not (candidates & header_key_set):
            return None

    column_source: dict[str, int] = {}

    for column in spec.columns:

        target_name = column.name

        candidate_keys = [
            target_name,
            *aliases_for_target.get(target_name, []),
        ]

        for candidate_key in candidate_keys:

            if candidate_key in header_keys:
                column_source[target_name] = header_keys.index(candidate_key)
                break

    return column_source


def match_table(block: DataBlock) -> TableSpec | None:
    """
    Determina a qué sub-tabla del esquema pertenece un bloque
    normalizado, según sus header_keys y (cuando hace falta para
    desambiguar) el título del bloque.
    """

    header_keys = block.extra.get("header_keys", [])

    candidates = []

    for spec in ALL_TABLES:

        if _title_excluded(spec.name, block.title):
            continue

        column_source = _resolve_column_source(spec, header_keys)

        if column_source is None:
            continue

        candidates.append((spec, column_source))

    if not candidates:
        return None

    # Prioriza la coincidencia con más columnas resueltas (más
    # específica); ante empate, usa el título del bloque para
    # desambiguar entre sub-tablas con las mismas columnas base.
    max_columns = max(len(cs) for _, cs in candidates)

    most_specific = [
        (spec, cs)
        for spec, cs in candidates
        if len(cs) == max_columns
    ]

    if len(most_specific) == 1:
        return most_specific[0][0]

    # Entre los empatados en especificidad, prioriza los que tienen
    # hints propios en TITLE_HINTS y cuyo título realmente matchea
    # (más confiable que un spec sin hints, que "matchea" cualquier
    # título por defecto).
    specific_title_matches = [
        spec
        for spec, _ in most_specific
        if spec.name in TITLE_HINTS and _title_matches(spec.name, block.title)
    ]

    if specific_title_matches:
        return specific_title_matches[0]

    generic_matches = [
        spec
        for spec, _ in most_specific
        if spec.name not in TITLE_HINTS
    ]

    if generic_matches:
        return generic_matches[0]

    return most_specific[0][0]


def map_block_to_rows(block: DataBlock, spec: TableSpec) -> list[dict]:
    """
    Convierte las filas crudas de un bloque en diccionarios con las
    claves de columna destino de `spec`, usando los header_keys del
    bloque para localizar cada valor.
    """

    header_keys = block.extra.get("header_keys", [])

    column_source = _resolve_column_source(spec, header_keys)

    if column_source is None:
        return []

    inferred_year = None

    if "anio" not in column_source:
        inferred_year = _infer_year_from_title(block.title)

    mapped_rows: list[dict] = []

    for row in block.rows:

        record = {}

        for column in spec.columns:

            if column.name == "anio" and "anio" not in column_source:
                record["anio"] = inferred_year
                continue

            index = column_source.get(column.name)

            raw_value = row[index] if index is not None else None

            record[column.name] = _coerce_value(raw_value, column)

        mapped_rows.append(record)

    return mapped_rows


def _dedupe_rows(rows: list[dict], spec: TableSpec) -> list[dict]:
    """
    Descarta filas con clave natural incompleta (algún campo de la
    clave en None) y deduplica por esa clave, quedándose con la
    primera aparición.
    """

    seen_keys = set()

    deduped: list[dict] = []

    for row in rows:

        key = tuple(row.get(field) for field in spec.natural_key)

        if any(value is None for value in key):
            continue

        if key in seen_keys:
            continue

        seen_keys.add(key)

        deduped.append(row)

    sort_fields = _sort_order(spec.natural_key)

    deduped.sort(
        key=lambda row: tuple(
            _sort_key(row.get(field)) for field in sort_fields
        )
    )

    return deduped


def _sort_order(natural_key: tuple[str, ...]) -> tuple[str, ...]:
    """
    Orden de presentación de filas: agrupa primero por las columnas
    de categoría (dominio, país, sexo, variable...) y deja 'anio' al
    final, para que el CSV/Excel lea como una serie de tiempo por
    grupo en vez de intercalar años entre grupos distintos.
    """

    return tuple(
        field for field in natural_key if field != "anio"
    ) + tuple(
        field for field in natural_key if field == "anio"
    )


def _sort_key(value):
    """
    Clave de orden segura para valores mixtos (int/float/str/None):
    agrupa por tipo antes que por valor, para que comparar no falle
    con TypeError cuando una columna mezcla números y texto.
    """

    if value is None:
        return (0, "")

    if isinstance(value, (int, float)):
        return (1, value)

    return (2, str(value))


def map_blocks(blocks: list[DataBlock]) -> dict[str, list[dict]]:
    """
    Clasifica y transforma una lista de bloques normalizados en
    filas listas para cada sub-tabla del esquema. Bloques que no
    calzan con ninguna sub-tabla se devuelven aparte bajo
    'sin_clasificar' junto con metadatos de origen para revisión manual.
    """

    result: dict[str, list[dict]] = {
        spec.name: [] for spec in ALL_TABLES
    }

    unmatched: list[dict] = []

    for block in blocks:

        spec = match_table(block)

        if spec is None:

            unmatched.append(
                {
                    "title": block.title,
                    "headers": block.headers,
                    "source_file": block.source_file,
                    "source_sheet": block.source_sheet,
                    "row_count": len(block.rows),
                }
            )

            continue

        result[spec.name].extend(
            map_block_to_rows(block, spec)
        )

    for spec in ALL_TABLES:
        result[spec.name] = _dedupe_rows(result[spec.name], spec)

    result["sin_clasificar"] = unmatched

    return result
