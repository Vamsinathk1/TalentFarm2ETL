"""Validate distributor sales file structure and basic data quality."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.models import ValidationResult, result


def field_name(columns: dict[str, Any], canonical: str, target: bool = False) -> str:
    if target:
        target_columns = columns.get("target_columns", {})
        if canonical in target_columns:
            return str(target_columns[canonical])
    return str(columns.get(canonical, ""))


def available(frame: pd.DataFrame, column: str) -> bool:
    return bool(column) and column in frame.columns


def sample_record_keys(frame: pd.DataFrame, mask: pd.Series, key_column: str) -> str:
    if key_column and key_column in frame.columns:
        keys = frame.loc[mask, key_column].astype(str).unique()
    else:
        keys = frame.index[mask].astype(str).unique()
    return ", ".join(keys[:20])


def validate_sales(
    frame: pd.DataFrame,
    label: str,
    columns: dict[str, Any],
) -> list[ValidationResult]:
    output: list[ValidationResult] = []
    mandatory = [str(value) for value in columns.get("mandatory", [])]
    canonical = [
        field_name(columns, name)
        for name in (
            "transaction_id",
            "customer_id",
            "product_id",
            "product_family",
            "quantity",
            "unit_price",
            "sales_amount",
            "sales_date",
        )
    ]
    required = list(dict.fromkeys(mandatory + [name for name in canonical if name]))
    missing = [name for name in required if name not in frame.columns]
    output.append(
        result(
            "STG-SCHEMA",
            "Source-to-Staging",
            f"{label} required columns",
            label,
            "normalized dataframe",
            "all configured columns present",
            ", ".join(missing) if missing else "all present",
            "FAIL" if missing else "PASS",
            len(missing),
            "Update column mappings in config if headers differ." if missing else "",
        )
    )
    if missing:
        return output

    empty_by_column: dict[str, int] = {}
    empty_rows = pd.Series(False, index=frame.index)
    for column in mandatory:
        empty_mask = frame[column].astype(str).str.strip().eq("")
        empty_by_column[column] = int(empty_mask.sum())
        empty_rows |= empty_mask
    transaction_id = field_name(columns, "transaction_id")
    empty_count = sum(empty_by_column.values())
    output.append(
        result(
            "STG-NULLS",
            "Source-to-Staging",
            f"{label} mandatory fields",
            label,
            "normalized dataframe",
            "0 empty mandatory values",
            empty_count,
            "FAIL" if empty_count else "PASS",
            empty_count,
            remarks="Blank counts by field: "
            + ", ".join(f"{name}={count}" for name, count in empty_by_column.items() if count),
            record_key=sample_record_keys(frame, empty_rows, transaction_id),
        )
    )

    if available(frame, transaction_id):
        duplicate_mask = frame[transaction_id].astype(str).str.strip().duplicated(keep=False)
        duplicate_count = int(duplicate_mask.sum())
        output.append(
            result(
                "STG-DUPLICATES",
                "Source-to-Staging",
                f"{label} transaction uniqueness",
                label,
                "normalized dataframe",
                "0 duplicate transaction rows",
                duplicate_count,
                "FAIL" if duplicate_count else "PASS",
                duplicate_count,
                record_key=sample_record_keys(frame, duplicate_mask, transaction_id),
            )
        )

    numeric_fields = columns.get("numeric", []) or [
        field_name(columns, name) for name in ("quantity", "unit_price", "sales_amount")
    ]
    for column in dict.fromkeys(str(value) for value in numeric_fields if value):
        if not available(frame, column):
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        invalid_mask = numeric.isna()
        invalid_count = int(invalid_mask.sum())
        output.append(
            result(
                f"STG-NUM-{column.upper().replace(' ', '_')}",
                "Source-to-Staging",
                f"{label} {column} numeric format",
                label,
                "normalized dataframe",
                "all values numeric",
                invalid_count,
                "FAIL" if invalid_count else "PASS",
                invalid_count,
                remarks=f"Invalid values in {column}: {invalid_count}.",
                record_key=sample_record_keys(frame, invalid_mask, transaction_id),
            )
        )

    date_column = field_name(columns, "sales_date")
    if available(frame, date_column):
        invalid_mask = pd.to_datetime(
            frame[date_column], format="mixed", errors="coerce"
        ).isna()
        invalid_count = int(invalid_mask.sum())
        output.append(
            result(
                "STG-DATE",
                "Source-to-Staging",
                f"{label} sales date format",
                label,
                "normalized dataframe",
                "all dates parse",
                invalid_count,
                "FAIL" if invalid_count else "PASS",
                invalid_count,
                remarks=f"Unparseable dates: {invalid_count}.",
                record_key=sample_record_keys(frame, invalid_mask, transaction_id),
            )
        )
    return output
