"""End-to-end runner: generate → load raw → dbt build (models + tests) → report.

Usage:
    python -m ecom.pipeline                 # full run with defaults
    python -m ecom.pipeline --customers 300 # smaller, faster run
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ecom.generate import GenConfig, generate
from ecom.load import load_raw
from ecom.report import build_report, format_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = PROJECT_ROOT / "dbt_project"


def run_dbt(args: list[str], db_path: Path) -> None:
    """Invoke dbt programmatically against the given DuckDB file; raise on failure."""
    from dbt.cli.main import dbtRunner

    os.environ["DUCKDB_PATH"] = str(db_path.resolve())
    result = dbtRunner().invoke(
        [*args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    )
    if not result.success:
        raise RuntimeError(f"dbt {' '.join(args)} failed: {result.exception}")


def run_pipeline(
    data_dir: Path,
    db_path: Path,
    cfg: GenConfig | None = None,
) -> dict[str, list[tuple]]:
    counts = generate(data_dir, cfg)
    print("Generated raw extracts:", counts)
    loaded = load_raw(data_dir, db_path)
    print("Loaded into raw schema:", loaded)
    run_dbt(["build"], db_path)
    return build_report(db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data" / "raw")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "warehouse.duckdb")
    parser.add_argument("--customers", type=int, default=GenConfig.n_customers)
    parser.add_argument("--seed", type=int, default=GenConfig.seed)
    args = parser.parse_args()

    cfg = GenConfig(n_customers=args.customers, seed=args.seed)
    report = run_pipeline(args.data_dir, args.db, cfg)
    print(format_report(report))


if __name__ == "__main__":
    main()
