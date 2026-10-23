"""Shared validation result model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    validation_id: str
    layer: str
    validation_name: str
    source_object: str
    target_object: str
    expected_value: str
    actual_value: str
    status: str
    variance: str = ""
    remarks: str = ""
    record_key: str = ""


def result(
    validation_id: str,
    layer: str,
    name: str,
    source: str,
    target: str,
    expected: Any,
    actual: Any,
    status: str,
    variance: Any = "",
    remarks: str = "",
    record_key: Any = "",
) -> ValidationResult:
    return ValidationResult(
        validation_id=validation_id,
        layer=layer,
        validation_name=name,
        source_object=source,
        target_object=target,
        expected_value=str(expected),
        actual_value=str(actual),
        status=status,
        variance=str(variance),
        remarks=remarks,
        record_key=str(record_key),
    )
