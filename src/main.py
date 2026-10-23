"""Configure and run the Assignment 2 validation pipeline."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.business_rules import validate_business_rules
from src.customer_validator import validate_customers
from src.database import load_target
from src.file_reader import read_customer_file, read_sales_file, resolve_path
from src.models import ValidationResult, result
from src.reconciliation import reconcile
from src.report_generator import generate_reports
from src.sales_validator import validate_sales


def run(config_path: Path) -> list[ValidationResult]:
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent
    project_root = Path(__file__).resolve().parents[1]
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
                    f"LOAD-{name.upper()}", "Source-to-Staging", f"Load {name}",
                    str(path), "normalized dataframe", "file readable",
                    f"{len(frame)} rows", "PASS",
                )
            )
            results.extend(validate_sales(frame, name, columns))
            results.extend(
                validate_business_rules(
                    frame, name, columns, config.get("business_rules", {})
                )
            )
        except Exception as exc:
            logger.exception("Failed loading %s", name)
            results.append(
                result(
                    f"LOAD-{name.upper()}", "Source-to-Staging", f"Load {name}",
                    str(path), "normalized dataframe", "file readable",
                    type(exc).__name__, "FAIL", remarks=str(exc),
                )
            )

    customer_frame: pd.DataFrame | None = None
    customer_name = next(
        (name for name in ("customer_master_file", "customer_master_json") if inputs.get(name)),
        None,
    )
    customer_path = inputs.get(customer_name) if customer_name else None
    if customer_path:
        path = resolve_path(base_dir, str(customer_path))
        try:
            customer_frame = read_customer_file(
                path, config.get("customer_json", {}).get("records_key")
            )
            results.append(
                result(
                    "LOAD-CUSTOMERS", "Source-to-Staging", "Load Customer Master file",
                    str(path), "customer dataframe", "valid customer file readable",
                    f"{len(customer_frame)} records", "PASS",
                )
            )
            reference_source = str(
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
                    dataframes.get(reference_source),
                    config.get("customer_json", {}),
                    columns,
                )
            )
        except Exception as exc:
            logger.exception("Failed loading Customer Master file")
            results.append(
                result(
                    "LOAD-CUSTOMERS", "Source-to-Staging", "Load Customer Master file",
                    str(path), "customer dataframe", "valid customer file readable",
                    type(exc).__name__, "FAIL", remarks=str(exc),
                )
            )

    try:
        target_frame, target_name = load_target(config, base_dir)
        results.append(
            result(
                "LOAD-TARGET", "Staging-to-Data Mart", "Read target data",
                str(config.get("target", {}).get("query", "")), target_name,
                "target query succeeds", f"{len(target_frame)} rows", "PASS",
            )
        )
        source_key = str(
            config.get("target", {}).get("reconciliation_source", "distributor_sales_json")
        )
        source_frame = dataframes.get(source_key)
        if source_frame is None:
            results.append(
                result(
                    "DM-SOURCE-UNAVAILABLE", "Staging-to-Data Mart",
                    "Reconciliation source available", source_key, target_name,
                    "configured source loaded", "not loaded", "BLOCKED",
                    remarks="Check input path/configuration and source file format.",
                )
            )
        else:
            reconciliation_columns = dict(columns)
            reconciliation_columns["target_columns"] = dict(columns.get("target_columns", {}))
            customer_settings = config.get("customer_json", {})
            master_key = str(customer_settings.get("target_key_field", ""))
            source_customer_key = str(customer_settings.get("mapping_source_field", ""))
            master_customer_key = str(customer_settings.get("mapping_master_field", ""))
            if (
                customer_frame is not None
                and master_key
                and source_customer_key in source_frame.columns
                and master_customer_key in customer_frame.columns
                and master_key in customer_frame.columns
            ):
                unique_customers = customer_frame.drop_duplicates(master_customer_key, keep=False)
                lookup = unique_customers.set_index(master_customer_key)[master_key]
                source_frame = source_frame.copy()
                mapped_key = "__reconciled_customer_key"
                source_frame[mapped_key] = source_frame[source_customer_key].map(lookup)
                reconciliation_columns["customer_id"] = mapped_key
                reconciliation_columns["target_columns"]["customer_id"] = str(
                    customer_settings.get("target_customer_key_field", "customer_key")
                )
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
                "LOAD-TARGET", "Staging-to-Data Mart", "Read target data",
                str(config.get("target", {}).get("query", "")), "configured target",
                "target query succeeds", type(exc).__name__, "FAIL", remarks=str(exc),
            )
        )

    reports_dir = resolve_path(
        base_dir,
        str(config.get("reports_dir", config.get("output_dir", "../reports"))),
    )
    if not reports_dir.is_absolute():
        reports_dir = (project_root / reports_dir).resolve()
    generated = generate_reports(results, reports_dir)
    logger.info("Wrote reports: %s", ", ".join(str(path) for path in generated.values()))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/config.json"))
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / "execution.log", encoding="utf-8"),
        ],
        force=True,
    )
    try:
        results = run(args.config)
    except Exception:
        logging.exception("Validation could not start")
        return 2
    counts = {status: sum(item.status == status for item in results) for status in ("PASS", "FAIL", "BLOCKED")}
    print(
        f"Validations: {len(results)} | PASS: {counts['PASS']} | "
        f"FAIL: {counts['FAIL']} | BLOCKED: {counts['BLOCKED']}"
    )
    return 1 if counts["FAIL"] or counts["BLOCKED"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
