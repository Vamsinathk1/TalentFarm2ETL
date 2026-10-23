"""Validate customer master records and sales-to-customer references."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.models import ValidationResult, result
from src.sales_validator import field_name


def validate_customers(
    customers: pd.DataFrame,
    sales: pd.DataFrame | None,
    customer_config: dict[str, Any],
    columns: dict[str, Any],
) -> list[ValidationResult]:
    output: list[ValidationResult] = []
    customer_id = str(customer_config.get("id_field", ""))
    missing = [customer_id] if not customer_id or customer_id not in customers.columns else []
    output.append(
        result(
            "STG-CUSTOMER-SCHEMA",
            "Source-to-Staging",
            "Customer Master required ID field",
            "Customer Master file",
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
    duplicate_mask = ids.ne("") & ids.duplicated(keep=False)
    duplicate_count = int(duplicate_mask.sum())
    output.append(
        result(
            "STG-CUSTOMER-IDS",
            "Source-to-Staging",
            "Customer IDs present and unique",
            "Customer Master file",
            "customer dataframe",
            "no blank or duplicate IDs",
            f"blank={empty_count}; duplicate_rows={duplicate_count}",
            "FAIL" if empty_count or duplicate_count else "PASS",
            empty_count + duplicate_count,
            remarks=f"Duplicate customer ID rows: {duplicate_count}",
            record_key=", ".join(ids[duplicate_mask].unique()[:20]),
        )
    )

    mandatory_fields = [str(value) for value in customer_config.get("mandatory_fields", [])]
    missing_fields = [name for name in mandatory_fields if name not in customers.columns]
    empty_values = 0
    empty_rows = pd.Series(False, index=customers.index)
    for name in mandatory_fields:
        if name in customers.columns:
            empty_mask = customers[name].astype(str).str.strip().eq("")
            empty_values += int(empty_mask.sum())
            empty_rows |= empty_mask
    output.append(
        result(
            "STG-CUSTOMER-MANDATORY",
            "Source-to-Staging",
            "Customer Master mandatory fields",
            "Customer Master file",
            "customer dataframe",
            "all configured fields present and nonblank",
            f"missing_fields={len(missing_fields)}; blank_values={empty_values}",
            "FAIL" if missing_fields or empty_values else "PASS",
            len(missing_fields) + empty_values,
            "Missing fields: " + ", ".join(missing_fields) if missing_fields else "",
            ", ".join(customers.index[empty_rows].astype(str)[:20]),
        )
    )

    if sales is None:
        return output

    sales_id = field_name(columns, "customer_id")
    if sales_id in sales.columns:
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
                "Source-to-Staging",
                "Sales customer references resolve",
                "Distributor Sales file",
                "Customer Master file",
                "all sales customer IDs exist and are active",
                len(invalid_ids),
                "FAIL" if invalid_ids else "PASS",
                len(invalid_ids),
                record_key=", ".join(invalid_ids[:20]),
            )
        )

    source_policy = str(customer_config.get("source_policy_field", "policy_number"))
    master_policy = str(customer_config.get("master_policy_field", "policy_number"))
    if source_policy in sales.columns and master_policy in customers.columns:
        policies = set(customers[master_policy].astype(str).str.strip())
        sales_policies = sales[source_policy].astype(str).str.strip()
        missing_policies = sales_policies.ne("") & ~sales_policies.isin(policies)
        output.append(
            result(
                "STG-CUSTOMER-POLICY-REF",
                "Source-to-Staging",
                "Sales policy references resolve",
                "Distributor Sales file",
                "Customer Master file",
                "all nonblank policy numbers exist",
                int(missing_policies.sum()),
                "FAIL" if missing_policies.any() else "PASS",
                int(missing_policies.sum()),
                record_key=", ".join(sales_policies[missing_policies].unique()[:20]),
            )
        )
    return output
