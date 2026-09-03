"""
Cliente para la API pública de CEPALSTAT (CEPAL).

Documentación oficial: https://statistics.cepal.org/portal/cepalstat/open-data.html
Swagger:               https://api-cepalstat.cepal.org/apidocs

Endpoints usados:
  - GET /cepalstat/api/v1/thematic-tree        -> árbol de temas e indicadores
                                                    (para buscar el id de un indicador por nombre)
  - GET /cepalstat/api/v1/indicator/{id}/data  -> datos de un indicador. Se pide en
                                                    formato Excel porque ya viene "aplanado"
                                                    (columnas fijas), a diferencia del JSON
                                                    crudo que usa dimensiones dinámicas
                                                    (dim_XXXXX) distintas por indicador.

IMPORTANTE: esta integración se escribió siguiendo la documentación oficial y un
ejemplo real publicado, pero no pudo probarse contra la API en vivo desde el
entorno de desarrollo (sin salida de red hacia api-cepalstat.cepal.org). Ejecútala
y, si CEPAL cambió algún nombre de columna, ajustamos `_detectar_columna_anio` o
`COLUMNAS_NO_DOMINIO` según la respuesta real.
"""

import io
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

BASE_URL = "https://api-cepalstat.cepal.org/cepalstat/api/v1"
TIMEOUT = 60

# Columnas del export de CEPALSTAT que NO forman parte del "dominio"
# (país / área geográfica / grupo poblacional, etc.)
COLUMNAS_NO_DOMINIO = {"indicator", "value", "unit", "notes_ids", "source_id"}

# Nombres de columna típicos para el año, según el indicador consultado
POSIBLES_COLUMNAS_ANIO = ["years_estandar", "anios_estandar", "year", "anio"]


class CepalApiError(Exception):
    """Error al consultar o interpretar la respuesta de la API de CEPALSTAT."""


def buscar_indicadores(nombre: str, lang: str = "es") -> List[Dict[str, Any]]:
    """
    Busca indicadores cuyo nombre contenga `nombre` (insensible a mayúsculas/minúsculas)
    recorriendo el árbol temático completo de CEPALSTAT.

    Devuelve una lista de dicts: [{"id": 1234, "name": "..."}, ...]
    """
    resp = requests.get(f"{BASE_URL}/thematic-tree", params={"lang": lang}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise CepalApiError(
            f"CEPALSTAT devolvió {resp.status_code} al consultar thematic-tree: {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise CepalApiError(f"La respuesta de thematic-tree no es JSON válido: {exc}") from exc

    encontrados: List[Dict[str, Any]] = []
    nombre_lower = nombre.lower()

    def _recorrer(nodo):
        if isinstance(nodo, dict):
            # En la respuesta real de CEPALSTAT, los nodos "hoja" (indicadores)
            # se identifican porque tienen la clave 'indicator_id' (no un campo
            # 'type'=='indicator' como se podría suponer). Los nodos de tema/
            # categoría en cambio tienen 'theme_id' o 'area_id' y 'children'.
            if "indicator_id" in nodo and "name" in nodo:
                if nombre_lower in str(nodo["name"]).lower():
                    encontrados.append({"id": nodo["indicator_id"], "name": nodo["name"]})
            for valor in nodo.values():
                _recorrer(valor)
        elif isinstance(nodo, list):
            for item in nodo:
                _recorrer(item)

    _recorrer(data)
    return encontrados


def descargar_datos_indicador(
    indicator_id: int, lang: str = "es", extra_params: Optional[Dict[str, Any]] = None
) -> pd.DataFrame:
    """
    Descarga los datos de un indicador de CEPALSTAT (en formato Excel, para obtener
    columnas ya aplanadas) y los devuelve como DataFrame de pandas.
    """
    params = {"format": "excel", "lang": lang}
    if extra_params:
        params.update(extra_params)

    resp = requests.get(f"{BASE_URL}/indicator/{indicator_id}/data", params=params, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise CepalApiError(
            f"CEPALSTAT devolvió {resp.status_code} para el indicador {indicator_id}: {resp.text[:300]}"
        )

    try:
        df = pd.read_excel(io.BytesIO(resp.content))
    except Exception as exc:
        raise CepalApiError(
            f"No se pudo leer la respuesta de CEPALSTAT como Excel (¿cambió el formato de la API?): {exc}"
        ) from exc

    if df.empty:
        raise CepalApiError(f"El indicador {indicator_id} no devolvió filas de datos.")

    return df


def _detectar_columna_anio(df: pd.DataFrame) -> str:
    for candidata in POSIBLES_COLUMNAS_ANIO:
        if candidata in df.columns:
            return candidata
    for col in df.columns:
        if re.search(r"year|anio|año", str(col), re.IGNORECASE):
            return col
    raise CepalApiError(
        f"No se encontró una columna de año en la respuesta de CEPALSTAT. "
        f"Columnas disponibles: {list(df.columns)}"
    )


def transformar_a_formato_estandar(df: pd.DataFrame, fuente: str = "CEPALSTAT") -> pd.DataFrame:
    """
    Convierte el DataFrame crudo de CEPALSTAT al formato objetivo:
        anio,dominio,ipm,fuente,fecha_extraccion,fecha_carga

    'dominio' agrupa todas las columnas que no son año/valor/metadatos
    (normalmente país, y a veces también área geográfica o grupo poblacional).
    Si hay más de una, se concatenan con " - ".
    """
    if "value" not in df.columns:
        raise CepalApiError(f"La respuesta no tiene columna 'value'. Columnas: {list(df.columns)}")

    col_anio = _detectar_columna_anio(df)

    columnas_dominio = [c for c in df.columns if c not in COLUMNAS_NO_DOMINIO and c != col_anio]

    if not columnas_dominio:
        dominio = pd.Series(["Total"] * len(df))
    elif len(columnas_dominio) == 1:
        dominio = df[columnas_dominio[0]].astype(str)
    else:
        dominio = df[columnas_dominio].astype(str).agg(" - ".join, axis=1)

    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    resultado = pd.DataFrame(
        {
            "anio": df[col_anio],
            "dominio": dominio,
            "ipm": df["value"],
            "fuente": fuente,
            "fecha_extraccion": ahora,
            "fecha_carga": ahora,
        }
    )
    return resultado