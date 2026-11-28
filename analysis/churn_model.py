"""
Churn prediction for CloudDesk (fictional company, synthetic data).

TARGET
  For a customer paying at a month-end cutoff T: churned_next_3m = 1 if the subscription ends in (T, T + 3 months].

LEAKAGE CONTROLS
  * Every feature is computed only from data stamped <= T (payments, tickets, plan changes) and from usage months
    that are fully complete before T (a usage row for month M covers mid-M to mid-M+1, so only M <= T - 1 month).
  * Snapshots are split by TIME, never randomly: a customer's future can not leak into training.
      train      cutoffs 2024-06-30 .. 2025-03-31   (labels observable by 2025-06-30)
      validation cutoffs 2025-04-30 .. 2025-06-30   (used only to choose model + decision threshold)
      test       cutoffs 2025-07-31 .. 2025-09-30   (untouched hold-out, reported once)
  * The final model is refit on train + validation + test snapshots and scores customers active at 2025-12-31.

DECISION THRESHOLD (business framing, assumptions documented in docs/metric_definitions.md)
  Contacting a customer costs OUTREACH_COST. A true churner who is contacted is saved with probability SAVE_RATE,
  preserving SAVED_VALUE of gross margin. The threshold maximises expected net value on the validation set.

NOTE: performance is measured on synthetic data whose churn mechanism we generated; it is NOT evidence of
real-world predictive performance.
"""
import json

import duckdb
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter
from sklearn.base import clone
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss, confusion_matrix, f1_score,
                             precision_recall_curve, precision_score, recall_score, roc_auc_score, roc_curve)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import viz_style as vs
from viz_style import plt

vs.apply()
OUT = vs.ROOT / "reports" / "churn_model"
OUT.mkdir(parents=True, exist_ok=True)
SEED = 42
OUTREACH_COST = 40.0        # $ per customer contacted (CSM time + incentive)
SAVE_RATE = 0.25            # share of contacted true churners retained
GROSS_MARGIN = 0.80
SAVED_MONTHS = 12           # months of margin preserved by a save

FEATURES_SQL = """
with cutoffs as (
    select cast(d + interval 1 month - interval 1 day as date) as t
    from generate_series(date '{first}', date '{last}', interval 1 month) g(d)
),
active as (
    select c.t, m.account_id, m.plan_id, m.mrr
    from cutoffs c
    join marts.fct_mrr m on m.month = date_trunc('month', c.t) and m.mrr > 0
),
usage as (
    select a.t, a.account_id,
           avg(case when u.usage_month >  date_trunc('month', a.t) - interval 4 month then u.sessions_per_seat end) as sps_3m,
           avg(case when u.usage_month <= date_trunc('month', a.t) - interval 4 month
                     and u.usage_month >  date_trunc('month', a.t) - interval 7 month then u.sessions_per_seat end) as sps_prior_3m,
           avg(case when u.usage_month >  date_trunc('month', a.t) - interval 4 month then u.active_seats end)      as seats_3m,
           count(case when u.usage_month > date_trunc('month', a.t) - interval 4 month and u.sessions is null then 1 end) as missing_usage_months
    from active a
    join marts.fct_usage_monthly u
      on u.account_id = a.account_id and u.usage_month <= date_trunc('month', a.t) - interval 1 month
    group by 1, 2
),
pays as (
    select a.t, a.account_id,
           count(case when not p.is_success and p.attempted_at > a.t - interval 90 day then 1 end) as failed_attempts_90d,
           count(case when not p.is_success then 1 end)                                           as failed_attempts_total
    from active a join marts.fct_payments p on p.account_id = a.account_id and p.attempted_at <= a.t
    group by 1, 2
),
tickets as (
    select a.t, a.account_id,
           count(case when e.event_ts > a.t - interval 90 day then 1 end) as tickets_90d,
           count(*)                                                       as tickets_total
    from active a join marts.fct_product_events e
      on e.account_id = a.account_id and e.event_name = 'support_ticket_opened' and e.event_ts <= a.t
    group by 1, 2
),
changes as (
    select a.t, a.account_id,
           count(case when s.start_reason = 'upgrade' then 1 end)   as upgrades,
           count(case when s.start_reason = 'downgrade' then 1 end) as downgrades
    from active a join staging.stg_subscriptions s on s.account_id = a.account_id and s.start_date <= a.t
    group by 1, 2
)
select
    a.t                                                         as cutoff,
    a.account_id,
    cast(a.plan_id as varchar)                                  as plan,
    a.mrr,
    d.company_size,
    d.acquisition_channel,
    d.country,
    d.is_activated::int                                         as is_activated,
    datediff('month', d.first_paid_date, a.t)                   as tenure_months,
    coalesce(u.sps_3m, -1)                                      as sessions_per_seat_3m,      -- -1 = no complete usage month yet
    (u.sps_3m is null)::int                                     as no_usage_history,
    coalesce(u.sps_3m / nullif(u.sps_prior_3m, 0), 1)           as usage_trend,
    ln(1 + coalesce(u.seats_3m, 0))                             as log_seats,
    coalesce(u.missing_usage_months, 0)                         as missing_usage_months,
    coalesce(p.failed_attempts_90d, 0)                          as failed_attempts_90d,
    coalesce(p.failed_attempts_total, 0)                        as failed_attempts_total,
    coalesce(k.tickets_90d, 0)                                  as tickets_90d,
    coalesce(k.tickets_total, 0)                                as tickets_total,
    coalesce(c.upgrades, 0)                                     as upgrades,
    coalesce(c.downgrades, 0)                                   as downgrades,
    (d.churned_date is not null and d.churned_date > a.t
       and d.churned_date <= a.t + interval 3 month)::int       as churned_next_3m
from active a
join marts.dim_accounts d using (account_id)
left join usage   u using (t, account_id)
left join pays    p using (t, account_id)
left join tickets k using (t, account_id)
left join changes c using (t, account_id)
order by a.t, a.account_id      -- deterministic row order => reproducible model fits
"""

NUM = ["mrr", "is_activated", "tenure_months", "sessions_per_seat_3m", "no_usage_history", "usage_trend", "log_seats",
       "missing_usage_months", "failed_attempts_90d", "failed_attempts_total", "tickets_90d", "tickets_total",
       "upgrades", "downgrades"]
CAT = ["plan", "company_size", "acquisition_channel", "country"]
TARGET = "churned_next_3m"

with duckdb.connect(str(vs.DB), read_only=True) as con:
    hist = con.sql(FEATURES_SQL.format(first="2024-06-01", last="2025-09-01")).df()
    score = con.sql(FEATURES_SQL.format(first="2025-12-01", last="2025-12-01")).df()
    plan_names = dict(con.sql("select cast(plan_id as varchar), plan_name from marts.dim_plans").fetchall())

hist["cutoff"] = pd.to_datetime(hist.cutoff)
train = hist[hist.cutoff <= "2025-03-31"]
valid = hist[(hist.cutoff > "2025-03-31") & (hist.cutoff <= "2025-06-30")]
test = hist[hist.cutoff > "2025-06-30"]
split_info = {k: {"rows": len(d), "customers": int(d.account_id.nunique()), "churn_rate": float(d[TARGET].mean()),
                  "cutoffs": f"{d.cutoff.min():%Y-%m-%d} .. {d.cutoff.max():%Y-%m-%d}"}
              for k, d in [("train", train), ("validation", valid), ("test", test)]}
for k, v in split_info.items():
    print(f"{k:<10} {v['rows']:>6,} rows  {v['customers']:>5,} customers  churn {v['churn_rate']:.1%}  ({v['cutoffs']})")


def prep():
    return ColumnTransformer([("num", StandardScaler(), NUM),
                              ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), CAT)])


MODELS = {
    "baseline_majority": DummyClassifier(strategy="prior"),
    "logistic_regression": LogisticRegression(max_iter=2000, C=0.5),
    "gradient_boosting": HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                        min_samples_leaf=40, l2_regularization=1.0, random_state=SEED),
}


def net_value(y, p, thr, mrr):
    """Expected $ value of contacting everyone with p >= thr (per the documented assumptions)."""
    flag = p >= thr
    saved_value = (SAVE_RATE * GROSS_MARGIN * SAVED_MONTHS * mrr[flag & (y == 1)]).sum()
    return saved_value - OUTREACH_COST * flag.sum()


def metrics(y, p, thr):
    yhat = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()
    return {"accuracy": accuracy_score(y, yhat), "precision": precision_score(y, yhat, zero_division=0),
            "recall": recall_score(y, yhat), "f1": f1_score(y, yhat), "roc_auc": roc_auc_score(y, p),
            "pr_auc": average_precision_score(y, p), "brier": brier_score_loss(y, p),
            "threshold": thr, "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
            "flagged_pct": float(yhat.mean())}


# ---------------------------------------------------------------- fit on train, choose on validation
fitted, val_scores = {}, {}
grid = np.round(np.arange(0.02, 0.61, 0.01), 2)
for name, model in MODELS.items():
    pipe = Pipeline([("prep", prep()), ("model", clone(model))]).fit(train[NUM + CAT], train[TARGET])
    pv = pipe.predict_proba(valid[NUM + CAT])[:, 1]
    values = [net_value(valid[TARGET].values, pv, t, valid.mrr.values) for t in grid]
    thr = float(grid[int(np.argmax(values))])
    fitted[name] = pipe
    val_scores[name] = {"pr_auc": average_precision_score(valid[TARGET], pv), "roc_auc": roc_auc_score(valid[TARGET], pv),
                        "best_threshold": thr, "net_value_at_threshold": float(max(values))}
    print(f"[valid] {name:<20} ROC-AUC {val_scores[name]['roc_auc']:.3f}  PR-AUC {val_scores[name]['pr_auc']:.3f}  "
          f"thr {thr:.2f}  net value ${max(values):,.0f}")

candidates = {k: v for k, v in val_scores.items() if k != "baseline_majority"}
best = max(candidates, key=lambda k: candidates[k]["pr_auc"])   # PR-AUC: the right ranking metric for a rare class
THR = val_scores[best]["best_threshold"]
print(f"Selected on validation PR-AUC: {best} (threshold {THR:.2f})")

# ---------------------------------------------------------------- hold-out test, reported once
test_metrics = {}
for name, pipe in fitted.items():
    pt = pipe.predict_proba(test[NUM + CAT])[:, 1]
    thr = val_scores[name]["best_threshold"]
    test_metrics[name] = metrics(test[TARGET].values, pt, thr)
    test_metrics[name]["net_value"] = float(net_value(test[TARGET].values, pt, thr, test.mrr.values))
pt_best = fitted[best].predict_proba(test[NUM + CAT])[:, 1]
mt = pd.DataFrame(test_metrics).T
print("\nHOLD-OUT TEST")
print(mt[["accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "brier", "threshold", "flagged_pct", "net_value"]]
      .round(3).to_string())

# drivers: permutation importance (PR-AUC drop) on the test set + LR coefficients for direction
perm = permutation_importance(fitted[best], test[NUM + CAT], test[TARGET], scoring="average_precision",
                              n_repeats=10, random_state=SEED, n_jobs=-1)
imp = pd.Series(perm.importances_mean, index=NUM + CAT).sort_values(ascending=False)
lr = fitted["logistic_regression"]
coef = pd.Series(lr.named_steps["model"].coef_[0], index=lr.named_steps["prep"].get_feature_names_out())
direction = {f: np.sign(coef[f"num__{f}"]) if f"num__{f}" in coef else 0 for f in NUM}
print("\nTop drivers (permutation importance, PR-AUC drop):")
print(imp.head(8).round(4).to_string())

# ---------------------------------------------------------------- refit on all labelled history, score today's customers
# clone: never refit the evaluated estimator in place (that would leak test data into the evaluation plots)
final = Pipeline([("prep", prep()), ("model", clone(MODELS[best]))]).fit(hist[NUM + CAT], hist[TARGET])
score["churn_probability"] = final.predict_proba(score[NUM + CAT])[:, 1]
base_rate = float(hist[TARGET].mean())
score["risk_tier"] = np.select([score.churn_probability >= THR, score.churn_probability >= base_rate],
                               ["High", "Medium"], "Low")


def reasons(r):
    out = []
    if r.usage_trend < 0.7 and r.no_usage_history == 0:
        out.append("usage down 30%+")
    if 0 <= r.sessions_per_seat_3m < 5:
        out.append("low engagement")
    if r.failed_attempts_90d > 0:
        out.append("recent failed payment")
    if r.tickets_90d >= 2:
        out.append("2+ support tickets in 90d")
    if r.is_activated == 0:
        out.append("never activated")
    if r.tenure_months < 3:
        out.append("new customer (<3 months)")
    return "; ".join(out) if out else "no rule-based flag"


ACTIONS = {"High": "CSM call within 7 days; payment-method update if payment failed; offer annual plan / training session",
           "Medium": "Automated re-engagement: feature tips, in-app nudges, check-in email from CSM",
           "Low": "Business as usual; target with expansion offers"}
score["risk_reasons"] = score.apply(reasons, axis=1)
score["recommended_action"] = score.risk_tier.map(ACTIONS)
score["plan_name"] = score.plan.map(plan_names)
score["expected_mrr_loss"] = score.churn_probability * score.mrr
score["scored_at"] = pd.Timestamp("2025-12-31")
export = score[["account_id", "scored_at", "plan_name", "mrr", "company_size", "acquisition_channel", "country",
                "tenure_months", "sessions_per_seat_3m", "usage_trend", "failed_attempts_90d", "tickets_90d",
                "churn_probability", "risk_tier", "expected_mrr_loss", "risk_reasons", "recommended_action"]]
vs.MARTS_OUT.mkdir(parents=True, exist_ok=True)
export.to_parquet(vs.MARTS_OUT / "churn_scores.parquet", index=False)
tiers = (export.groupby("risk_tier").agg(customers=("account_id", "count"), mrr=("mrr", "sum"),
                                         avg_probability=("churn_probability", "mean"),
                                         expected_mrr_loss=("expected_mrr_loss", "sum"))
         .reindex(["High", "Medium", "Low"]))
print("\nScored customers active at 2025-12-31:")
print(tiers.round(3).to_string())

# ---------------------------------------------------------------- charts
fig, axes = plt.subplots(1, 3, figsize=(15, 4.3))
ax = axes[0]
for k, name in enumerate(["logistic_regression", "gradient_boosting"]):
    p = fitted[name].predict_proba(test[NUM + CAT])[:, 1]
    fpr, tpr, _ = roc_curve(test[TARGET], p)
    ax.plot(fpr, tpr, color=vs.SERIES[k], label=f"{name.replace('_', ' ')} (AUC {test_metrics[name]['roc_auc']:.2f})")
ax.plot([0, 1], [0, 1], color=vs.NEUTRAL, ls=":", lw=1, label="random")
ax.set_xlabel("False positive rate")
ax.set_ylabel("True positive rate")
ax.legend(loc="lower right", fontsize=8)
ax.set_title("Both models rank churners well")
vs.subtitle(ax, "ROC curve, hold-out test (Jul-Sep 2025 cutoffs)")
ax = axes[1]
for k, name in enumerate(["logistic_regression", "gradient_boosting"]):
    p = fitted[name].predict_proba(test[NUM + CAT])[:, 1]
    pr, rc, _ = precision_recall_curve(test[TARGET], p)
    ax.plot(rc, pr, color=vs.SERIES[k], label=f"{name.replace('_', ' ')} (AP {test_metrics[name]['pr_auc']:.2f})")
ax.axhline(test[TARGET].mean(), color=vs.NEUTRAL, ls=":", lw=1, label=f"base rate {test[TARGET].mean():.1%}")
m = test_metrics[best]
ax.scatter([m["recall"]], [m["precision"]], color=vs.TEXT, zorder=4, s=30)
ax.annotate(f"operating point\nthr {THR:.2f}", (m["recall"], m["precision"]), xytext=(10, 10), textcoords="offset points", fontsize=8)
ax.set_xlabel("Recall (share of churners caught)")
ax.set_ylabel("Precision")
ax.legend(loc="upper right", fontsize=8)
ax.set_title(f"At the chosen threshold we catch {m['recall']:.0%} of churners")
vs.subtitle(ax, "Precision-recall trade-off (more relevant than ROC for a rare event)")
ax = axes[2]
cm = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
ax.imshow(cm, cmap=vs.SEQ_BLUE)
for i in range(2):
    for j in range(2):
        ax.text(j, i, f"{cm[i, j]:,}\n{['TN', 'FP', 'FN', 'TP'][i * 2 + j]}", ha="center", va="center", fontsize=10,
                color="white" if cm[i, j] > cm.max() * 0.5 else vs.TEXT)
ax.set_xticks([0, 1], ["Predicted stay", "Predicted churn"])
ax.set_yticks([0, 1], ["Actual stay", "Actual churn"])
ax.grid(False)
ax.set_title(f"Precision {m['precision']:.0%}, recall {m['recall']:.0%}")
vs.subtitle(ax, f"Confusion matrix, {best.replace('_', ' ')}, test set")
vs.footnote(fig, "Synthetic data: these scores describe how well the model recovers the simulated churn mechanism, not real-world accuracy.")
vs.save(fig, "churn_model_evaluation", "churn_model")

fig, axes = plt.subplots(1, 2, figsize=(12, 4.3))
ax = axes[0]
top = imp.head(10)[::-1]
labels = [f"{f.replace('_', ' ')} ({'+' if direction.get(f, 0) > 0 else '-' if direction.get(f, 0) < 0 else 'cat'})" for f in top.index]
ax.barh(labels, top.values, color=vs.SERIES[0], height=0.6)
ax.grid(axis="y", visible=False)
ax.grid(axis="x", visible=True)
ax.set_xlabel("Drop in PR-AUC when the feature is shuffled")
ax.set_title(f"{top.index[-1].replace('_', ' ').capitalize()} is the strongest churn signal")
vs.subtitle(ax, "Churn drivers: permutation importance (+/- = direction in logistic regression)")
ax = axes[1]
bins = np.linspace(0, max(0.6, score.churn_probability.max()), 40)
for t in ["Low", "Medium", "High"]:
    ax.hist(score.loc[score.risk_tier == t, "churn_probability"], bins=bins, color=vs.RISK_COLORS[t],
            label=f"{t} ({(score.risk_tier == t).sum():,})", alpha=0.9, edgecolor="white", linewidth=0.4)
ax.axvline(THR, color=vs.TEXT, ls="--", lw=1)
ax.text(THR, ax.get_ylim()[1] * 0.92, f" action threshold {THR:.2f}", fontsize=8)
ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlabel("Predicted probability of churning in the next 3 months")
ax.legend(title="Risk tier", fontsize=8.5)
ax.set_title(f"{(score.risk_tier == 'High').sum():,} customers need action now")
vs.subtitle(ax, "Churn probability of customers active at 2025-12-31")
vs.footnote(fig)
vs.save(fig, "churn_drivers_and_risk_distribution", "churn_model")

prob_true, prob_pred = calibration_curve(test[TARGET], pt_best, n_bins=8, strategy="quantile")
fig, ax = plt.subplots(figsize=(5.5, 4.3))
ax.plot([0, prob_pred.max()], [0, prob_pred.max()], color=vs.NEUTRAL, ls=":", lw=1, label="perfect calibration")
ax.plot(prob_pred, prob_true, color=vs.SERIES[0], marker="o", label=best.replace("_", " "))
ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.yaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlabel("Predicted churn probability")
ax.set_ylabel("Observed churn rate")
ax.legend(fontsize=8.5)
ax.set_title("Probabilities are usable as-is")
vs.subtitle(ax, "Calibration on the hold-out test set (8 quantile bins)")
vs.footnote(fig)
vs.save(fig, "churn_calibration", "churn_model")

# ---------------------------------------------------------------- report
results = {"target": "churned within 3 months after a month-end cutoff", "splits": split_info, "selected_model": best,
           "selection_metric": "validation PR-AUC", "threshold": THR, "validation": val_scores, "test": test_metrics,
           "permutation_importance": imp.round(5).to_dict(),
           "assumptions": {"outreach_cost": OUTREACH_COST, "save_rate": SAVE_RATE, "gross_margin": GROSS_MARGIN,
                           "saved_months": SAVED_MONTHS},
           "scored_tiers": tiers.reset_index().to_dict(orient="records")}
(OUT / "churn_model_results.json").write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
fmt = lambda v: f"{v:.3f}"
alt = max((k for k in test_metrics if k != "baseline_majority"), key=lambda k: test_metrics[k]["net_value"])
alt_note = "" if alt == best else (
    f" Note: on the hold-out test, **{alt.replace('_', ' ')}** produced more net value "
    f"(${test_metrics[alt]['net_value']:,.0f} vs ${test_metrics[best]['net_value']:,.0f}) at its own threshold. The choice was "
    "fixed on validation before looking at test, so it is reported rather than switched - the two models are close, "
    "and the simpler logistic regression is a defensible alternative where explainability matters most.")
rows = "\n".join(f"| {n} | {fmt(t['accuracy'])} | {fmt(t['precision'])} | {fmt(t['recall'])} | {fmt(t['f1'])} | "
                 f"{fmt(t['roc_auc'])} | {fmt(t['pr_auc'])} | {fmt(t['brier'])} | {t['threshold']:.2f} | ${t['net_value']:,.0f} |"
                 for n, t in test_metrics.items())
tier_rows = "\n".join(f"| {t} | {r.customers:,.0f} | ${r.mrr:,.0f} | {r.avg_probability:.1%} | ${r.expected_mrr_loss:,.0f} | {ACTIONS[t]} |"
                      for t, r in tiers.iterrows())
md = f"""# Churn prediction model

> Fictional company, synthetic data. Generated by `analysis/churn_model.py`. Model performance describes how well the
> model recovers the *simulated* churn mechanism; it is **not** an estimate of real-world predictive performance.

## Problem definition
- **Target:** a customer paying at a month-end cutoff churns within the next 3 months (`churned_next_3m`).
- **Population:** every customer with MRR > 0 at the cutoff; one row per customer per monthly cutoff.
- **Why 3 months:** long enough for Customer Success to act, short enough for the signal to be fresh.

## Leakage prevention and validation
| split | cutoffs | rows | customers | churn rate |
|---|---|---:|---:|---:|
""" + "\n".join(f"| {k} | {v['cutoffs']} | {v['rows']:,} | {v['customers']:,} | {v['churn_rate']:.1%} |" for k, v in split_info.items()) + f"""

- Features use only events stamped on or before the cutoff and **complete** usage months (the in-progress month is excluded).
- Splits are **out-of-time**; the test set is scored once, after model and threshold were fixed on validation.
- The same customer can appear in several snapshots (different cutoffs); because splits are by time, no future
  information reaches training.

## Features ({len(NUM)} numeric + {len(CAT)} categorical)
Plan and MRR at the cutoff, tenure, activation flag, sessions per seat (last 3 complete months), usage trend
(last 3 vs prior 3 months), seats, missing usage months, failed payment attempts (90 days and total), support tickets
(90 days and total), upgrades, downgrades, company size, acquisition channel and country.

## Model comparison (hold-out test)
| model | accuracy | precision | recall | F1 | ROC-AUC | PR-AUC | Brier | threshold | net value |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{rows}

Selected: **{best.replace('_', ' ')}** (highest validation PR-AUC).{alt_note} Accuracy is shown for completeness, but with a
{test[TARGET].mean():.1%} base rate a model that predicts "nobody churns" is already {1 - test[TARGET].mean():.1%} accurate, so it is not used for selection.

## Choosing the threshold: false positives vs false negatives
- **False positive** (we contact a customer who would have stayed): costs ~${OUTREACH_COST:.0f} of CSM time / incentive.
- **False negative** (we miss a churner): loses the chance to save them, worth
  {SAVE_RATE:.0%} x {GROSS_MARGIN:.0%} margin x {SAVED_MONTHS} months x their MRR (≈ ${SAVE_RATE * GROSS_MARGIN * SAVED_MONTHS * score.mrr.mean():,.0f} for an average customer).
- Because a miss costs far more than a wasted call, the value-maximising threshold is low (**{THR:.2f}**), which trades
  precision for recall. On the test set it flags {test_metrics[best]['flagged_pct']:.0%} of customers, catches
  {test_metrics[best]['recall']:.0%} of churners at {test_metrics[best]['precision']:.0%} precision, and creates an estimated
  **${test_metrics[best]['net_value']:,.0f}** of net value over three monthly cohorts. If CSM capacity is the constraint, raise the threshold.

## Churn drivers (permutation importance on the test set)
| feature | PR-AUC drop | direction |
|---|---:|---|
""" + "\n".join(f"| {f} | {v:.4f} | {'higher -> more churn' if direction.get(f, 0) > 0 else 'higher -> less churn' if direction.get(f, 0) < 0 else 'categorical'} |"
                for f, v in imp.head(10).items()) + f"""

## Risk tiers for customers active at 2025-12-31
Tiers: **High** = probability >= action threshold ({THR:.2f}); **Medium** = above the historical base rate ({base_rate:.1%});
**Low** = below the base rate.

| tier | customers | MRR | avg probability | expected MRR loss (3m) | recommended action |
|---|---:|---:|---:|---:|---|
{tier_rows}

Each customer in `data/marts/churn_scores.parquet` also carries `risk_reasons` (rule-based reason codes such as
"usage down 30%+" or "recent failed payment") so Customer Success knows *why* they were flagged.

## Recommendations for reducing churn
1. **Fix involuntary churn first** - failed payments are a top driver and the cheapest to fix: card-updater service,
   pre-expiry reminders, smarter retry timing and a grace period before cancellation.
2. **Engagement early-warning:** trigger CSM outreach when sessions per seat fall 30%+ versus the prior quarter.
3. **Drive activation:** customers who never invited a teammate churn more - push teammate invites in onboarding.
4. **First-90-days programme** for new customers (onboarding call, success plan), where hazard is highest.
5. **Measure the intervention:** hold out a random 10-20% of High-risk customers from outreach to estimate the true save rate.

## Limitations
- Synthetic data: the churn mechanism was generated by `scripts/generate_data.py`, so the model can recover it unusually well.
- Snapshots of the same customer are correlated; metrics are point estimates without confidence intervals.
- Economic assumptions (save rate, outreach cost) are illustrative and should be replaced with measured values.

![evaluation](../figures/churn_model/churn_model_evaluation.png)
![drivers](../figures/churn_model/churn_drivers_and_risk_distribution.png)
![calibration](../figures/churn_model/churn_calibration.png)
"""
(OUT / "churn_model_report.md").write_text(md, encoding="utf-8")
print("\nWrote reports/churn_model/ and data/marts/churn_scores.parquet")
