"""Compare source and target records by configured transaction key."""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

from src.models import ValidationResult, result
from src.sales_validator import available, field_name


def equal_values(left: Any, right: Any, canonical: str, tolerance: float) -> tuple[bool, str]:
    left_text = str(left).strip()
    right_text = str(right).strip()
    left_missing = pd.isna(left) or left_text.casefold() in {"", "none", "nan", "nat"}
    right_missing = pd.isna(right) or right_text.casefold() in {"", "none", "nan", "nat"}
    if left_missing or right_missing:
        return left_missing and right_missing, ""
    numeric_fields = {
        "quantity",
        "unit_price",
        "sales_amount",
        "gross_amount",
        "commission_amount",
        "net_amount",
        "tax_amount",
        "discount_amount",
        "premium_amount",
    }
    if canonical in numeric_fields:
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
    source_key = field_name(columns, "transaction_id")
    target_key = field_name(columns, "transaction_id", target=True)
    if not available(source, source_key) or not available(target, target_key):
        return [
            result(
                "DM-KEY-SCHEMA",
                "Staging-to-Data Mart",
                "Reconciliation key available",
                source_name,
                target_name,
                "transaction key mapped on both sides",
                f"source={source_key in source.columns}; target={target_key in target.columns}",
                "BLOCKED",
                remarks="Configure source and target transaction ID column names.",
            )
        ]

    source_keys = source[source_key].astype(str).str.strip()
    target_keys = target[target_key].astype(str).str.strip()
    source_counts = source_keys[source_keys.ne("")].value_counts()
    target_counts = target_keys[target_keys.ne("")].value_counts()
    missing = sorted(set(source_counts.index) - set(target_counts.index))
    extra = sorted(set(target_counts.index) - set(source_counts.index))
    count_delta = len(target) - len(source)
    output.extend(
        [
            result(
                "DM-ROW-COUNT", "Staging-to-Data Mart", "Source and target row counts",
                source_name, target_name, len(source), len(target),
                "PASS" if count_delta == 0 else "FAIL", count_delta,
            ),
            result(
                "DM-DUPLICATES", "Staging-to-Data Mart", "Duplicate transaction keys",
                source_name, target_name, "0 duplicate-key rows on each side",
                f"source={int(source_counts[source_counts > 1].sum())}; target={int(target_counts[target_counts > 1].sum())}",
                "FAIL" if (source_counts > 1).any() or (target_counts > 1).any() else "PASS",
                int(source_counts[source_counts > 1].sum() + target_counts[target_counts > 1].sum()),
            ),
            result(
                "DM-MISSING", "Staging-to-Data Mart", "Source records missing in target",
                source_name, target_name, 0, len(missing), "PASS" if not missing else "FAIL",
                len(missing), record_key=", ".join(missing[:50]),
            ),
            result(
                "DM-EXTRA", "Staging-to-Data Mart", "Unexpected target records",
                source_name, target_name, 0, len(extra), "PASS" if not extra else "FAIL",
                len(extra), record_key=", ".join(extra[:50]),
            ),
        ]
    )

    shared_keys = set(source_counts.index) & set(target_counts.index)
    unique_keys = {
        key for key in shared_keys if source_counts[key] == 1 and target_counts[key] == 1
    }
    source_by_key = source.assign(_recon_key=source_keys).set_index("_recon_key", drop=False)
    target_by_key = target.assign(_recon_key=target_keys).set_index("_recon_key", drop=False)
    compare_fields = columns.get("compare_fields") or (
        "customer_id", "product_id", "product_family", "quantity", "unit_price",
        "sales_amount", "sales_date",
    )
    blocked_fields = columns.get("blocked_compare_fields", {})
    mismatch_count = 0
    for canonical in compare_fields:
        if canonical in blocked_fields:
            continue
        left_column = str(
            columns.get("source_columns", {}).get(canonical, field_name(columns, canonical))
        )
        right_column = str(
            columns.get("target_columns", {}).get(
                canonical, field_name(columns, canonical, target=True)
            )
        )
        if not available(source, left_column) or not available(target, right_column):
            continue
        for key in sorted(unique_keys):
            left = source_by_key.at[key, left_column]
            right = target_by_key.at[key, right_column]
            same, variance = equal_values(
                left, right, canonical, tolerance if canonical == "sales_amount" else 1e-9
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
                        left,
                        right,
                        "FAIL",
                        variance,
                        f"Source and target {canonical} differ.",
                        key,
                    )
                )
    for canonical, reason in blocked_fields.items():
        output.append(
            result(
                "DM-FIELD-BLOCKED", "Staging-to-Data Mart",
                f"Field comparison blocked: {canonical}", source_name, target_name,
                "confirmed source-to-target mapping", "mapping not verified", "BLOCKED",
                remarks=str(reason),
            )
        )
    output.append(
        result(
            "DM-FIELD-SUMMARY", "Staging-to-Data Mart", "Field-level reconciliation",
            source_name, target_name, "0 field mismatches on unique matched keys",
            mismatch_count, "PASS" if mismatch_count == 0 else "FAIL", mismatch_count,
            "Ambiguous duplicate keys are excluded from field comparison and reported separately.",
        )
    )
    return output
