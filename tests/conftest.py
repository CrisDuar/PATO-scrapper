import pytest

from app.config import DATABASE_URL


def _db_available() -> bool:

    if not DATABASE_URL:
        return False

    try:
        import psycopg2

        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
        conn.close()
        return True

    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="DATABASE_URL no configurada o base de datos no accesible.",
)
