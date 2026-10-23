import pandas as pd

from src.file_reader import read_delimited_file, read_sales_file
from src.sales_validator import validate_sales


def test_comma_delimiter_is_detected_in_txt_file(tmp_path):
    path = tmp_path / "customer.txt"
    path.write_text("customer_id,active_flag\nC-1,Y\n", encoding="utf-8")

    frame = read_delimited_file(path)

    assert frame.columns.tolist() == ["customer_id", "active_flag"]
    assert frame.loc[0, "customer_id"] == "C-1"


def test_json_sales_file_loads_as_records(tmp_path):
    path = tmp_path / "sales.json"
    path.write_text('[{"transaction_id":"T-1"}]', encoding="utf-8")

    frame = read_sales_file(path)

    assert frame.to_dict("records") == [{"transaction_id": "T-1"}]


def test_sales_validator_reports_missing_columns_and_invalid_dates():
    frame = pd.DataFrame(
        [{"transaction_id": "T-1", "sale_date": "not-a-date", "amount": "10"}]
    )
    config = {
        "transaction_id": "transaction_id",
        "sales_date": "sale_date",
        "sales_amount": "amount",
        "mandatory": ["transaction_id", "sale_date", "amount"],
    }

    results = validate_sales(frame, "sales", config)

    assert next(item for item in results if item.validation_id == "STG-SCHEMA").status == "PASS"
    assert next(item for item in results if item.validation_id == "STG-DATE").status == "FAIL"
