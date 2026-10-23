import pandas as pd

from src.customer_validator import validate_customers


def test_customer_id_and_policy_references_are_validated():
    customers = pd.DataFrame(
        [
            {"customer_id": "C-1", "active": "Y", "policy": "P-1"},
            {"customer_id": "C-2", "active": "Y", "policy": "P-2"},
        ]
    )
    sales = pd.DataFrame(
        [
            {"customer_id": "C-1", "policy": "P-1"},
            {"customer_id": "C-404", "policy": "P-404"},
        ]
    )
    results = validate_customers(
        customers,
        sales,
        {
            "id_field": "customer_id",
            "active_field": "active",
            "active_values": ["Y"],
            "source_policy_field": "policy",
            "master_policy_field": "policy",
        },
        {"customer_id": "customer_id"},
    )

    by_id = {item.validation_id: item for item in results}
    assert by_id["STG-CUSTOMER-REF"].actual_value == "1"
    assert by_id["STG-CUSTOMER-POLICY-REF"].actual_value == "1"


def test_duplicate_customer_ids_fail_uniqueness_check():
    customers = pd.DataFrame(
        [
            {"customer_id": "C-1"},
            {"customer_id": "C-1"},
        ]
    )

    results = validate_customers(
        customers,
        None,
        {"id_field": "customer_id"},
        {},
    )

    uniqueness = next(item for item in results if item.validation_id == "STG-CUSTOMER-IDS")
    assert uniqueness.status == "FAIL"
    assert uniqueness.variance == "2"
