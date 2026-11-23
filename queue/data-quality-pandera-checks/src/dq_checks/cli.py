"""Command-line interface: ``dq-checks generate | validate | evaluate``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from dq_checks.evaluate import detection_report, unexpected_flags
from dq_checks.generate import AS_OF, generate
from dq_checks.report import table_summary, write_report
from dq_checks.validate import TABLE_ORDER, ValidationResult, validate_tables


def load_tables(data_dir: Path) -> dict[str, pd.DataFrame]:
    """Read the three CSVs as strings; typing is the validator's job."""
    return {
        name: pd.read_csv(data_dir / f"{name}.csv", dtype=str, keep_default_na=True) for name in TABLE_ORDER
    }


def _run_validation(args: argparse.Namespace) -> ValidationResult:
    result = validate_tables(load_tables(Path(args.data_dir)), as_of=args.as_of)
    write_report(result, Path(args.out_dir), fail_on=args.fail_on)
    print(table_summary(result).to_string(index=False))
    print(f"\nerrors={result.n_errors} warnings={result.n_warnings} -> report in {args.out_dir}/report.md")
    return result


def cmd_generate(args: argparse.Namespace) -> int:
    per_type = 0 if args.clean else args.defects_per_type
    ds = generate(n_customers=args.customers, seed=args.seed, defects_per_type=per_type)
    ds.write(Path(args.out))
    sizes = ", ".join(f"{n}={len(df)}" for n, df in ds.tables().items())
    print(f"wrote {sizes}, injected defects={len(ds.defects)} to {args.out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    result = _run_validation(args)
    passed = result.gate_passed(args.fail_on)
    print(f"gate ({args.fail_on}): {'PASSED' if passed else 'FAILED'}")
    return 0 if passed else 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    result = _run_validation(args)
    defects = pd.read_csv(Path(args.data_dir) / "defects.csv")
    det = detection_report(result.failures, defects)
    extra = unexpected_flags(result.failures, defects)
    print("\n" + det.to_string(index=False))
    total_inj, total_det = int(det["injected"].sum()), int(det["detected"].sum())
    print(f"\ndetected {total_det}/{total_inj} injected defects; flags on unlabelled rows: {len(extra)}")
    det.to_csv(Path(args.out_dir) / "detection.csv", index=False)
    return 0 if total_det == total_inj and extra.empty else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dq-checks", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="write synthetic CSVs (+ defects.csv manifest)")
    g.add_argument("--out", default="data/raw")
    g.add_argument("--customers", type=int, default=500)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--defects-per-type", type=int, default=3)
    g.add_argument("--clean", action="store_true", help="no injected defects")
    g.set_defaults(func=cmd_generate)

    for name, func, help_ in (
        ("validate", cmd_validate, "validate CSVs; exit 1 when the gate fails"),
        ("evaluate", cmd_evaluate, "validate and score detection against defects.csv"),
    ):
        v = sub.add_parser(name, help=help_)
        v.add_argument("--data-dir", default="data/raw")
        v.add_argument("--out-dir", default="reports")
        v.add_argument("--as-of", default=str(AS_OF.date()), help="logical load date")
        v.add_argument("--fail-on", choices=["error", "warning", "never"], default="error")
        v.set_defaults(func=func)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
