import pandas as pd

from src.reconciliation import equal_values, reconcile


def test_reconciliation_reports_missing_extra_and_field_mismatch():
    source = pd.DataFrame(
        [
            {"transaction_id": "T-1", "amount": "10.00"},
            {"transaction_id": "T-2", "amount": "20.00"},
        ]
    )
    target = pd.DataFrame(
        [
            {"transaction_id": "T-1", "amount": "9.00"},
            {"transaction_id": "T-3", "amount": "30.00"},
        ]
    )
    config = {
        "transaction_id": "transaction_id",
        "sales_amount": "amount",
        "compare_fields": ["sales_amount"],
        "target_columns": {"sales_amount": "amount"},
    }

    results = reconcile(source, target, "source", "target", config, 0.01)
    by_id = {item.validation_id: item for item in results if item.validation_id != "DM-FIELD-MISMATCH"}

    assert by_id["DM-MISSING"].actual_value == "1"
    assert by_id["DM-EXTRA"].actual_value == "1"
    assert any(item.validation_id == "DM-FIELD-MISMATCH" for item in results)


def test_date_key_and_null_normalization():
    assert equal_values("2025-01-02", 20250102, "sales_date", 0.01)[0]
    assert equal_values(None, "", "customer_id", 0.01)[0]
    assert not equal_values(None, "C-1", "customer_id", 0.01)[0]
