"""Small display helpers for the dashboard (kept out of app.py so they are unit-testable)."""

from __future__ import annotations


def fmt_eur(value: float) -> str:
    """Compact euro format that fits in a metric tile (e.g. €2.77M, €48.3k, €950)."""
    if abs(value) >= 1e6:
        return f"€{value / 1e6:.2f}M"
    if abs(value) >= 1e4:
        return f"€{value / 1e3:.1f}k"
    return f"€{value:,.0f}"


def fmt_delta(value: float | None, unit: str = "%") -> str | None:
    """Signed delta label for st.metric; None hides the delta when there is no baseline."""
    return None if value is None else f"{value:+.1f} {unit}"
