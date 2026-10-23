from src.models import result
from src.report_generator import generate_reports


def test_report_generator_writes_requested_outputs_and_redacted_html(tmp_path):
    rows = [
        result(
            "DM-FIELD-MISMATCH",
            "Staging-to-Data Mart",
            "Field comparison: customer_id",
            "source",
            "target",
            "private-source-value",
            "private-target-value",
            "FAIL",
            record_key="private-transaction-key",
        )
    ]

    paths = generate_reports(rows, tmp_path)

    assert {path.name for path in paths.values()} == {
        "validation_results.csv",
        "reconciliation_report.csv",
        "qa_summary.html",
    }
    html = paths["qa_summary"].read_text(encoding="utf-8")
    assert "DM-FIELD-MISMATCH" in html
    assert "private-transaction-key" not in html
    assert "private-source-value" not in html
