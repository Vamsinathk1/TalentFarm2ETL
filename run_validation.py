"""Run configurable source, reference-data, and MySQL reconciliation checks."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class ValidationResult:
    validation_id: str
    layer: str
    validation_name: str
    source_object: str
    target_object: str
    expected_value: str
    actual_value: str
    status: str
    variance: str = ""
    remarks: str = ""
    record_key: str = ""


def result(
    validation_id: str,
    layer: str,
    name: str,
    source: str,
    target: str,
    expected: Any,
    actual: Any,
    status: str,
    variance: Any = "",
    remarks: str = "",
    record_key: Any = "",
) -> ValidationResult:
    return ValidationResult(
        validation_id=validation_id,
        layer=layer,
        validation_name=name,
        source_object=source,
        target_object=target,
        expected_value=str(expected),
        actual_value=str(actual),
        status=status,
        variance=str(variance),
        remarks=remarks,
        record_key=str(record_key),
    )


def read_pipe_file(path: Path) -> pd.DataFrame:
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


def read_sales_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            if payload and all(isinstance(value, dict) for value in payload.values()):
                payload = list(payload.values())
            else:
                raise ValueError("Sales JSON object must contain a list of records")
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ValueError("Sales JSON must be a list of objects")
        return pd.DataFrame(payload).fillna("")
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, on_bad_lines="error")
    return read_pipe_file(path)


def read_customer_json(path: Path, records_key: str | None) -> pd.DataFrame:
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
        raise ValueError("Customer JSON must be an object or a list of objects")
    return pd.DataFrame(payload).fillna("")


def read_customer_file(path: Path, records_key: str | None) -> pd.DataFrame:
    if path.suffix.lower() == ".json":
        return read_customer_json(path, records_key)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False, on_bad_lines="error")
    return read_pipe_file(path)


def _field(columns: dict[str, Any], canonical: str, target: bool = False) -> str:
    if target:
        target_columns = columns.get("target_columns", {})
        if canonical in target_columns:
            return str(target_columns[canonical])
    return str(columns.get(canonical, ""))


def _available(df: pd.DataFrame, column: str) -> bool:
    return bool(column) and column in df.columns


def _sample_record_keys(df: pd.DataFrame, mask: pd.Series, key_column: str) -> str:
    if key_column and key_column in df.columns:
        keys = df.loc[mask, key_column].astype(str).unique()
    else:
        keys = df.index[mask].astype(str).unique()
    return ", ".join(keys[:20])


def validate_sales(
    df: pd.DataFrame,
    label: str,
    columns: dict[str, Any],
    validation: dict[str, Any],
) -> list[ValidationResult]:
    layer = "Source-to-Staging"
    output: list[ValidationResult] = []
    mandatory = [str(value) for value in columns.get("mandatory", [])]
    canonical_columns = [
        _field(columns, key)
        for key in (
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
    required = list(dict.fromkeys(mandatory + [name for name in canonical_columns if name]))
    missing = [name for name in required if name not in df.columns]
    output.append(
        result(
            "STG-SCHEMA",
            layer,
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

    empty_count = 0
    empty_by_column: dict[str, int] = {}
    empty_rows = pd.Series(False, index=df.index)
    for column in mandatory:
        empty_mask = df[column].astype(str).str.strip().eq("")
        empty_by_column[column] = int(empty_mask.sum())
        empty_count += empty_by_column[column]
        empty_rows |= empty_mask
    transaction_id = _field(columns, "transaction_id")
    output.append(
        result(
            "STG-NULLS",
            layer,
            f"{label} mandatory fields",
            label,
            "normalized dataframe",
            "0 empty mandatory values",
            empty_count,
            "FAIL" if empty_count else "PASS",
            empty_count,
            remarks="Blank counts by field: "
            + ", ".join(f"{name}={count}" for name, count in empty_by_column.items() if count),
            record_key=_sample_record_keys(df, empty_rows, transaction_id),
        )
    )

    if _available(df, transaction_id):
        duplicate_mask = df[transaction_id].astype(str).str.strip().duplicated(keep=False)
        duplicate_count = int(duplicate_mask.sum())
        output.append(
            result(
                "STG-DUPLICATES",
                layer,
                f"{label} transaction uniqueness",
                label,
                "normalized dataframe",
                "0 duplicate transaction rows",
                duplicate_count,
                "FAIL" if duplicate_count else "PASS",
                duplicate_count,
                record_key=", ".join(df.loc[duplicate_mask, transaction_id].astype(str).unique()[:20]),
            )
        )

    numeric_fields = columns.get("numeric", []) or [
        _field(columns, canonical)
        for canonical in ("quantity", "unit_price", "sales_amount")
    ]
    for column in dict.fromkeys(str(value) for value in numeric_fields if value):
        if not _available(df, column):
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        invalid_count = int(numeric.isna().sum())
        canonical = column.upper().replace(" ", "_")
        output.append(
            result(
                f"STG-NUM-{canonical}",
                layer,
                f"{label} {column} numeric format",
                label,
                "normalized dataframe",
                "all values numeric",
                invalid_count,
                "FAIL" if invalid_count else "PASS",
                invalid_count,
                remarks=f"Invalid values in {column}: {invalid_count}.",
                record_key=_sample_record_keys(df, numeric.isna(), _field(columns, "transaction_id")),
            )
        )
        if column == _field(columns, "quantity") and validation.get("quantity_must_be_positive", True):
            invalid_count = int((numeric.notna() & (numeric <= 0)).sum())
            output.append(
                result(
                    "STG-QUANTITY-RANGE",
                    layer,
                    f"{label} quantity positive",
                    label,
                    "normalized dataframe",
                    "all quantities > 0",
                    invalid_count,
                    "FAIL" if invalid_count else "PASS",
                    invalid_count,
                    remarks=f"Nonpositive quantities: {invalid_count}.",
                    record_key=_sample_record_keys(
                        df, numeric.notna() & (numeric <= 0), _field(columns, "transaction_id")
                    ),
                )
            )
        if column == _field(columns, "unit_price") and validation.get("unit_price_must_be_nonnegative", True):
            invalid_count = int((numeric.notna() & (numeric < 0)).sum())
            output.append(
                result(
                    "STG-PRICE-RANGE",
                    layer,
                    f"{label} unit price nonnegative",
                    label,
                    "normalized dataframe",
                    "all unit prices >= 0",
                    invalid_count,
                    "FAIL" if invalid_count else "PASS",
                    invalid_count,
                    remarks=f"Negative unit prices: {invalid_count}.",
                    record_key=_sample_record_keys(
                        df, numeric.notna() & (numeric < 0), _field(columns, "transaction_id")
                    ),
                )
            )

    date_column = _field(columns, "sales_date")
    if _available(df, date_column):
        invalid_dates = int(
            pd.to_datetime(df[date_column], format="mixed", errors="coerce").isna().sum()
        )
        output.append(
            result(
                "STG-DATE",
                layer,
                f"{label} sales date format",
                label,
                "normalized dataframe",
                "all dates parse",
                invalid_dates,
                "FAIL" if invalid_dates else "PASS",
                invalid_dates,
                remarks=f"Unparseable dates: {invalid_dates}.",
                record_key=_sample_record_keys(
                    df,
                    pd.to_datetime(df[date_column], format="mixed", errors="coerce").isna(),
                    _field(columns, "transaction_id"),
                ),
            )
        )

    quantity_column = _field(columns, "quantity")
    price_column = _field(columns, "unit_price")
    amount_column = _field(columns, "sales_amount")
    if all(_available(df, name) for name in (quantity_column, price_column, amount_column)):
        quantity = pd.to_numeric(df[quantity_column], errors="coerce")
        price = pd.to_numeric(df[price_column], errors="coerce")
        amount = pd.to_numeric(df[amount_column], errors="coerce")
        tolerance = float(validation.get("amount_tolerance", 0.01))
        mismatch = (quantity * price - amount).abs() > tolerance
        mismatch_count = int((mismatch & quantity.notna() & price.notna() & amount.notna()).sum())
        output.append(
            result(
                "STG-AMOUNT-CALC",
                layer,
                f"{label} sales amount calculation",
                label,
                "normalized dataframe",
                "quantity * unit price within tolerance " + str(tolerance),
                mismatch_count,
                "FAIL" if mismatch_count else "PASS",
                mismatch_count,
                "Confirm rounding/tolerance with the approved business rule.",
                _sample_record_keys(
                    df,
                    (quantity * price - amount).abs().gt(tolerance)
                    & quantity.notna()
                    & price.notna()
                    & amount.notna(),
                    _field(columns, "transaction_id"),
                ),
            )
        )

    product_column = _field(columns, "product_id")
    family_column = _field(columns, "product_family")
    if _available(df, product_column) and _available(df, family_column):
        pairs = df.groupby(product_column)[family_column].nunique(dropna=False)
        bad_products = pairs[pairs > 1].index.astype(str).tolist()
        output.append(
            result(
                "STG-PRODUCT-FAMILY",
                layer,
                f"{label} product-family consistency",
                label,
                "normalized dataframe",
                "one family per product",
                len(bad_products),
                "FAIL" if bad_products else "PASS",
                len(bad_products),
                "This is an internal consistency check; an approved product master is needed for authoritative validation.",
                ", ".join(bad_products[:20]),
            )
        )
    return output


def validate_customers(
    customers: pd.DataFrame,
    sales: pd.DataFrame | None,
    customer_config: dict[str, Any],
    columns: dict[str, Any],
) -> list[ValidationResult]:
    layer = "Source-to-Staging"
    output: list[ValidationResult] = []
    customer_id = str(customer_config.get("id_field", ""))
    missing = [customer_id] if not customer_id or customer_id not in customers.columns else []
    output.append(
        result(
            "STG-CUSTOMER-SCHEMA",
            layer,
            "Customer Master required ID field",
            "Customer Master JSON",
            "customer dataframe",
            "configured customer ID field present",
            ", ".join(missing) if missing else "present",
            "FAIL" if missing else "PASS",
            len(missing),
        )
    )
    if missing:
        return output

    ids = customers[customer_id].astype(str).str.strip()
    empty_count = int(ids.eq("").sum())
    duplicate_count = int(ids.duplicated(keep=False).sum())
    output.append(
        result(
            "STG-CUSTOMER-IDS",
            layer,
            "Customer IDs present and unique",
            "Customer Master JSON",
            "customer dataframe",
            "no blank or duplicate IDs",
            f"blank={empty_count}; duplicate_rows={duplicate_count}",
            "FAIL" if empty_count or duplicate_count else "PASS",
            empty_count + duplicate_count,
            remarks="Duplicate customer ID rows: " + str(duplicate_count),
            record_key=", ".join(ids[ids.duplicated(keep=False)].unique()[:20]),
        )
    )
    mandatory_fields = [str(value) for value in customer_config.get("mandatory_fields", [])]
    missing_fields = [name for name in mandatory_fields if name not in customers.columns]
    empty_values = sum(
        int(customers[name].astype(str).str.strip().eq("").sum())
        for name in mandatory_fields
        if name in customers.columns
    )
    output.append(
        result(
            "STG-CUSTOMER-MANDATORY",
            layer,
            "Customer Master mandatory fields",
            "Customer Master file",
            "customer dataframe",
            "all configured fields present and nonblank",
            f"missing_fields={len(missing_fields)}; blank_values={empty_values}",
            "FAIL" if missing_fields or empty_values else "PASS",
            len(missing_fields) + empty_values,
            "Missing fields: " + ", ".join(missing_fields) if missing_fields else "",
        )
    )

    if sales is not None:
        sales_id = _field(columns, "customer_id")
        if _available(sales, sales_id):
            valid_ids = set(ids[ids.ne("")])
            active_field = customer_config.get("active_field")
            active_values = {str(value).casefold() for value in customer_config.get("active_values", [])}
            if active_field and active_field in customers.columns:
                active_mask = customers[active_field].astype(str).str.casefold().isin(active_values)
                valid_ids = set(ids[active_mask & ids.ne("")])
            sales_ids = sales[sales_id].astype(str).str.strip()
            invalid = sales_ids.ne("") & ~sales_ids.isin(valid_ids)
            invalid_ids = sales_ids[invalid].unique().tolist()
            output.append(
                result(
                    "STG-CUSTOMER-REF",
                    layer,
                    "Sales customer references resolve",
                    "Distributor Sales TXT",
                    "Customer Master JSON",
                    "all sales customer IDs exist and are active",
                    len(invalid_ids),
                    "FAIL" if invalid_ids else "PASS",
                    len(invalid_ids),
                    record_key=", ".join(invalid_ids[:20]),
                )
            )
        source_policy_field = str(customer_config.get("source_policy_field", "policy_number"))
        master_policy_field = str(customer_config.get("master_policy_field", "policy_number"))
        if source_policy_field in sales.columns and master_policy_field in customers.columns:
            master_policies = set(customers[master_policy_field].astype(str).str.strip())
            sale_policies = sales[source_policy_field].astype(str).str.strip()
            missing_policies = sale_policies.ne("") & ~sale_policies.isin(master_policies)
            output.append(
                result(
                    "STG-CUSTOMER-POLICY-REF",
                    layer,
                    "Sales policy references resolve",
                    "Distributor Sales file",
                    "Customer Master file",
                    "all nonblank policy numbers exist",
                    int(missing_policies.sum()),
                    "FAIL" if missing_policies.any() else "PASS",
                    int(missing_policies.sum()),
                )
            )
    return output


def load_target(config: dict[str, Any], base_dir: Path) -> tuple[pd.DataFrame, str]:
    target = config.get("target", {})
    mode = str(target.get("mode", "mysql")).lower()
    if mode == "file":
        path = resolve_path(base_dir, str(target["path"]))
        frame = read_sales_file(path)
        return frame, str(path)
    if mode != "mysql":
        raise ValueError("target.mode must be 'mysql' or 'file'")

    query = str(target.get("query", "")).strip()
    if not re.match(r"(?is)^select\b", query) or ";" in query.rstrip(";"):
        raise ValueError("Target query must be one read-only SELECT statement")
    database = config.get("database", {})
    user_env = str(database.get("user_env", ""))
    user = os.environ.get(user_env) if user_env else database.get("user")
    if not user:
        raise ValueError(f"Database user environment variable is unset: {user_env or '(not configured)'}")
    password_env = str(database.get("password_env", ""))
    password = os.environ.get(password_env) if password_env else None
    if not password:
        raise ValueError(f"Database password environment variable is unset: {password_env or '(not configured)'}")

    import mysql.connector

    connection = mysql.connector.connect(
        host=database["host"],
        port=int(database.get("port", 3306)),
        database=database["database"],
        user=user,
        password=password,
        connection_timeout=10,
    )
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            return pd.DataFrame(rows, columns=[item[0] for item in cursor.description]), query
        finally:
            cursor.close()
    finally:
        connection.close()


def _equal_values(left: Any, right: Any, canonical: str, tolerance: float) -> tuple[bool, str]:
    left_text = str(left).strip()
    right_text = str(right).strip()
    left_missing = pd.isna(left) or left_text.casefold() in {"", "none", "nan", "nat"}
    right_missing = pd.isna(right) or right_text.casefold() in {"", "none", "nan", "nat"}
    if left_missing or right_missing:
        return left_missing and right_missing, ""
    if canonical in {
        "quantity",
        "unit_price",
        "sales_amount",
        "gross_amount",
        "commission_amount",
        "net_amount",
        "tax_amount",
        "discount_amount",
        "premium_amount",
    }:
        try:
            left_number = float(left_text)
            right_number = float(right_text)
            delta = abs(left_number - right_number)
            return math.isclose(left_number, right_number, rel_tol=0.0, abs_tol=tolerance), str(delta)
        except (TypeError, ValueError):
            return False, "not numeric"
    if canonical == "sales_date":
        if re.fullmatch(r"\d{8}", right_text):
            right_text = f"{right_text[:4]}-{right_text[4:6]}-{right_text[6:8]}"
        left_date = pd.to_datetime(left_text, format="mixed", errors="coerce")
        right_date = pd.to_datetime(right_text, format="mixed", errors="coerce")
        if pd.isna(left_date) or pd.isna(right_date):
            return left_text == right_text, "unparseable date"
        return left_date.date() == right_date.date(), str(left_date.date() - right_date.date())
    return left_text == right_text, ""


def reconcile(
    source: pd.DataFrame,
    target: pd.DataFrame,
    source_name: str,
    target_name: str,
    columns: dict[str, Any],
    tolerance: float,
) -> list[ValidationResult]:
    output: list[ValidationResult] = []
    key_source = _field(columns, "transaction_id")
    key_target = _field(columns, "transaction_id", target=True)
    if not _available(source, key_source) or not _available(target, key_target):
        return [
            result(
                "DM-KEY-SCHEMA",
                "Staging-to-Data Mart",
                "Reconciliation key available",
                source_name,
                target_name,
                "transaction key mapped on both sides",
                f"source={key_source in source.columns}; target={key_target in target.columns}",
                "BLOCKED",
                remarks="Configure source and target transaction ID column names.",
            )
        ]

    source_keys = source[key_source].astype(str).str.strip()
    target_keys = target[key_target].astype(str).str.strip()
    source_counts = source_keys[source_keys.ne("")].value_counts()
    target_counts = target_keys[target_keys.ne("")].value_counts()
    missing = sorted(set(source_counts.index) - set(target_counts.index))
    extra = sorted(set(target_counts.index) - set(source_counts.index))
    count_delta = len(target) - len(source)
    output.append(
        result(
            "DM-ROW-COUNT",
            "Staging-to-Data Mart",
            "Source and target row counts",
            source_name,
            target_name,
            len(source),
            len(target),
            "PASS" if count_delta == 0 else "FAIL",
            count_delta,
        )
    )
    source_duplicates = int(source_counts[source_counts > 1].sum())
    target_duplicates = int(target_counts[target_counts > 1].sum())
    output.append(
        result(
            "DM-DUPLICATES",
            "Staging-to-Data Mart",
            "Duplicate transaction keys",
            source_name,
            target_name,
            "0 duplicate-key rows on each side",
            f"source={source_duplicates}; target={target_duplicates}",
            "FAIL" if source_duplicates or target_duplicates else "PASS",
            source_duplicates + target_duplicates,
        )
    )
    output.append(
        result(
            "DM-MISSING",
            "Staging-to-Data Mart",
            "Source records missing in target",
            source_name,
            target_name,
            0,
            len(missing),
            "PASS" if not missing else "FAIL",
            len(missing),
            record_key=", ".join(missing[:50]),
        )
    )
    output.append(
        result(
            "DM-EXTRA",
            "Staging-to-Data Mart",
            "Unexpected target records",
            source_name,
            target_name,
            0,
            len(extra),
            "PASS" if not extra else "FAIL",
            len(extra),
            record_key=", ".join(extra[:50]),
        )
    )

    shared_keys = set(source_counts.index) & set(target_counts.index)
    unique_keys = {key for key in shared_keys if source_counts[key] == 1 and target_counts[key] == 1}
    source_by_key = source.assign(_recon_key=source_keys).set_index("_recon_key", drop=False)
    target_by_key = target.assign(_recon_key=target_keys).set_index("_recon_key", drop=False)
    compare_fields = columns.get("compare_fields") or (
        "customer_id",
        "product_id",
        "product_family",
        "quantity",
        "unit_price",
        "sales_amount",
        "sales_date",
    )
    mismatch_count = 0
    blocked_fields = columns.get("blocked_compare_fields", {})
    for canonical in compare_fields:
        if canonical in blocked_fields:
            continue
        source_column = str(columns.get("source_columns", {}).get(canonical, _field(columns, canonical)))
        target_column = str(columns.get("target_columns", {}).get(canonical, _field(columns, canonical, target=True)))
        if not _available(source, source_column) or not _available(target, target_column):
            continue
        for key in sorted(unique_keys):
            same, variance = _equal_values(
                source_by_key.at[key, source_column],
                target_by_key.at[key, target_column],
                canonical,
                tolerance if canonical == "sales_amount" else 1e-9,
            )
            if not same:
                mismatch_count += 1
                output.append(
                    result(
                        "DM-FIELD-MISMATCH",
                        "Staging-to-Data Mart",
                        f"Field comparison: {canonical}",
                        source_name,
                        target_name,
                        source_by_key.at[key, source_column],
                        target_by_key.at[key, target_column],
                        "FAIL",
                        variance,
                        f"Source and target {canonical} differ.",
                        key,
                    )
                )
    for canonical, reason in blocked_fields.items():
        output.append(
            result(
                "DM-FIELD-BLOCKED",
                "Staging-to-Data Mart",
                f"Field comparison blocked: {canonical}",
                source_name,
                target_name,
                "confirmed source-to-target mapping",
                "mapping not verified",
                "BLOCKED",
                remarks=str(reason),
            )
        )
    output.append(
        result(
            "DM-FIELD-SUMMARY",
            "Staging-to-Data Mart",
            "Field-level reconciliation",
            source_name,
            target_name,
            "0 field mismatches on unique matched keys",
            mismatch_count,
            "PASS" if mismatch_count == 0 else "FAIL",
            mismatch_count,
            "Ambiguous duplicate keys are excluded from field comparison and reported separately.",
        )
    )
    return output


def resolve_path(base_dir: Path, configured_path: str) -> Path:
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def write_reports(results: list[ValidationResult], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_frame = pd.DataFrame(asdict(item) for item in results)
    detail_frame.to_csv(output_dir / "validation_details.csv", index=False)
    if detail_frame.empty:
        summary_lines = ["No validations executed."]
    else:
        counts = detail_frame.groupby(["layer", "status"]).size().unstack(fill_value=0)
        summary_lines = [
            "Assignment 2 QA Validation Summary",
            f"Generated UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"Total validations: {len(results)}",
        ]
        for status in ("PASS", "FAIL", "BLOCKED"):
            summary_lines.append(f"{status}: {int((detail_frame['status'] == status).sum())}")
        summary_lines.extend(["", "By layer:", counts.to_string()])
    (output_dir / "validation_summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


def run(config_path: Path) -> list[ValidationResult]:
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent
    columns = config.get("columns", {})
    validation = config.get("validation", {})
    inputs = config.get("inputs", {})
    results: list[ValidationResult] = []
    logger = logging.getLogger("assignment2")
    logger.info("Validation started")

    dataframes: dict[str, pd.DataFrame] = {}
    sales_input_names = (
        "distributor_sales_file",
        "distributor_sales_json",
        "distributor_sales_txt",
        "fact_sales_txt",
    )
    for name in sales_input_names:
        configured = inputs.get(name)
        if not configured:
            continue
        path = resolve_path(base_dir, str(configured))
        try:
            frame = read_sales_file(path)
            dataframes[name] = frame
            results.append(
                result(
                    f"LOAD-{name.upper()}",
                    "Source-to-Staging",
                    f"Load {name}",
                    str(path),
                    "normalized dataframe",
                    "file readable",
                    f"{len(frame)} rows",
                    "PASS",
                )
            )
            results.extend(validate_sales(frame, name, columns, validation))
        except Exception as exc:
            logger.exception("Failed loading %s", name)
            results.append(
                result(
                    f"LOAD-{name.upper()}",
                    "Source-to-Staging",
                    f"Load {name}",
                    str(path),
                    "normalized dataframe",
                    "file readable",
                    type(exc).__name__,
                    "FAIL",
                    remarks=str(exc),
                )
            )

    customer_frame: pd.DataFrame | None = None
    customer_input_name = next(
        (name for name in ("customer_master_file", "customer_master_json") if inputs.get(name)),
        None,
    )
    customer_path = inputs.get(customer_input_name) if customer_input_name else None
    if customer_path:
        path = resolve_path(base_dir, str(customer_path))
        try:
            customer_frame = read_customer_file(path, config.get("customer_json", {}).get("records_key"))
            results.append(
                result(
                    "LOAD-CUSTOMERS",
                    "Source-to-Staging",
                    "Load Customer Master file",
                    str(path),
                    "customer dataframe",
                    "valid customer file readable",
                    f"{len(customer_frame)} records",
                    "PASS",
                )
            )
            reference_source_name = str(
                config.get("customer_json", {}).get(
                    "reference_source",
                    config.get("target", {}).get(
                        "reconciliation_source", "distributor_sales_json"
                    ),
                )
            )
            results.extend(
                validate_customers(
                    customer_frame,
                    dataframes.get(reference_source_name),
                    config.get("customer_json", {}),
                    columns,
                )
            )
        except Exception as exc:
            logger.exception("Failed loading Customer Master JSON")
            results.append(
                result(
                    "LOAD-CUSTOMERS",
                    "Source-to-Staging",
                    "Load Customer Master file",
                    str(path),
                    "customer dataframe",
                    "valid customer file readable",
                    type(exc).__name__,
                    "FAIL",
                    remarks=str(exc),
                )
            )

    try:
        target_frame, target_name = load_target(config, base_dir)
        results.append(
            result(
                "LOAD-TARGET",
                "Staging-to-Data Mart",
                "Read target data",
                str(config.get("target", {}).get("query", "")),
                target_name,
                "target query succeeds",
                f"{len(target_frame)} rows",
                "PASS",
            )
        )
        source_key = str(config.get("target", {}).get("reconciliation_source", "distributor_sales_json"))
        source_frame = dataframes.get(source_key)
        if source_frame is None:
            results.append(
                result(
                    "DM-SOURCE-UNAVAILABLE",
                    "Staging-to-Data Mart",
                    "Reconciliation source available",
                    source_key,
                    target_name,
                    "configured source loaded",
                    "not loaded",
                    "BLOCKED",
                    remarks="Check input path/configuration and source file format.",
                )
            )
        else:
            reconciliation_columns = dict(columns)
            reconciliation_columns["target_columns"] = dict(columns.get("target_columns", {}))
            customer_settings = config.get("customer_json", {})
            customer_key_field = customer_settings.get("target_key_field")
            source_customer_id = str(customer_settings.get("mapping_source_field", ""))
            master_customer_id = str(customer_settings.get("mapping_master_field", ""))
            if (
                customer_frame is not None
                and customer_key_field
                and source_customer_id in source_frame.columns
                and master_customer_id in customer_frame.columns
                and customer_key_field in customer_frame.columns
            ):
                unique_customers = customer_frame.drop_duplicates(master_customer_id, keep=False)
                customer_map = unique_customers.set_index(master_customer_id)[customer_key_field]
                mapped_source = source_frame.copy()
                mapped_column = "__reconciled_customer_key"
                mapped_source[mapped_column] = mapped_source[source_customer_id].map(customer_map)
                reconciliation_columns["customer_id"] = mapped_column
                reconciliation_columns["target_columns"]["customer_id"] = str(
                    config.get("customer_json", {}).get("target_customer_key_field", "customer_key")
                )
                source_frame = mapped_source
            results.extend(
                reconcile(
                    source_frame,
                    target_frame,
                    source_key,
                    target_name,
                    reconciliation_columns,
                    float(validation.get("amount_tolerance", 0.01)),
                )
            )
    except Exception as exc:
        logger.exception("Failed reading target data")
        results.append(
            result(
                "LOAD-TARGET",
                "Staging-to-Data Mart",
                "Read target data",
                str(config.get("target", {}).get("query", "")),
                "configured target",
                "target query succeeds",
                type(exc).__name__,
                "FAIL",
                remarks=str(exc),
            )
        )

    output_dir = resolve_path(base_dir, str(config.get("output_dir", "output")))
    write_reports(results, output_dir)
    logger.info("Wrote reports to %s", output_dir)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("execution.log", encoding="utf-8")],
    )
    try:
        results = run(args.config)
    except Exception as exc:
        logging.exception("Validation could not start")
        return 2
    passed = sum(item.status == "PASS" for item in results)
    failed = sum(item.status == "FAIL" for item in results)
    blocked = sum(item.status == "BLOCKED" for item in results)
    print(f"Validations: {len(results)} | PASS: {passed} | FAIL: {failed} | BLOCKED: {blocked}")
    return 1 if failed or blocked else 0


if __name__ == "__main__":
    sys.exit(main())
