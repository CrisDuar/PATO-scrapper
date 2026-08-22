from urllib.parse import (
    urljoin,
    urlparse,
    urldefrag,
)


def normalize_url(
    base_url: str,
    href: str,
) -> str | None:

    if not href:
        return None

    href = href.strip()

    if href.startswith(
        (
            "#",
            "javascript:",
            "mailto:",
            "tel:",
            "data:",
        )
    ):
        return None

    url = urljoin(
        base_url,
        href,
    )

    url, _ = urldefrag(url)

    parsed = urlparse(url)

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return None

    return url


def get_hostname(
    url: str,
) -> str:

    return (
        urlparse(url)
        .hostname
        or ""
    ).lower()


def get_filename(
    url: str,
) -> str:

    path = urlparse(url).path

    filename = (
        path.rstrip("/")
        .split("/")[-1]
    )

    return filename or "archivo_descargado"


def is_same_domain(
    url: str,
    allowed_domains: list[str],
) -> bool:

    hostname = get_hostname(url)

    for domain in allowed_domains:

        domain = domain.lower().strip()

        if (
            hostname == domain
            or hostname.endswith(
                "." + domain
            )
        ):
            return True

    return False