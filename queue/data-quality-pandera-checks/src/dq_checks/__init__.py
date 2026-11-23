"""Reusable data-quality layer built on pandera: contracts, checks, reports and a CI gate."""

from dq_checks.validate import ValidationResult, validate_tables

__all__ = ["ValidationResult", "validate_tables"]
__version__ = "0.1.0"
