"""CLI: generate a synthetic experiment, plan it, analyse it and write the report."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .analysis import analyze_experiment
from .data import generate_experiment
from .power import duration_days, mde_proportions, power_proportions, sample_size_proportions
from .report import render_markdown
from .simulation import simulate_peeking, simulate_power


def build_plan(baseline: float, mde: float, alpha: float, power: float, daily_traffic: int,
               n_collected: int) -> dict:
    n = sample_size_proportions(baseline, mde, alpha, power)
    return {"baseline": baseline, "mde": mde, "alpha": alpha, "power": power,
            "n_per_group": n, "daily_traffic": daily_traffic,
            "days": duration_days(n, daily_traffic),
            "achieved_mde": mde_proportions(baseline, n_collected, alpha, power)}


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-users", type=int, default=60_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sims", type=int, default=2000, help="Monte-Carlo simulations")
    ap.add_argument("--baseline", type=float, default=0.075, help="planning baseline rate")
    ap.add_argument("--mde", type=float, default=0.10, help="planning relative MDE")
    ap.add_argument("--daily-traffic", type=int, default=4000)
    ap.add_argument("--out", type=Path, default=Path("reports"))
    args = ap.parse_args(argv)

    df = generate_experiment(args.n_users, args.seed)
    analysis = analyze_experiment(df, seed=args.seed)
    plan = build_plan(args.baseline, args.mde, 0.05, 0.8, args.daily_traffic,
                      min(analysis.n_control, analysis.n_treatment))

    n_plan = plan["n_per_group"]
    p1, p2 = args.baseline, args.baseline * (1 + args.mde)
    simulations = {
        "power": {"n_sims": args.sims,
                  "empirical_power": simulate_power(p1, p2, n_plan, args.sims, seed=args.seed),
                  "analytic_power": power_proportions(p1, args.mde, n_plan)},
        "peeking": simulate_peeking(p1, n_plan, n_looks=20, n_sims=args.sims, seed=args.seed),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    md = render_markdown(analysis, plan, simulations, "Checkout redesign (synthetic) - report")
    (args.out / "report.md").write_text(md, encoding="utf-8")
    payload = {"plan": plan, "simulations": simulations,
               **{k: v for k, v in asdict(analysis).items() if k != "results"},
               "results": [r.to_dict() for r in analysis.results]}
    (args.out / "results.json").write_text(json.dumps(payload, indent=2, default=float))
    print(md)
    return payload


if __name__ == "__main__":
    main()
