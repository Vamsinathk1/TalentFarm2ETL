"""Write detailed CSV, reconciliation CSV, and aggregate HTML reports."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.models import ValidationResult


def generate_reports(
    results: Iterable[ValidationResult],
    reports_dir: Path,
) -> dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(item) for item in results]
    details = pd.DataFrame(rows, columns=list(ValidationResult.__dataclass_fields__))
    validation_path = reports_dir / "validation_results.csv"
    reconciliation_path = reports_dir / "reconciliation_report.csv"
    summary_path = reports_dir / "qa_summary.html"

    details.to_csv(validation_path, index=False)
    reconciliation = details[details["layer"] == "Staging-to-Data Mart"] if not details.empty else details
    reconciliation.to_csv(reconciliation_path, index=False)

    status_counts = (
        details["status"].value_counts().to_dict()
        if not details.empty
        else {}
    )
    grouped = (
        details.groupby(["layer", "validation_id", "validation_name", "status"])
        .size()
        .reset_index(name="result_rows")
        if not details.empty
        else pd.DataFrame(columns=["layer", "validation_id", "validation_name", "status", "result_rows"])
    )
    rows_processed = details.loc[
        details["validation_id"].str.startswith("LOAD-"), "actual_value"
    ].tolist() if not details.empty else []
    report_html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>QA Summary</title>
<style>body{font:15px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#18222d}h1,h2{color:#12344a}table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #ccd5dc;padding:.5rem;text-align:left}th{background:#edf3f6}.PASS{color:#176b3a}.FAIL{color:#a32121}.BLOCKED{color:#805500}</style>
</head><body>
<h1>QA Validation Summary</h1>
<p>Generated UTC: """ + escape(datetime.now(timezone.utc).isoformat(timespec="seconds")) + """</p>
<h2>Summary</h2><ul>"""
    for status in ("PASS", "FAIL", "BLOCKED"):
        report_html += f'<li class="{status}">{status}: {int(status_counts.get(status, 0))}</li>'
    report_html += "</ul><h2>Input/target loads</h2><ul>"
    report_html += "".join(f"<li>{escape(value)}</li>" for value in rows_processed)
    report_html += "</ul><h2>Checks by validation</h2>"
    report_html += grouped.to_html(index=False, escape=True, classes="results")
    report_html += "\n</body></html>\n"
    summary_path.write_text(report_html, encoding="utf-8")
    return {
        "validation_results": validation_path,
        "reconciliation_report": reconciliation_path,
        "qa_summary": summary_path,
    }
