"""Compatibility entry point for the modular Assignment 2 framework."""

from src.business_rules import validate_business_rules
from src.customer_validator import validate_customers
from src.database import load_target
from src.file_reader import read_customer_file, read_delimited_file, read_sales_file
from src.main import main, run
from src.models import ValidationResult, result
from src.reconciliation import equal_values as _equal_values
from src.reconciliation import reconcile
from src.sales_validator import validate_sales as _validate_sales

read_pipe_file = read_delimited_file


def validate_sales(frame, label, columns, validation=None):
    return _validate_sales(frame, label, columns)


if __name__ == "__main__":
    raise SystemExit(main())
