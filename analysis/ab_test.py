"""
Pricing-page A/B test readout (fictional company, synthetic data).

Experiment: accounts that signed up 1 Jul - 30 Sep 2025 were randomised 50/50 at signup to
  A (control)   - current pricing page
  B (treatment) - pricing page with an annual-discount banner
Unit of randomisation and analysis: account.
Primary metric : trial-to-paid conversion (paid within the 14-day trial). All test accounts have finished the trial.
Guardrails     : average starting MRR of converters, plan mix, activation rate, 60-day early churn of converters.

Methodology
  * SRM: chi-square goodness-of-fit against the designed 50/50 split (alarm if p < 0.01).
  * Primary: two-sided two-proportion z-test (alpha = 0.05); 95% Newcomb CI for the absolute difference;
    bootstrap (10,000 resamples) CI for the relative lift; Bayesian P(B > A) with Beta(1,1) priors as a complement.
  * Guardrails: Welch t-test (MRR), chi-square (plan mix), z-tests (activation, early churn).
    A guardrail "fails" if it is significantly worse for B at alpha = 0.05.
  * Power: achieved power for the observed effect, MDE at 80% power for the actual sample, required sample per
    arm to detect the observed lift, and the extra weeks of traffic that would take.
  * Decision rule (not p-value alone): SHIP if primary is significant with CI > 0 and no guardrail fails;
    DO NOT SHIP if the effect is significantly negative or a guardrail fails; otherwise CONTINUE TESTING
    when the test is under-powered for a commercially meaningful effect.

Outputs: reports/ab_test/ab_test_readout.md, reports/ab_test/ab_test_results.json,
         reports/figures/ab_test/*.png, data/marts/ab_test_summary.parquet
"""
import json

import duckdb
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter
from scipy import stats
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_effectsize, proportions_ztest

import viz_style as vs
from viz_style import plt

vs.apply()
ALPHA, POWER = 0.05, 0.80
rng = np.random.default_rng(42)
OUT = vs.ROOT / "reports" / "ab_test"
OUT.mkdir(parents=True, exist_ok=True)

with duckdb.connect(str(vs.DB), read_only=True) as con:
    df = con.sql("""
        select a.account_id,
               a.pricing_page_variant                          as variant,
               a.signup_date,
               a.is_paying_customer::int                       as converted,
               a.is_activated::int                             as activated,
               s.mrr                                           as start_mrr,
               p.plan_name                                     as start_plan,
               (a.churned_date is not null
                and a.churned_date <= a.first_paid_date + interval 60 day)::int as churned_60d
        from marts.dim_accounts a
        left join staging.stg_subscriptions s on s.account_id = a.account_id and s.start_reason = 'new'
        left join marts.dim_plans p on p.plan_id = s.plan_id
        where a.pricing_page_variant is not null
    """).df()

R = {}
# ------------------------------------------------------------------ 1. sample sizes and SRM
n = df.variant.value_counts().reindex(["A", "B"])
srm_chi2, srm_p = stats.chisquare(n.values)
R["sample"] = {"n_A": int(n.A), "n_B": int(n.B), "srm_p_value": float(srm_p), "srm_ok": bool(srm_p >= 0.01),
               "test_window": f"{df.signup_date.min():%Y-%m-%d} to {df.signup_date.max():%Y-%m-%d}"}

# ------------------------------------------------------------------ 2. primary metric
x = df.groupby("variant").converted.sum().reindex(["A", "B"])
pA, pB = x.A / n.A, x.B / n.B
z, p_val = proportions_ztest([x.B, x.A], [n.B, n.A])
ci_lo, ci_hi = confint_proportions_2indep(x.B, n.B, x.A, n.A, method="newcomb", alpha=ALPHA)
boot_a = rng.binomial(n.A, pA, 10_000) / n.A
boot_b = rng.binomial(n.B, pB, 10_000) / n.B
rel_lo, rel_hi = np.percentile(boot_b / boot_a - 1, [2.5, 97.5])
post_a = rng.beta(1 + x.A, 1 + n.A - x.A, 100_000)
post_b = rng.beta(1 + x.B, 1 + n.B - x.B, 100_000)
R["primary"] = {"conv_A": pA, "conv_B": pB, "abs_lift": pB - pA, "abs_lift_ci95": [ci_lo, ci_hi],
                "rel_lift": pB / pA - 1, "rel_lift_ci95_bootstrap": [rel_lo, rel_hi],
                "z": z, "p_value": p_val, "significant": bool(p_val < ALPHA),
                "bayes_prob_B_better": float((post_b > post_a).mean())}

# ------------------------------------------------------------------ 3. guardrails
conv = df[df.converted == 1]
mA, mB = conv.loc[conv.variant == "A", "start_mrr"], conv.loc[conv.variant == "B", "start_mrr"]
t_mrr, p_mrr = stats.ttest_ind(mB, mA, equal_var=False)
mix = pd.crosstab(conv.variant, conv.start_plan).reindex(columns=["Starter", "Pro", "Business"])
_, p_mix, _, _ = stats.chi2_contingency(mix)
act = df.groupby("variant").activated.sum().reindex(["A", "B"])
_, p_act = proportions_ztest([act.B, act.A], [n.B, n.A])
ch = conv.groupby("variant").churned_60d.agg(["sum", "count"]).reindex(["A", "B"])
_, p_ch = proportions_ztest([ch.loc["B", "sum"], ch.loc["A", "sum"]], [ch.loc["B", "count"], ch.loc["A", "count"]])
guard = [
    {"metric": "Avg starting MRR of converters", "A": mA.mean(), "B": mB.mean(), "p_value": p_mrr,
     "worse_for_B": bool(mB.mean() < mA.mean()), "test": "Welch t-test"},
    {"metric": "Plan mix of converters (Starter/Pro/Business)", "A": mix.loc["A"].div(mix.loc["A"].sum()).round(3).tolist(),
     "B": mix.loc["B"].div(mix.loc["B"].sum()).round(3).tolist(), "p_value": p_mix,
     "worse_for_B": bool(mix.loc["B", "Starter"] / mix.loc["B"].sum() > mix.loc["A", "Starter"] / mix.loc["A"].sum()),
     "test": "chi-square"},
    {"metric": "Activation rate (invited teammate)", "A": act.A / n.A, "B": act.B / n.B, "p_value": p_act,
     "worse_for_B": bool(act.B / n.B < act.A / n.A), "test": "two-proportion z"},
    {"metric": "60-day churn of converters", "A": ch.loc["A", "sum"] / ch.loc["A", "count"],
     "B": ch.loc["B", "sum"] / ch.loc["B", "count"], "p_value": p_ch,
     "worse_for_B": bool(ch.loc["B", "sum"] / ch.loc["B", "count"] > ch.loc["A", "sum"] / ch.loc["A", "count"]),
     "test": "two-proportion z"},
]
BONF = ALPHA / len(guard)          # multiple guardrails -> Bonferroni threshold for "real" differences
for g in guard:
    g["fails"] = bool(g["worse_for_B"] and g["p_value"] < ALPHA)       # conservative: any harm at alpha fails
    if g["fails"]:
        g["status"] = "FAIL - worse for B"
    elif g["p_value"] < BONF:
        g["status"] = "OK - B better (significant after Bonferroni)"
    elif g["p_value"] < ALPHA:
        g["status"] = f"OK - B better, but not significant after Bonferroni (p >= {BONF:.4f}); treat as noise"
    else:
        g["status"] = "OK - no significant difference"
R["guardrails"] = guard

# ------------------------------------------------------------------ 4. power and MDE
pw = NormalIndPower()
n_arm = int(n.min())
obs_es = proportion_effectsize(pB, pA)
achieved = pw.power(effect_size=abs(obs_es), nobs1=n_arm, alpha=ALPHA)
mde_es = pw.solve_power(nobs1=n_arm, alpha=ALPHA, power=POWER)
# convert Cohen's h back to a conversion rate: h = 2 asin(sqrt(p2)) - 2 asin(sqrt(p1))
mde_p = np.sin(np.arcsin(np.sqrt(pA)) + mde_es / 2) ** 2
need_obs = pw.solve_power(effect_size=abs(obs_es), alpha=ALPHA, power=POWER) if obs_es else np.inf
need_10 = pw.solve_power(effect_size=proportion_effectsize(pA * 1.10, pA), alpha=ALPHA, power=POWER)
weekly = len(df) / ((df.signup_date.max() - df.signup_date.min()).days / 7) / 2      # per arm
R["power"] = {"n_per_arm": n_arm, "achieved_power_observed_effect": achieved,
              "mde_abs_80pct_power": mde_p - pA, "mde_rel_80pct_power": mde_p / pA - 1,
              "n_per_arm_needed_for_observed_lift": float(np.ceil(need_obs)),
              "n_per_arm_needed_for_10pct_lift": float(np.ceil(need_10)),
              "signups_per_arm_per_week": weekly,
              "extra_weeks_for_observed_lift": float(max(0, np.ceil((need_obs - n_arm) / weekly)))}

# ------------------------------------------------------------------ 5. business impact & decision
monthly_signups = len(df) / 3
impact = (pB - pA) * monthly_signups * mB.mean()
impact_lo = ci_lo * monthly_signups * mB.mean()
impact_hi = ci_hi * monthly_signups * mB.mean()
R["impact"] = {"monthly_signups_assumed": monthly_signups,
               "incremental_new_mrr_per_month_point": impact, "ci95": [impact_lo, impact_hi]}

failed = [g["metric"] for g in guard if g["fails"]]
if failed or (R["primary"]["significant"] and pB < pA):
    decision = "DO NOT SHIP"
    why = ("a guardrail is significantly worse for B: " + ", ".join(failed)) if failed else \
          "B significantly reduces conversion"
elif R["primary"]["significant"] and ci_lo > 0:
    decision = "SHIP"
    why = "conversion lift is statistically significant, the whole CI is positive and no guardrail is harmed"
else:
    decision = "CONTINUE TESTING"
    why = (f"the point estimate is {R['primary']['rel_lift']:+.1%} with P(B>A) = {R['primary']['bayes_prob_B_better']:.0%}, "
           f"but the test only has {achieved:.0%} power for an effect of this size; the 95% CI "
           f"({ci_lo:+.2%} to {ci_hi:+.2%}) still includes zero. No guardrail is harmed.")
R["decision"] = {"recommendation": decision, "rationale": why}

# ------------------------------------------------------------------ 6. charts
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
ax = axes[0]
for i, (v, p_, nn) in enumerate([("A (control)", pA, n.A), ("B (annual-discount banner)", pB, n.B)]):
    se = np.sqrt(p_ * (1 - p_) / nn)
    ax.bar(i, p_, color=[vs.NEUTRAL, vs.SERIES[0]][i], width=0.5)
    ax.errorbar(i, p_, yerr=1.96 * se, color=vs.TEXT, capsize=6, lw=1.4)
    ax.text(i + 0.28, p_, f"{p_:.2%}\n(n={nn:,})", va="center", fontsize=9)
ax.set_xticks([0, 1], ["A (control)", "B (banner)"])
ax.set_xlim(-0.5, 1.9)
ax.yaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_title(f"B converts {R['primary']['rel_lift']:+.1%} better (p = {p_val:.3f})")
vs.subtitle(ax, "Trial-to-paid conversion by variant, with 95% confidence intervals")
ax = axes[1]
lifts = np.linspace(0.0, 0.30, 61)
for k, (mult, lab) in enumerate([(1, f"Actual sample ({n_arm:,}/arm)"), (2, "2x sample"), (3, "3x sample")]):
    pows = [pw.power(effect_size=proportion_effectsize(pA * (1 + l), pA), nobs1=n_arm * mult, alpha=ALPHA) if l else ALPHA
            for l in lifts]
    ax.plot(lifts, pows, color=vs.SERIES[k], label=lab)
ax.axhline(POWER, color=vs.TEXT_2, ls="--", lw=1)
ax.axvline(R["primary"]["rel_lift"], color=vs.SERIES[1], ls=":", lw=1.2)
ax.text(R["primary"]["rel_lift"], 0.03, " observed lift", color=vs.TEXT_2, fontsize=8)
ax.text(0.30, POWER + 0.02, "80% power", ha="right", fontsize=8, color=vs.TEXT_2)
ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.yaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlabel("True relative lift in conversion")
ax.legend(loc="upper left", fontsize=8.5)
ax.set_title(f"MDE at 80% power is a {R['power']['mde_rel_80pct_power']:.0%} relative lift")
vs.subtitle(ax, "Was the test big enough? Power curve by sample size")
vs.footnote(fig)
vs.save(fig, "ab_conversion_and_power", "ab_test")

# ------------------------------------------------------------------ 7. outputs
(OUT / "ab_test_results.json").write_text(json.dumps(R, indent=2, default=float), encoding="utf-8")
summary = pd.DataFrame([
    {"metric": "Accounts", "A": n.A, "B": n.B, "difference": n.B - n.A, "p_value": srm_p},
    {"metric": "Conversion rate", "A": pA, "B": pB, "difference": pB - pA, "p_value": p_val},
] + [{"metric": g["metric"], "A": g["A"] if np.isscalar(g["A"]) else None, "B": g["B"] if np.isscalar(g["B"]) else None,
      "difference": (g["B"] - g["A"]) if np.isscalar(g["A"]) else None, "p_value": g["p_value"]} for g in guard])
summary["decision"] = decision
vs.MARTS_OUT.mkdir(parents=True, exist_ok=True)
summary.to_parquet(vs.MARTS_OUT / "ab_test_summary.parquet", index=False)


def fmt(v):
    return f"{v:.2%}" if isinstance(v, float) and abs(v) < 1 else (f"{v:,.1f}" if isinstance(v, float) else str(v))


P = R["primary"]
W = R["power"]
md = f"""# Pricing-page A/B test readout

> Fictional company, synthetic data. Generated by `analysis/ab_test.py`; every number below is computed on this run.

## Recommendation: **{decision}**

{why[0].upper() + why[1:]}.

## Design
- **Hypothesis:** an annual-discount banner on the pricing page (B) increases trial-to-paid conversion vs the current page (A).
- **Randomisation unit:** account, 50/50 at signup. **Window:** {R['sample']['test_window']} signups (all have completed the 14-day trial).
- **Primary metric:** trial-to-paid conversion. **Guardrails:** starting MRR, plan mix, activation, 60-day churn of converters.
- **Alpha** {ALPHA}, two-sided. **Target power** {POWER:.0%}.

## Sample and SRM
| | A (control) | B (treatment) |
|---|---:|---:|
| Accounts | {n.A:,} | {n.B:,} |
| Converted | {x.A:,} | {x.B:,} |

SRM chi-square p = {srm_p:.3f} -> {'no sample-ratio mismatch' if srm_p >= 0.01 else '**SRM detected - investigate assignment before reading results**'}.

## Primary metric
| Metric | Value |
|---|---|
| Conversion A / B | {pA:.2%} / {pB:.2%} |
| Absolute lift (B - A) | {P['abs_lift']:+.2%} (95% CI {ci_lo:+.2%} to {ci_hi:+.2%}) |
| Relative lift | {P['rel_lift']:+.1%} (bootstrap 95% CI {rel_lo:+.1%} to {rel_hi:+.1%}) |
| z / p-value | {z:.2f} / {p_val:.4f} |
| Bayesian P(B > A) | {P['bayes_prob_B_better']:.1%} |

## Guardrails
| Guardrail | A | B | p-value | Status |
|---|---|---|---:|---|
""" + "\n".join(f"| {g['metric']} | {fmt(g['A']) if np.isscalar(g['A']) else g['A']} | {fmt(g['B']) if np.isscalar(g['B']) else g['B']} | "
                f"{g['p_value']:.3f} | {g['status']} |" for g in guard) + f"""

## Power and minimum detectable effect
- Sample per arm: **{n_arm:,}**. Achieved power for the observed effect: **{W['achieved_power_observed_effect']:.0%}**.
- MDE at 80% power with this sample: **{W['mde_abs_80pct_power']:+.2%} absolute ({W['mde_rel_80pct_power']:+.0%} relative)**.
- Sample per arm needed to detect the observed lift at 80% power: **{W['n_per_arm_needed_for_observed_lift']:,.0f}**
  ({'already reached by this test' if W['extra_weeks_for_observed_lift'] == 0 else f"~{W['extra_weeks_for_observed_lift']:.0f} more weeks at {W['signups_per_arm_per_week']:,.0f} signups/arm/week"}).
- Sample per arm needed for a 10% relative lift: {W['n_per_arm_needed_for_10pct_lift']:,.0f}.

## Business impact (if the point estimate is real)
At ~{monthly_signups:,.0f} signups/month and ${mB.mean():.0f} average starting MRR, B would add about
**${impact:,.0f} of new MRR per month** (95% CI ${impact_lo:,.0f} to ${impact_hi:,.0f}), i.e. ~${impact * 12:,.0f} ARR per month of signups.

## Assumptions and caveats
- Accounts are independent; no cross-variant contamination (one account sees one variant).
- The z-test relies on the normal approximation (np > 10 in both arms - satisfied).
- One primary metric is pre-registered, so no multiple-comparison correction is applied to it. Guardrails are read as
  "do no harm" at alpha = {ALPHA} (conservative), and any *improvement* is only credited if it survives Bonferroni (p < {BONF:.4f}).
- A conversion lift does not guarantee an LTV lift: annual-discount buyers may retain differently. Monitor 6-month retention after launch.
- No peeking: the readout is computed once on the full, pre-defined window.
- **Winner's curse:** the observed lift ({P['rel_lift']:+.1%}) is close to the MDE ({W['mde_rel_80pct_power']:+.0%}), so a significant
  result at this sample size tends to *overstate* the true effect. Forecast impact from the lower part of the CI, not the point estimate.

![A/B test](../figures/ab_test/ab_conversion_and_power.png)
"""
(OUT / "ab_test_readout.md").write_text(md, encoding="utf-8")
print(f"SRM p={srm_p:.3f} | conv A={pA:.2%} B={pB:.2%} rel={P['rel_lift']:+.1%} p={p_val:.4f} "
      f"CI=[{ci_lo:+.2%},{ci_hi:+.2%}] P(B>A)={P['bayes_prob_B_better']:.1%}")
print(f"power={achieved:.0%} MDE_rel={W['mde_rel_80pct_power']:.1%} n_needed={W['n_per_arm_needed_for_observed_lift']:,.0f}")
print("guardrails:", [(g["metric"], round(float(g["p_value"]), 3), g["status"]) for g in guard])
print(f"Decision: {decision} - {why}")
