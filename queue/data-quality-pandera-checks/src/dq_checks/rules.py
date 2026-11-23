"""Central catalogue of data-quality rules.

Every check used anywhere in the project is registered here with a severity and a
human-readable description. Keeping the catalogue in one place means the report,
the CI gate and the documentation all agree on what a rule means.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"  # row is quarantined, gate fails
    WARNING = "warning"  # row is kept, reported for follow-up


@dataclass(frozen=True)
class Rule:
    name: str
    severity: Severity
    description: str


_RULES: list[Rule] = [
    # parsing / structural
    Rule("parse_error", Severity.ERROR, "value cannot be parsed into the expected type"),
    Rule("not_nullable", Severity.ERROR, "required value is missing"),
    Rule("unique_key", Severity.ERROR, "primary key value is duplicated"),
    Rule("missing_column", Severity.ERROR, "expected column is missing from the file"),
    Rule("unexpected_column", Severity.ERROR, "file contains a column the contract does not allow"),
    # customers
    Rule("positive_id", Severity.ERROR, "identifier must be a positive integer"),
    Rule("email_format", Severity.ERROR, "email does not look like local@domain.tld"),
    Rule("email_lowercase", Severity.WARNING, "email should be stored lower-case"),
    Rule("valid_country", Severity.ERROR, "country is not an allowed ISO-3166 alpha-2 code"),
    Rule("valid_segment", Severity.ERROR, "segment must be consumer or business"),
    Rule("not_in_future", Severity.ERROR, "timestamp lies after the as-of date of the load"),
    # orders
    Rule("valid_status", Severity.ERROR, "order status is not part of the lifecycle"),
    Rule("valid_currency", Severity.ERROR, "currency must be EUR or CHF"),
    Rule("non_negative_amount", Severity.ERROR, "amount must be >= 0"),
    Rule("shipped_after_ordered", Severity.ERROR, "shipped_ts is earlier than order_ts"),
    Rule("delivered_has_ship_ts", Severity.ERROR, "shipped/delivered order has no shipped_ts"),
    # order items
    Rule("sku_format", Severity.ERROR, "sku must match SKU-#####"),
    Rule("quantity_range", Severity.ERROR, "quantity must be between 1 and 100"),
    Rule("positive_price", Severity.ERROR, "unit_price must be > 0"),
    Rule("price_plausible", Severity.WARNING, "unit_price above 2,000 EUR is unusual for this shop"),
    # cross-table
    Rule("fk_customer_exists", Severity.ERROR, "order references a customer_id that does not exist"),
    Rule("fk_order_exists", Severity.ERROR, "order item references an order_id that does not exist"),
    Rule("total_matches_items", Severity.ERROR, "order total differs from sum of line items by > 0.01"),
    Rule("order_after_signup", Severity.WARNING, "order was placed before the customer signed up"),
]

RULES: dict[str, Rule] = {r.name: r for r in _RULES}


def severity_of(rule_name: str) -> Severity:
    """Severity of a rule; unknown (e.g. pandera-internal) checks default to ERROR."""
    rule = RULES.get(rule_name)
    return rule.severity if rule else Severity.ERROR
