"""Analytics on the loaded warehouse: monthly KPIs and a Markdown summary."""

from __future__ import annotations

from pathlib import Path

import duckdb

MONTHLY_SQL = """
SELECT
    strftime(delivery_date, '%Y-%m')            AS month,
    count(*)                                    AS days,
    round(avg(base_avg), 2)                     AS base_avg,
    round(avg(peak_avg), 2)                     AS peak_avg,
    round(avg(intraday_spread), 2)              AS avg_spread,
    sum(negative_hours)                         AS negative_hours,
    min(min_price)                              AS min_price,
    max(max_price)                              AS max_price
FROM daily_price_stats
GROUP BY 1
ORDER BY 1
"""

HOURLY_PROFILE_SQL = """
SELECT local_hour, round(avg(price_eur_mwh), 2) AS avg_price
FROM hourly_prices
GROUP BY 1
ORDER BY 1
"""

WEEKDAY_VS_WEEKEND_SQL = """
SELECT
    CASE WHEN isodow(delivery_date) >= 6 THEN 'weekend' ELSE 'weekday' END AS day_type,
    round(avg(base_avg), 2) AS base_avg,
    round(avg(negative_hours), 2) AS avg_negative_hours
FROM daily_price_stats
GROUP BY 1
ORDER BY 1
"""

HEALTH_SQL = """
SELECT
    (SELECT count(*) FROM hourly_prices)                       AS hourly_rows,
    (SELECT count(*) FROM daily_price_stats)                   AS days_loaded,
    (SELECT count(*) FROM daily_price_stats WHERE n_hours = 23) AS days_23h,
    (SELECT count(*) FROM daily_price_stats WHERE n_hours = 25) AS days_25h,
    (SELECT count(*) - count(DISTINCT ts_utc) FROM hourly_prices) AS duplicate_rows,
    (SELECT count(*) FROM load_audit)                          AS load_runs
"""


def _md_table(con: duckdb.DuckDBPyConnection, sql: str) -> str:
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def health(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    cur = con.execute(HEALTH_SQL)
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, cur.fetchone(), strict=True))


def build_report(db_path: Path | str) -> str:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        h = health(con)
        parts = [
            "# Day-ahead price report",
            "",
            "_Generated from the DuckDB warehouse by `python -m energy_pipeline report`._",
            "",
            "## Pipeline health",
            "",
            "\n".join(f"- **{k}**: {v}" for k, v in h.items()),
            "",
            "## Monthly KPIs (EUR/MWh)",
            "",
            _md_table(con, MONTHLY_SQL),
            "",
            "## Weekday vs weekend",
            "",
            _md_table(con, WEEKDAY_VS_WEEKEND_SQL),
            "",
            "## Average price by local hour",
            "",
            _md_table(con, HOURLY_PROFILE_SQL),
            "",
        ]
        return "\n".join(parts)
    finally:
        con.close()
