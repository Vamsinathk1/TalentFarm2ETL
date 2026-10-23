# Assignment 2 Reference

Local summary of the assignment PDFs and `Submission 2 .txt`. No external sources used. Credential values printed in the Quick Start PDF are intentionally omitted.

## Submission 2 deliverables

- Completed test-case sheet covering all validation layers.
- Python automation code, organized for mentor review.
- Redacted example configuration; never commit passwords or tokens.
- README with setup, execution, assumptions, dependencies, and known limitations.
- Python dependency list (`requirements.txt`).
- Sample validation report, console output, or log from an initial run.
- All submitted links must be accessible to mentors.

The submission guideline says each important test case should identify source and target objects, validation logic, and expected result. Its fuller suggested fields are test ID, layer, risk/requirement, source, target, logic, expected result, automation candidate/method, severity, and evidence. Validators should report validation name, expected/actual, status, variance, and remarks. Logs should capture start time, checks run, and errors. Reports may be CSV, Excel, HTML, or readable text.

## Project-specific scope

The problem statement describes distributor sales in a pipe-delimited TXT file, customer master in JSON, and MySQL sales data. The detailed context and functional-module description call for file/JSON validation, SQL/database checks, source-target reconciliation, business rules, defect evidence, PASS/FAIL results, and a QA summary.

Minimum functional checks:

- File exists, is readable, has expected pipe-delimited columns, and contains no malformed rows.
- Required fields and data types; valid dates; missing values; duplicate transaction IDs.
- Customer JSON structure, required fields, unique IDs, and active/existing customer references.
- MySQL connectivity, target availability, SQL retrieval, counts, duplicates, missing/extra records, and proper connection/error handling.
- Transaction-level reconciliation and field-level comparisons.
- Quantity, unit price, sales amount (`quantity * unit price`, subject to the confirmed rounding/tolerance rule), product/product-family consistency, and source-target consistency.
- Traceable defects with transaction/customer key, rule, expected/actual or source/target value, failure reason, and severity where defined.
- Summary counts for processed records, validations, PASS/FAIL, missing/extra/duplicate records, and rule/mismatch categories.

The evaluation emphasizes Python implementation (20%), test design (15%), reconciliation (15%), business rules (10%), SQL/database (10%), reporting/defects (5%), and maintainability (5%), alongside problem and data understanding (20%). Minimum coverage also names completeness, uniqueness, database checks, customer references, quantities/prices, sales amount, products/product families, PASS/FAIL, and QA reporting.

## Three-layer test design

The general Submission Guidelines require coverage for:

1. Source-to-staging: ingestion, file/API/schema/count/data-quality checks.
2. Staging-to-data mart: transformations, mappings, derived fields, aggregates.
3. Data mart-to-reporting: report/dashboard values, filters, displayed metrics.

The same guide gives generic retail CSV and online API examples. Those are not named in the distributor-specific problem statement. Adapt the test sheet to the supplied distributor project. Mark unsupported stages as blocked/out-of-scope until their objects/mappings are supplied; do not invent tables or report expectations. The automation in this folder can verify ingestion and reconciliation/report-file generation, but cannot certify a dashboard without a reporting extract/specification.

## Environment and target ambiguity

The PDFs conflict on the data model:

- Problem Statement, Detailed Context, Functional Module Description, and Technical Framework refer to a MySQL `Fact_Sales` target.
- Quick Start lists three input files (`dim_Distributor_sales.txt`, `Fact_Sales.txt`, and `dim_Customer_Master.json`) and a MySQL `dm_Distributor_Sales_Customer_360` target. It specifies MySQL 8.0, a read-only learner account, and Pandas / `mysql.connector` / `openpyxl` in its dependency check.

The live lab database was checked with read-only queries. It contains both `fact_sales` and `dm_distributor_sales_customer_360`; the latter is the reconciliation target because it includes the direct source fields. The example config uses that mart and reads credentials from `P2_DB_USER` and `P2_DB_PASSWORD`; never place the password itself in a config file.

## Actual lab datasets inspected

The learner lab folder contains 3 read-only files, each with 50,000 records:

- `dim_Distributor_sales_50k.json`: JSON array with transaction ID, sale date, distributor code/name, customer ID/PAN, product code/name/type, policy/folio numbers, gross/commission amounts, region, status, and timestamps.
- `dim_Customer_Master_50k.txt`: comma-delimited text despite the `.txt` extension; columns include customer key/ID, policy, contact/profile, KYC, active flag, and timestamps.
- `Fact_Sales_50k_CSV.csv`: CSV snapshot of the Fact Sales table with transaction ID, date/distributor/product/customer/region keys, gross/net/commission/tax/discount/premium amounts, policy/folio/status, and ETL metadata.

Observed relationships: the source has 50,000 unique transaction IDs; the live mart has 45,076 unique IDs, all present in the source. There are 4,924 missing mart transactions and no extra mart transactions. Policy numbers resolve across source and customer files. Customer Master has 2,525 duplicate-ID rows (1,254 IDs with multiple keys); 44,753 unique nonblank distributor customer IDs do not resolve to an active Customer Master ID. Of 45,076 matched rows, 40,575 have a customer-PAN mismatch; other compared direct fields match. Product/distributor/region lookup tables and reporting specifications are not provided.

Initial live mart validation on 2026-10-23: 40,594 result rows, 13 PASS and 40,581 FAIL. This count includes 40,575 row-level customer-PAN mismatches. Other findings are 4,924 missing mart transactions, 1,539 blank source customer IDs, duplicate customer IDs, and unmatched customer references. See `sample_execution.txt`; row-level output may contain sensitive identifiers and is excluded from the submission ZIP.

## Local environment notes

The repository initially contained assignment documents and the submission checklist; the separate lab directory contains the files listed above. The starter uses configurable column names and synthetic unit tests. Synthetic output is not evidence of a real lab run. The source files and database should remain read-only during validation. Never include lab credentials in public config, reports, logs, screenshots, or this reference.

## Source documents

- `Assignment 2 Submission Guidelines.pdf`
- `Problem Statement Overview.pdf`
- `Detailed Context.pdf`
- `Functional Module Description.pdf`
- `Technical Environment and Automation Framework.pdf`
- `Lab Quick Start Guide.pdf`
- `Submission and Evaluation.pdf`
- `Submission 2 .txt`
