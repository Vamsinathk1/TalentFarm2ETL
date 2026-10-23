"""Read configured delimited, CSV, and JSON source files."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd


def resolve_path(base_dir: Path, configured_path: str) -> Path:
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def read_delimited_file(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8-sig", newline="") as source_file:
        sample = source_file.read(8192)
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",|\t;").delimiter
    except csv.Error:
        delimiter = "|"
    return pd.read_csv(
        path,
        sep=delimiter,
        dtype=str,
        keep_default_na=False,
        on_bad_lines="error",
    )


def _json_records(path: Path, records_key: str | None = None) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if records_key:
        if not isinstance(payload, dict) or records_key not in payload:
            raise ValueError(f"JSON does not contain configured records key: {records_key}")
        payload = payload[records_key]
    if isinstance(payload, dict):
        if payload and all(isinstance(value, dict) for value in payload.values()):
            payload = list(payload.values())
        else:
            payload = [payload]
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ValueError("JSON data must be an object or a list of objects")
    return payload


def read_sales_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return pd.DataFrame(_json_records(path)).fillna("")
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, on_bad_lines="error")
    return read_delimited_file(path)


def read_customer_file(path: Path, records_key: str | None = None) -> pd.DataFrame:
    if path.suffix.lower() == ".json":
        return pd.DataFrame(_json_records(path, records_key)).fillna("")
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, on_bad_lines="error")
    return read_delimited_file(path)
