# Assignment 2: Sales Data QA Automation

The submission requirements extracted from the local PDFs are summarized in [assignment2_reference.md](assignment2_reference.md). The detailed test inventory is [test_cases.csv](test_cases.csv).

The implementation follows the requested modular layout: `src/` contains the file reader, sales/customer validators, database connector, reconciliation, business rules, report generator, and pipeline entry point. The six focused test modules are in `tests/`.

## Environment

Python 3.10+. From PowerShell at this repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run against the discovered lab files

Copy `config/config.example.json` to the ignored runtime file `config/config.json`. It points to read-only lab inputs under `C:\qa-lab\python-project-2\input` and the verified `dm_distributor_sales_customer_360` MySQL table:

- `dim_Distributor_sales_50k.json`
- `dim_Customer_Master_50k.txt` (comma-delimited despite its extension)
- `Fact_Sales_50k_CSV.csv`

Do not copy the input datasets into the repository; `data/README.md` explains the data-handling rule.
Create the local runtime config:

```powershell
Copy-Item config/config.example.json config/config.json
```

Enter the password through a non-echoing SecureString prompt, then clear the environment variables when finished:

```powershell
$securePassword = Read-Host 'Database password' -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
	$env:P2_DB_USER = Read-Host 'Database user'
	$env:P2_DB_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
	python run_validation.py --config config/config.json
}
finally {
	Remove-Item Env:P2_DB_USER, Env:P2_DB_PASSWORD -ErrorAction SilentlyContinue
	[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
	$securePassword.Dispose()
}
```

Each run writes `reports/validation_results.csv`, `reports/reconciliation_report.csv`, `reports/qa_summary.html`, and `logs/execution.log`. Detailed reports are ignored and excluded from the ZIP because row-level data can contain sensitive identifiers. The process exits nonzero when checks fail. The runner issues a configured read-only `SELECT`; it does not modify the database. Do not put passwords in config or reports. `sample_execution.txt` contains the sanitized summary of the verified run.

## Run tests and demo

```powershell
python -m pytest -q
python demo_run.py
```

The demo uses fabricated records and deliberately includes defects. Its output is explicitly labeled synthetic; do not submit it as lab execution evidence. Actual MySQL execution evidence is summarized in `sample_execution.txt`.

## PDF text extraction

```powershell
python extract_pdf_text.py . --output-dir extracted_pdf_text
```

The Quick Start PDF contains credentials. Keep extracted files private; do not commit or share them.

## Current findings and limits

The inspected source files each have 50,000 rows. The live mart has 45,076 rows: 4,924 source transactions are missing and there are no extra mart keys. Of matched records, 40,575 customer-PAN values differ; the other compared direct fields match.

The current run finds 1,539 blank distributor `customer_id` values, 2,525 Customer Master rows participating in duplicate IDs, and 44,753 unique nonblank distributor customer IDs that do not resolve to an active Customer Master ID. Policy references resolve. Confirm whether these findings reflect intended data quality rules with the mentor.

The input folder does not include product/distributor/region dimension tables or the dashboard specification. Derived measures, aggregate rules, and dashboard tests remain blocked until mappings and reporting extracts are provided. `test_cases.csv` records these limits. The PDFs differ from the actual input formats; this config follows the verified lab files and live mart schema.
