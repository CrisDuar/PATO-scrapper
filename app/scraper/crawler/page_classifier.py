from urllib.parse import urlparse

from app.config import (
    DISCOVERY_KEYWORDS,
)


def calculate_page_score(
    url: str,
    text: str,
    query: str,
) -> int:

    score = 0

    query_lower = query.lower()

    url_lower = url.lower()

    text_lower = text.lower()



    if query_lower in url_lower:
        score += 50

    if query_lower in text_lower:
        score += 40


    for keyword in DISCOVERY_KEYWORDS:

        if keyword in url_lower:
            score += 8

        if keyword in text_lower:
            score += 4



    statistical_paths = (
        "datos",
        "estadisticas",
        "estadística",
        "indicadores",
        "microdatos",
        "biblioteca",
        "documentos",
        "publicaciones",
        "descargas",
        "resultados",
        "informacion",
        "información",
    )

    parsed = urlparse(url)

    path = parsed.path.lower()

    for word in statistical_paths:

        if word in path:
            score += 10

    return score