import pandas as pd

from run_validation import _equal_values, read_pipe_file, reconcile, validate_customers, validate_sales


COLUMNS = {
    "transaction_id": "distributor_txn_id",
    "customer_id": "customer_id",
    "product_id": "product_code",
    "sales_amount": "gross_amount",
    "sales_date": "sale_date",
    "mandatory": ["distributor_txn_id", "customer_id", "gross_amount", "sale_date"],
    "numeric": ["gross_amount", "commission_amount"],
    "target_columns": {
        "customer_id": "customer_key",
        "sales_amount": "gross_amount",
        "sales_date": "sale_date_key",
    },
}


def sample_source() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "distributor_txn_id": "TX-1",
                "customer_id": "C-1",
                "product_code": "P-1",
                "gross_amount": "20.00",
                "commission_amount": "1.00",
                "sale_date": "2025-01-02",
            },
            {
                "distributor_txn_id": "TX-2",
                "customer_id": "C-2",
                "product_code": "P-2",
                "gross_amount": "50.00",
                "commission_amount": "2.50",
                "sale_date": "2025-01-03",
            },
        ]
    )


def test_sales_checks_report_numeric_and_date_errors():
    source = sample_source()
    source.loc[1, "gross_amount"] = "bad"
    source.loc[0, "sale_date"] = "not-a-date"

    results = validate_sales(source, "distributor_sales", COLUMNS, {})

    assert {item.validation_id for item in results} >= {
        "STG-NUM-GROSS_AMOUNT",
        "STG-DATE",
    }
    assert all(item.status in {"PASS", "FAIL", "BLOCKED"} for item in results)
    assert any(item.status == "FAIL" for item in results)


def test_customer_references_flag_unknown_customer():
    customers = pd.DataFrame(
        [
            {"customer_id": "C-1", "active_flag": "Y"},
            {"customer_id": "C-2", "active_flag": "Y"},
        ]
    )
    sales = sample_source()
    sales.loc[1, "customer_id"] = "C-404"

    results = validate_customers(
        customers,
        sales,
        {"id_field": "customer_id", "active_field": "active_flag", "active_values": ["Y"]},
        COLUMNS,
    )

    reference = next(item for item in results if item.validation_id == "STG-CUSTOMER-REF")
    assert reference.status == "FAIL"
    assert reference.record_key == "C-404"


def test_policy_reference_is_checked_when_available():
    customers = pd.DataFrame(
        [
            {"customer_id": "C-1", "policy_number": "POL-1"},
            {"customer_id": "C-2", "policy_number": "POL-2"},
        ]
    )
    sales = pd.DataFrame(
        [
            {"customer_id": "C-1", "policy_number": "POL-1"},
            {"customer_id": "C-2", "policy_number": "POL-MISSING"},
        ]
    )

    results = validate_customers(
        customers,
        sales,
        {"id_field": "customer_id"},
        {"customer_id": "customer_id", "mandatory": []},
    )

    policy_reference = next(
        item for item in results if item.validation_id == "STG-CUSTOMER-POLICY-REF"
    )
    assert policy_reference.status == "FAIL"
    assert policy_reference.actual_value == "1"


def test_delimited_text_reader_detects_comma_separator(tmp_path):
    path = tmp_path / "customer_master.txt"
    path.write_text("customer_id,active_flag\nC-1,Y\n", encoding="utf-8")

    frame = read_pipe_file(path)

    assert frame.columns.tolist() == ["customer_id", "active_flag"]
    assert frame.loc[0, "customer_id"] == "C-1"


def test_reconciliation_reports_missing_extra_and_field_mismatch():
    source = sample_source()
    source["customer_key"] = [101, 102]
    target = pd.DataFrame(
        [
            {
                "distributor_txn_id": "TX-1",
                "customer_key": 101,
                "gross_amount": 19.0,
                "sale_date_key": 20250102,
            },
            {
                "distributor_txn_id": "TX-3",
                "customer_key": 103,
                "gross_amount": 5.0,
                "sale_date_key": 20250104,
            },
        ]
    )

    results = reconcile(source, target, "source", "target", COLUMNS, 0.01)

    by_id = {item.validation_id: item for item in results if item.validation_id != "DM-FIELD-MISMATCH"}
    assert by_id["DM-MISSING"].actual_value == "1"
    assert by_id["DM-EXTRA"].actual_value == "1"
    assert any(item.validation_id == "DM-FIELD-MISMATCH" for item in results)


def test_reconciliation_compares_yyyymmdd_target_dates():
    source = pd.DataFrame(
        [{"distributor_txn_id": "TX-1", "sale_date": "2025-01-02"}]
    )
    target = pd.DataFrame(
        [{"distributor_txn_id": "TX-1", "sale_date_key": 20250102}]
    )
    columns = {
        "transaction_id": "distributor_txn_id",
        "sales_date": "sale_date",
        "mandatory": [],
        "target_columns": {"sales_date": "sale_date_key"},
    }

    results = reconcile(source, target, "source", "target", columns, 0.01)

    assert not any(item.validation_id == "DM-FIELD-MISMATCH" for item in results)


def test_unverified_field_mapping_is_blocked_not_failed():
    source = pd.DataFrame([{"distributor_txn_id": "TX-1", "customer_id": "C-1"}])
    target = pd.DataFrame([{"distributor_txn_id": "TX-1", "customer_key": "100"}])
    columns = {
        "transaction_id": "distributor_txn_id",
        "customer_id": "customer_id",
        "compare_fields": ["customer_id"],
        "target_columns": {"customer_id": "customer_key"},
        "blocked_compare_fields": {"customer_id": "mapping not verified"},
    }

    results = reconcile(source, target, "source", "target", columns, 0.01)

    blocked = next(item for item in results if item.validation_id == "DM-FIELD-BLOCKED")
    assert blocked.status == "BLOCKED"
    assert not any(item.validation_id == "DM-FIELD-MISMATCH" for item in results)


def test_null_and_empty_values_compare_as_equal_but_one_sided_null_does_not():
    assert _equal_values(None, "", "folio_number", 0.01) == (True, "")
    assert _equal_values(float("nan"), None, "customer_id", 0.01) == (True, "")
    assert _equal_values(None, "C-1", "customer_id", 0.01) == (False, "")
