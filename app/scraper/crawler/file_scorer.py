import re

from pathlib import Path
from urllib.parse import urlparse




STRONG_TERMS = {
    "ipm",
    "indice de pobreza multidimensional",
    "índice de pobreza multidimensional",
    "pobreza multidimensional",
    "pobreza_multidimensional",
    "pobreza-multidimensional",
}



RELATED_TERMS = {
    "pobreza",
    "multidimensional",
    "privaciones",
    "privacion",
    "privación",
    "dimensiones",
    "dimension",
    "dimensión",
}



def normalize_text(
    value: str,
) -> str:

    value = value.lower()

    replacements = {
        "_": " ",
        "-": " ",
        "/": " ",
        "\\": " ",
        ".": " ",
    }

    for old, new in replacements.items():
        value = value.replace(
            old,
            new,
        )

    # Eliminar espacios duplicados

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def calculate_file_score(
    url: str,
    link_text: str,
    query: str,
    source_page: str = "",
) -> int:



    query_normalized = normalize_text(
        query
    )

    url_normalized = normalize_text(
        url
    )

    text_normalized = normalize_text(
        link_text
    )

    source_normalized = normalize_text(
        source_page
    )

    filename = Path(
        urlparse(url).path
    ).name

    filename_normalized = normalize_text(
        filename
    )

    contexts = [
        filename_normalized,
        text_normalized,
        url_normalized,
        source_normalized,
    ]

    full_context = " ".join(
        contexts
    )

    score = 0



    if query_normalized in filename_normalized:
        score += 100

    if query_normalized in text_normalized:
        score += 80

    if query_normalized in url_normalized:
        score += 70

    if query_normalized in source_normalized:
        score += 50



    strong_matches = 0

    for term in STRONG_TERMS:

        normalized_term = normalize_text(
            term
        )

        if normalized_term in full_context:

            strong_matches += 1

            # Una coincidencia fuerte
            # ya es una evidencia importante.

            score += 60



    related_matches = 0

    for term in RELATED_TERMS:

        normalized_term = normalize_text(
            term
        )

        if normalized_term in full_context:

            related_matches += 1

            score += 15


    has_poverty = (
        "pobreza"
        in full_context
    )

    has_multidimensional = (
        "multidimensional"
        in full_context
    )

    if (
        has_poverty
        and has_multidimensional
    ):
        score += 80


    if (
        has_poverty
        and "privaciones"
        in full_context
    ):
        score += 50


    if (
        has_poverty
        and (
            "dimensiones"
            in full_context
            or "dimension"
            in full_context
        )
    ):
        score += 40


    other_statistics = {
        "iccv",
        "ices",
        "ictc",
        "ictip",
        "ipc",
        "ipp",
        "ica",
        "icac",
        "ens",
        "eas",
        "etup",
    }

    for statistic in other_statistics:

        if statistic in filename_normalized:
            score -= 100

        if statistic in url_normalized:
            score -= 100

        if statistic in source_normalized:
            score -= 100



    if (
        strong_matches == 0
        and not (
            has_poverty
            and has_multidimensional
        )
        and related_matches < 2
    ):
        return 0

    return max(
        score,
        0,
    )