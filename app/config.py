import os

from pathlib import Path

from dotenv import load_dotenv



APP_DIR = Path(__file__).resolve().parent

BASE_DIR = APP_DIR.parent


ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


def get_string(
    name: str,
    default: str,
) -> str:

    value = os.getenv(name)

    if value is None:
        return default

    return value.strip()


def get_int(
    name: str,
    default: int,
) -> int:

    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)

    except ValueError as exc:
        raise ValueError(
            f"La variable {name} debe ser un entero."
        ) from exc


def get_float(
    name: str,
    default: float,
) -> float:

    value = os.getenv(name)

    if value is None:
        return default

    try:
        return float(value)

    except ValueError as exc:
        raise ValueError(
            f"La variable {name} debe ser un número."
        ) from exc


def get_bool(
    name: str,
    default: bool,
) -> bool:

    value = os.getenv(name)

    if value is None:
        return default

    return value.lower() in {
        "true",
        "1",
        "yes",
        "y",
        "on",
    }


def get_list(
    name: str,
    default: str = "",
) -> list[str]:

    value = os.getenv(
        name,
        default,
    )

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]



APP_NAME = get_string(
    "APP_NAME",
    "PATO Data Discovery",
)

APP_VERSION = get_string(
    "APP_VERSION",
    "3.0.0",
)


API_HOST = get_string(
    "API_HOST",
    "127.0.0.1",
)

API_PORT = get_int(
    "API_PORT",
    8000,
)



SCRAPY_MAX_DEPTH = get_int(
    "SCRAPY_MAX_DEPTH",
    10,
)

SCRAPY_CONCURRENT_REQUESTS = get_int(
    "SCRAPY_CONCURRENT_REQUESTS",
    8,
)

SCRAPY_DOWNLOAD_DELAY = get_float(
    "SCRAPY_DOWNLOAD_DELAY",
    0.5,
)

SCRAPY_ROBOTSTXT_OBEY = get_bool(
    "SCRAPY_ROBOTSTXT_OBEY",
    True,
)

SCRAPY_USER_AGENT = get_string(
    "SCRAPY_USER_AGENT",
    "PATO-DataDiscovery/3.0",
)

LOG_LEVEL = get_string(
    "LOG_LEVEL",
    "INFO",
)



MIN_LINK_SCORE = get_int(
    "MIN_LINK_SCORE",
    20,
)

MIN_PAGE_SCORE = get_int(
    "MIN_PAGE_SCORE",
    15,
)

MIN_FILE_SCORE = get_int(
    "MIN_FILE_SCORE",
    20,
)

MAX_PAGES = get_int(
    "MAX_PAGES",
    1000,
)



DOWNLOADS_DIR = (
    BASE_DIR
    / get_string(
        "DOWNLOADS_DIR",
        "downloads",
    )
)

DOWNLOADS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


FILE_EXTENSIONS = tuple(
    (
        extension
        if extension.startswith(".")
        else f".{extension}"
    ).lower()
    for extension in get_list(
        "FILE_EXTENSIONS",
        ".pdf,.xlsx,.xls,.csv,.zip,.rar,.7z,.json,.xml,.txt,.doc,.docx",
    )
)



DISCOVERY_KEYWORDS = tuple(
    keyword.lower()
    for keyword in get_list(
        "DISCOVERY_KEYWORDS",
        (
            "datos,"
            "estadisticas,"
            "estadística,"
            "indicadores,"
            "informacion,"
            "información,"
            "publicaciones,"
            "microdatos,"
            "documentos,"
            "metodologia,"
            "metodología,"
            "resultados,"
            "base de datos,"
            "descargas"
        ),
    )
)