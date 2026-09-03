
from __future__ import annotations

import re
from typing import Any

import pandas as pd
import requests

CEPALSTAT_BASE_URL = "https://api-cepalstat.cepal.org/cepalstat/api/v1"

_DIM_KEY_RE = re.compile(r"^dim_(\d+)$")


class CepalDimensionsError(Exception):
    """Error al consultar o interpretar la API de CEPALSTAT."""


def _get_json(url: str, timeout: int = 30) -> dict:

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    except requests.RequestException as exc:

        raise CepalDimensionsError(
            f"Error de red consultando {url}: {exc}"
        ) from exc

    if resp.status_code != 200:

        raise CepalDimensionsError(
            f"HTTP {resp.status_code} consultando {url}"
        )

    try:
        payload = resp.json()

    except ValueError as exc:

        raise CepalDimensionsError(
            f"Respuesta no es JSON válido desde {url}: {exc}"
        ) from exc

    header = payload.get("header", {})

    if not header.get("success", True):

        raise CepalDimensionsError(
            f"La API de CEPALSTAT respondió con error para {url}: "
            f"{header.get('message')}"
        )

    return payload


def _fetch_data(indicator_id: int) -> dict:

    url = f"{CEPALSTAT_BASE_URL}/indicator/{indicator_id}/data"

    return _get_json(url)


def _fetch_dimensions(indicator_id: int) -> list[dict]:

    url = f"{CEPALSTAT_BASE_URL}/indicator/{indicator_id}/dimensions"

    payload = _get_json(url)

    return payload.get("body", {}).get("dimensions", [])


def _build_member_index(
    dimensions: list[dict],
) -> dict[int, dict[int, str]]:
    """Por cada dimensión, arma un mapa id de miembro -> nombre."""

    index: dict[int, dict[int, str]] = {}

    for dim in dimensions:

        dim_id = dim["id"]

        index[dim_id] = {
            member["id"]: member["name"]
            for member in dim.get("members", [])
        }

    return index


def _resolve_dimension_columns(
    first_row: dict[str, Any],
    dimensions: list[dict],
) -> list[tuple[int, str, str]]:


    columns: list[tuple[int, str, str]] = []

    seen: set[int] = set()

    for dim in dimensions:

        dim_id = dim["id"]

        key = f"dim_{dim_id}"

        if key not in first_row or dim_id in seen:
            continue

        seen.add(dim_id)

        label = dim.get("name") or key

        columns.append((dim_id, key, label))

    extra_ids = sorted(
        {
            int(match.group(1))
            for key in first_row
            if (match := _DIM_KEY_RE.match(key))
            and int(match.group(1)) not in seen
        }
    )

    for dim_id in extra_ids:

        key = f"dim_{dim_id}"

        columns.append((dim_id, key, key))

    return columns


def _resolve_member_label(
    raw_member_id: Any,
    members: dict[int, str] | None,
) -> Any:


    if raw_member_id is None:
        return None

    try:
        member_id = int(raw_member_id)

    except (TypeError, ValueError):
        return raw_member_id

    if members and member_id in members:
        return members[member_id]

    return member_id


def build_dataframe(indicator_id: int) -> pd.DataFrame:


    data_payload = _fetch_data(indicator_id)

    rows: list[dict[str, Any]] = (
        data_payload.get("body", {}).get("data", [])
    )

    dimensions = _fetch_dimensions(indicator_id)

    member_index = _build_member_index(dimensions)

    if not rows:

        return pd.DataFrame(
            columns=["value", "source_id", "notes_ids", "iso3"]
        )

    dim_columns = _resolve_dimension_columns(rows[0], dimensions)

    records = []

    for row in rows:

        record: dict[str, Any] = {
            "value": row.get("value"),
            "source_id": row.get("source_id"),
            "notes_ids": row.get("notes_ids"),
            "iso3": row.get("iso3"),
        }

        for dim_id, key, label in dim_columns:

            record[label] = _resolve_member_label(
                row.get(key),
                member_index.get(dim_id),
            )

        records.append(record)

    columns_order = (
        ["value", "source_id", "notes_ids", "iso3"]
        + [label for _, _, label in dim_columns]
    )

    return pd.DataFrame.from_records(records, columns=columns_order)


def to_preview_records(df: pd.DataFrame, n: int = 5) -> list[dict]:


    preview = df.head(n)

    preview = preview.astype(object).where(
        pd.notnull(preview),
        None,
    )

    return preview.to_dict(orient="records")


def get_indicator_metadata(indicator_id: int) -> dict:


    payload = _fetch_data(indicator_id)

    return payload.get("body", {}).get("metadata", {})