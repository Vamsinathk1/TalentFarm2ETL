import pandas as pd

from src.business_rules import validate_business_rules


def test_sales_amount_formula_uses_configured_tolerance():
    frame = pd.DataFrame(
        [
            {"transaction_id": "T-1", "quantity": "2", "unit_price": "5", "amount": "10"},
            {"transaction_id": "T-2", "quantity": "2", "unit_price": "5", "amount": "11"},
        ]
    )
    rules = {
        "sales_amount": {
            "quantity_field": "quantity",
            "unit_price_field": "unit_price",
            "amount_field": "amount",
            "tolerance": 0.01,
        }
    }

    results = validate_business_rules(
        frame,
        "sales",
        {"transaction_id": "transaction_id"},
        rules,
    )

    assert results[0].validation_id == "BR-SALES-AMOUNT"
    assert results[0].status == "FAIL"
    assert results[0].actual_value == "1"
