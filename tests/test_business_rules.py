import pandas as pd

from src.business_rules import validate_business_rules


def test_product_family_rule_checks_approved_mapping():
    frame = pd.DataFrame(
        [
            {"transaction_id": "T-1", "product": "P-1", "family": "Life"},
            {"transaction_id": "T-2", "product": "P-2", "family": "Wrong"},
        ]
    )
    rules = {
        "product_family": {
            "product_field": "product",
            "family_field": "family",
            "allowed": {"P-1": "Life", "P-2": "Health"},
        }
    }

    results = validate_business_rules(
        frame,
        "sales",
        {"transaction_id": "transaction_id"},
        rules,
    )

    assert results[0].validation_id == "BR-PRODUCT-FAMILY"
    assert results[0].status == "FAIL"
    assert results[0].actual_value == "1"


def test_unprovided_product_mapping_is_blocked():
    result = validate_business_rules(
        pd.DataFrame([{"product": "P-1"}]),
        "sales",
        {},
        {"product_family": {"product_field": "product", "family_field": "family"}},
    )[0]

    assert result.status == "BLOCKED"
