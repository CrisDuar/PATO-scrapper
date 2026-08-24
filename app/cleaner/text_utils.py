import re
import unicodedata


ENCODING_FIXES = {
    "�": "",
}


def fix_mojibake(value: str) -> str:
    """
    Repara texto mal decodificado (mojibake) proveniente de
    archivos que originalmente estaban en latin-1/cp1252 y
    fueron leídos como utf-8 (o viceversa).
    """

    if not value:
        return value

    candidates = [value]

    try:
        candidates.append(
            value.encode("latin-1").decode("utf-8")
        )
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    try:
        candidates.append(
            value.encode("cp1252").decode("utf-8")
        )
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    best = min(
        candidates,
        key=lambda text: text.count("�"),
    )

    return best


def normalize_text(value) -> str:
    """
    Limpia espacios redundantes, repara encoding y normaliza
    unicode (NFC) para que valores como 'A�o ' y 'Año' o
    'Dominio' y 'Dominio ' se traten como iguales.
    """

    if value is None:
        return ""

    text = str(value)

    text = fix_mojibake(text)

    text = unicodedata.normalize("NFC", text)

    text = text.replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text).strip()

    return text


def slugify_column(value) -> str:
    """
    Convierte un encabezado humano ('Año ', 'Privación por Analfabetismo')
    en un identificador snake_case sin tildes, usado como clave interna
    para comparar/mapear columnas entre archivos distintos.
    """

    text = normalize_text(value).lower()

    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )

    text = re.sub(r"[^a-z0-9]+", "_", text)

    return text.strip("_")
