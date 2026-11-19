"""CLI: ``python -m energy_pipeline {run,backfill,report}``."""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from datetime import date
from pathlib import Path

from energy_pipeline.pipeline import Settings, backfill, run_day
from energy_pipeline.report import build_report
from energy_pipeline.sources import SyntheticSmardSource


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="energy_pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="load a single delivery day")
    p_run.add_argument("--date", type=date.fromisoformat, required=True)

    p_bf = sub.add_parser("backfill", help="(re)load an inclusive date range")
    p_bf.add_argument("--start", type=date.fromisoformat, required=True)
    p_bf.add_argument("--end", type=date.fromisoformat, required=True)

    p_rep = sub.add_parser("report", help="write a Markdown KPI report")
    p_rep.add_argument("--out", type=Path, default=Path("reports/summary.md"))

    for p in (p_run, p_bf):
        p.add_argument("--source", choices=["synthetic", "smard"], default=None)
        p.add_argument(
            "--drop-hour-on",
            type=date.fromisoformat,
            action="append",
            default=[],
            help="synthetic source only: simulate an incomplete upstream delivery on this date",
        )

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    if getattr(args, "source", None):
        settings = Settings(settings.raw_dir, settings.db_path, args.source)

    source = None
    if getattr(args, "drop_hour_on", None):
        if settings.source != "synthetic":
            parser.error("--drop-hour-on only works with the synthetic source")
        source = SyntheticSmardSource(drop_hour_on=set(args.drop_hour_on))

    if args.cmd == "run":
        result = run_day(args.date, settings, source)
        print(result)
        return 0 if result.status == "loaded" else 1
    if args.cmd == "backfill":
        results = backfill(args.start, args.end, settings, source)
        counts = Counter(r.status for r in results)
        rows = sum(r.rows_inserted for r in results)
        print(f"days={len(results)} {dict(counts)} rows_inserted={rows}")
        for r in results:
            if r.status != "loaded":
                print(f"  {r.delivery_date}: {r.error}")
        return 0 if counts.get("failed_quality", 0) == 0 else 1
    text = build_report(settings.db_path)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
