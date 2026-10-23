"""Run a clearly labeled synthetic end-to-end validation demonstration."""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
from pathlib import Path

from run_validation import run


SOURCE_ROWS = [
    "Transaction_ID|Customer_ID|Product_ID|Quantity|Unit_Price|Sales_Amount|Sales_Date",
    "TX-1001|C-001|P-01|2|10.00|20.00|2025-01-02",
    "TX-1002|C-002|P-02|3|20.00|60.00|2025-01-03",
    "TX-1003|C-001|P-01|1|10.00|10.00|2025-01-04",
]
TARGET_ROWS = [
    "Transaction_ID|Customer_ID|Product_ID|Quantity|Unit_Price|Sales_Amount|Sales_Date",
    "TX-1001|C-001|P-01|2|10.00|19.00|2025-01-02",
    "TX-1003|C-001|P-01|1|10.00|10.00|2025-01-04",
    "TX-9000|C-002|P-02|1|20.00|20.00|2025-01-05",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output/demo"))
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(output_dir / "execution.log", encoding="utf-8"),
        ],
        force=True,
    )

    with tempfile.TemporaryDirectory(prefix="assignment2-demo-") as temp_dir:
        workspace = Path(temp_dir)
        source_path = workspace / "source.txt"
        target_path = workspace / "target.txt"
        customer_path = workspace / "customers.json"
        config_path = workspace / "config.json"
        source_path.write_text("\n".join(SOURCE_ROWS) + "\n", encoding="utf-8")
        target_path.write_text("\n".join(TARGET_ROWS) + "\n", encoding="utf-8")
        customer_path.write_text(
            json.dumps(
                [
                    {"Customer_ID": "C-001", "Status": "ACTIVE"},
                    {"Customer_ID": "C-002", "Status": "ACTIVE"},
                ]
            ),
            encoding="utf-8",
        )
        config = {
            "inputs": {
                "distributor_sales_txt": str(source_path),
                "customer_master_json": str(customer_path),
            },
            "target": {
                "mode": "file",
                "path": str(target_path),
                "reconciliation_source": "distributor_sales_txt",
            },
            "columns": {
                "transaction_id": "Transaction_ID",
                "customer_id": "Customer_ID",
                "product_id": "Product_ID",
                "quantity": "Quantity",
                "unit_price": "Unit_Price",
                "sales_amount": "Sales_Amount",
                "sales_date": "Sales_Date",
                "mandatory": [
                    "Transaction_ID",
                    "Customer_ID",
                    "Product_ID",
                    "Quantity",
                    "Unit_Price",
                    "Sales_Amount",
                    "Sales_Date",
                ],
            },
            "customer_json": {
                "id_field": "Customer_ID",
                "active_field": "Status",
                "active_values": ["ACTIVE"],
            },
            "validation": {"amount_tolerance": 0.01},
            "output_dir": str(output_dir),
        }
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        results = run(config_path)

    (output_dir / "DEMO_ONLY.txt").write_text(
        "Synthetic demonstration only. These fabricated records are not assignment lab data.\n",
        encoding="utf-8",
    )
    passed = sum(item.status == "PASS" for item in results)
    failed = sum(item.status == "FAIL" for item in results)
    blocked = sum(item.status == "BLOCKED" for item in results)
    print(f"Synthetic demo complete | PASS: {passed} | FAIL: {failed} | BLOCKED: {blocked}")
    print(f"Reports: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
