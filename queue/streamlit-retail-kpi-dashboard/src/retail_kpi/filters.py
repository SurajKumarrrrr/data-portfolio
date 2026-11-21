"""Dashboard filter state and its translation into a parameterised SQL WHERE clause."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta


@dataclass(frozen=True)
class Filters:
    """Immutable (hashable) filter state, so it can be used as a cache key.

    Empty tuples mean "no restriction" for that dimension.
    """

    start: date
    end: date
    regions: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"start {self.start} is after end {self.end}")

    @property
    def n_days(self) -> int:
        return (self.end - self.start).days + 1

    def previous_period(self) -> Filters:
        """Same filters, shifted to the equally long period directly before this one."""
        new_end = self.start - timedelta(days=1)
        new_start = new_end - timedelta(days=self.n_days - 1)
        return replace(self, start=new_start, end=new_end)

    def to_sql(self) -> tuple[str, list]:
        """Return ``(where_clause, params)`` for the `sales` view.

        Values are always bound as parameters (never interpolated), so user input from
        the UI cannot inject SQL.
        """
        clauses = ["order_date BETWEEN ? AND ?"]
        params: list = [self.start, self.end]
        for column, values in (
            ("region", self.regions),
            ("category", self.categories),
            ("channel", self.channels),
        ):
            if values:
                placeholders = ", ".join("?" for _ in values)
                clauses.append(f"{column} IN ({placeholders})")
                params.extend(values)
        return "WHERE " + " AND ".join(clauses), params
