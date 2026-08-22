from app.scraper.crawler.page_classifier import (
    calculate_page_score,
)


def calculate_link_score(
    url: str,
    text: str,
    query: str,
) -> int:

    score = calculate_page_score(
        url,
        text,
        query,
    )

    text_lower = text.lower()

    url_lower = url.lower()



    if query.lower() in text_lower:
        score += 60

    if query.lower() in url_lower:
        score += 60


    important_terms = (
        "indicador",
        "indicadores",
        "pobreza",
        "multidimensional",
        "ipm",
        "datos",
        "resultado",
        "resultados",
        "metodologia",
        "metodología",
        "microdatos",
        "base de datos",
        "documento",
        "publicacion",
        "publicación",
        "estadistica",
        "estadística",
    )

    for term in important_terms:

        if term in text_lower:
            score += 10

        if term in url_lower:
            score += 10

    return score