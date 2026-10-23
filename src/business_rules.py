"""Validate documented calculations and product-family business rules."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.models import ValidationResult, result
from src.sales_validator import field_name, sample_record_keys


def validate_business_rules(
    frame: pd.DataFrame,
    label: str,
    columns: dict[str, Any],
    rules: dict[str, Any],
) -> list[ValidationResult]:
    output: list[ValidationResult] = []
    amount_rule = rules.get("sales_amount")
    if amount_rule:
        quantity_field = str(amount_rule.get("quantity_field", field_name(columns, "quantity")))
        price_field = str(amount_rule.get("unit_price_field", field_name(columns, "unit_price")))
        amount_field = str(amount_rule.get("amount_field", field_name(columns, "sales_amount")))
        if all(name in frame.columns for name in (quantity_field, price_field, amount_field)):
            quantity = pd.to_numeric(frame[quantity_field], errors="coerce")
            price = pd.to_numeric(frame[price_field], errors="coerce")
            amount = pd.to_numeric(frame[amount_field], errors="coerce")
            tolerance = float(amount_rule.get("tolerance", 0.01))
            invalid = (quantity * price - amount).abs().gt(tolerance)
            valid_values = quantity.notna() & price.notna() & amount.notna()
            failures = invalid & valid_values
            count = int(failures.sum())
            output.append(
                result(
                    "BR-SALES-AMOUNT",
                    "Source-to-Staging",
                    "Sales amount calculation",
                    label,
                    "calculated sales amount",
                    f"{quantity_field} * {price_field} within {tolerance}",
                    count,
                    "FAIL" if count else "PASS",
                    count,
                    "Formula/tolerance must match the approved business rule.",
                    sample_record_keys(frame, failures, field_name(columns, "transaction_id")),
                )
            )
        else:
            output.append(
                result(
                    "BR-SALES-AMOUNT",
                    "Source-to-Staging",
                    "Sales amount calculation",
                    label,
                    "calculated sales amount",
                    "configured input fields available",
                    "one or more fields unavailable",
                    "BLOCKED",
                    remarks="Configure quantity, unit-price, and amount fields from the approved mapping.",
                )
            )

    family_rule = rules.get("product_family")
    if family_rule:
        product_field = str(family_rule.get("product_field", field_name(columns, "product_id")))
        family_field = str(family_rule.get("family_field", field_name(columns, "product_family")))
        allowed = family_rule.get("allowed", {})
        if product_field in frame.columns and family_field in frame.columns and allowed:
            expected = frame[product_field].map(allowed)
            actual = frame[family_field].astype(str).str.strip()
            failures = expected.notna() & expected.astype(str).ne(actual)
            count = int(failures.sum())
            output.append(
                result(
                    "BR-PRODUCT-FAMILY",
                    "Source-to-Staging",
                    "Product-family relationship",
                    label,
                    "configured product-family mapping",
                    "family matches approved product mapping",
                    count,
                    "FAIL" if count else "PASS",
                    count,
                    record_key=sample_record_keys(frame, failures, field_name(columns, "transaction_id")),
                )
            )
        else:
            output.append(
                result(
                    "BR-PRODUCT-FAMILY",
                    "Source-to-Staging",
                    "Product-family relationship",
                    label,
                    "configured product-family mapping",
                    "mapping and fields available",
                    "mapping or fields unavailable",
                    "BLOCKED",
                    remarks="Provide the product master and approved product-family mapping.",
                )
            )
    return output
