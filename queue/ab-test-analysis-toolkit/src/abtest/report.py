"""Render an experiment analysis as a stakeholder-friendly Markdown report."""

from __future__ import annotations

from .analysis import ExperimentAnalysis


def _pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:+.{digits}f}%"


def _fmt(x: float) -> str:
    return f"{x:.4f}" if abs(x) < 10 else f"{x:.2f}"


def _pval(p: float) -> str:
    return "<0.0001" if p < 1e-4 else f"{p:.4f}"


def render_markdown(a: ExperimentAnalysis, plan: dict | None = None,
                    simulations: dict | None = None, title: str = "Experiment report") -> str:
    lines = [f"# {title}", "", f"**Decision:** {a.decision}", ""]
    if plan:
        lines += ["## Plan", "",
                  f"- Baseline conversion {plan['baseline']:.2%}, MDE {plan['mde']:.0%} relative, "
                  f"alpha {plan['alpha']}, power {plan['power']:.0%}",
                  f"- Required sample: **{plan['n_per_group']:,} users per group** "
                  f"(~{plan['days']} days at {plan['daily_traffic']:,} users/day)",
                  f"- MDE achievable with the collected sample: "
                  f"{plan['achieved_mde']:.2%} relative",
                  ""]
    s = a.srm
    lines += ["## Sample ratio check", "",
              f"Control {a.n_control:,} vs treatment {a.n_treatment:,} "
              f"(chi2 = {s['chi2']:.2f}, p = {s['p_value']:.3f}) -> "
              + ("**SRM detected**" if s["srm_detected"] else "no mismatch"), ""]
    lines += ["## Metrics", "",
              "| Metric | Role | Control | Treatment | Rel. lift | 95% CI (rel.) | p | p (Holm) |",
              "|---|---|---|---|---|---|---|---|"]
    for r in a.results:
        lines.append(
            f"| {r.metric} | {a.roles[r.metric]} | {_fmt(r.control_mean)} | "
            f"{_fmt(r.treatment_mean)} | {_pct(r.rel_lift)} | "
            f"[{_pct(r.rel_ci_low)}, {_pct(r.rel_ci_high)}] | {_pval(r.p_value)} | "
            f"{_pval(a.adjusted_p[r.metric])} |")
    lines.append("")
    b = a.bayes
    lines += ["## Bayesian view (primary metric, Beta(1,1) prior)", "",
              f"- P(treatment > control) = **{b['prob_treatment_better']:.1%}**",
              f"- Relative lift median {_pct(b['rel_lift_median'])}, 95% credible interval "
              f"[{_pct(b['rel_lift_ci_low'])}, {_pct(b['rel_lift_ci_high'])}]",
              f"- Expected loss if we ship: {b['expected_loss_treatment'] * 100:.4f} pp; "
              f"if we keep control: {b['expected_loss_control'] * 100:.4f} pp",
              f"- Expected-loss rule says: {b['decision']}", ""]
    for metric, c in a.cuped.items():
        raw, adj = c["raw"], c["adjusted"]
        lines += [f"## CUPED variance reduction ({metric})", "",
                  f"- corr(pre-period, outcome) = {c['correlation']:.3f}, theta = {c['theta']:.4f}",
                  f"- Variance reduced by **{c['variance_reduction']:.1%}**, "
                  f"CI width reduced by {c['ci_width_reduction']:.1%}",
                  f"- Raw diff {raw['abs_diff']:+.3f} [{raw['ci_low']:+.3f}, "
                  f"{raw['ci_high']:+.3f}], "
                  f"p = {_pval(raw['p_value'])}",
                  f"- CUPED diff {adj['abs_diff']:+.3f} [{adj['ci_low']:+.3f}, "
                  f"{adj['ci_high']:+.3f}], p = {_pval(adj['p_value'])}", ""]
    for metric, (lo, hi) in a.bootstrap.items():
        lines += [f"Bootstrap 95% CI for {metric} difference: [{lo:+.3f}, {hi:+.3f}]", ""]
    if a.segments:
        lines += ["## Segments (exploratory, not used for the decision)", "",
                  "| Segment | Users | Control | Treatment | Rel. lift | p |",
                  "|---|---|---|---|---|---|"]
        for g in a.segments:
            lines.append(f"| {g['segment']} | {g['n']:,} | {g['control_mean']:.4f} | "
                         f"{g['treatment_mean']:.4f} | {_pct(g['rel_lift'])} | "
                         f"{_pval(g['p_value'])} |")
        lines.append("")
    if simulations:
        pk, pw = simulations["peeking"], simulations["power"]
        lines += ["## Method checks (Monte Carlo)", "",
                  f"- Empirical power at the planned sample: {pw['empirical_power']:.1%} "
                  f"(analytic {pw['analytic_power']:.1%}, {pw['n_sims']:,} sims)",
                  f"- A/A false-positive rate, single look: {pk['fixed_horizon_fpr']:.1%}",
                  f"- A/A false-positive rate when peeking {pk['n_looks']}x and stopping at "
                  f"first p<0.05: **{pk['peeking_fpr']:.1%}**",
                  f"- Peeking with Bonferroni alpha/{pk['n_looks']}: "
                  f"{pk['bonferroni_peeking_fpr']:.1%}", ""]
    lines += ["_Data are synthetic (fixed seed); figures illustrate the method, not a real shop._",
              ""]
    return "\n".join(lines)
