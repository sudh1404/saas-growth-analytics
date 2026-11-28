"""
Exploratory data analysis for CloudDesk (fictional, synthetic data).

Every chart answers one business question (its title states the answer, the grey subtitle the question).
Outputs:
  reports/figures/eda/*.png      charts
  reports/tables/eda_*.csv       supporting tables
  reports/eda_summary.md         findings with the numbers computed in this run
"""
import duckdb
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter
from scipy import stats

import viz_style as vs
from viz_style import plt

vs.apply()
RAW = vs.ROOT / "data" / "raw"
vs.TABLES.mkdir(parents=True, exist_ok=True)
F = []          # findings for the markdown summary: (section, text)


def q(sql):
    return con.sql(sql).df()


con = duckdb.connect(str(vs.DB), read_only=True)
acc = q("select * from marts.dim_accounts order by account_id")
mrr = q("select * from marts.fct_mrr order by account_id, month")
kpi = q("select * from marts.agg_kpis_monthly order by month")
usage = q("select * from marts.fct_usage_monthly order by account_id, usage_month")
cohort = q("select * from marts.agg_cohort_retention order by all")
chan = q("select * from marts.agg_channel_performance order by channel")
seg = q("select * from marts.agg_customer_segments order by account_id")
plans = q("select * from marts.dim_plans order by plan_id")
mkt = q("select * from marts.fct_marketing_daily order by date, channel")

# =====================================================================================
# 1. Data quality: missing values, duplicates, outliers (on the RAW files, before cleaning)
# =====================================================================================
rows = []
for f in sorted(RAW.glob("*.csv")):
    df = pd.read_csv(f)
    for c in df.columns:
        rows.append({"table": f.stem, "column": c, "rows": len(df),
                     "missing": int(df[c].isna().sum()), "missing_pct": df[c].isna().mean()})
    rows.append({"table": f.stem, "column": "<exact duplicate rows>", "rows": len(df),
                 "missing": int(df.duplicated().sum()), "missing_pct": df.duplicated().mean()})
dq = pd.DataFrame(rows)
dq.to_csv(vs.TABLES / "eda_missing_and_duplicates.csv", index=False)

# structural NULLs (by design) vs genuine quality gaps
by_design = {("subscriptions", "end_date"), ("subscriptions", "end_reason"), ("subscriptions", "churn_reason"),
             ("payments", "failure_reason"), ("accounts", "pricing_page_variant"), ("plans", "max_seats")}
gaps = dq[(dq.missing > 0) & ~dq.apply(lambda r: (r.table, r.column) in by_design, axis=1)].copy()
gaps["label"] = gaps.table + "." + gaps.column
gaps = gaps.sort_values("missing")
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.barh(gaps.label, gaps.missing, color=vs.SERIES[0], height=0.6)
for y, (v, p) in enumerate(zip(gaps.missing, gaps.missing_pct)):
    ax.text(v, y, f"  {v:,} ({p:.1%})", va="center", fontsize=9, color=vs.TEXT)
ax.grid(axis="y", visible=False)
ax.grid(axis="x", visible=True)
ax.set_xlabel("Rows affected")
ax.set_title("Data gaps are small (<1.1% of any column) and all are fixed in staging")
vs.subtitle(ax, "Where is raw data missing or duplicated? (structural NULLs such as end_date of active subscriptions excluded)")
ax.set_xlim(0, gaps.missing.max() * 1.35)
vs.footnote(fig)
vs.save(fig, "01_data_quality_gaps", "eda")
F.append(("Data quality", f"{len(gaps)} raw columns have genuine gaps or duplicates; the worst is "
          f"`{gaps.iloc[-1].label}` with {gaps.iloc[-1].missing:,} rows ({gaps.iloc[-1].missing_pct:.1%}). "
          "Structural NULLs (e.g. `end_date` of active subscriptions) are expected and excluded."))

# outliers: sessions per seat (IQR rule) by plan
u = usage.merge(mrr[["account_id", "month", "plan_id"]], left_on=["account_id", "usage_month"],
                right_on=["account_id", "month"], how="left").merge(plans[["plan_id", "plan_name"]], on="plan_id")
u = u.dropna(subset=["sessions_per_seat"])
# usage is right-skewed, so the IQR rule is applied on log(1 + sessions per seat)
lg = np.log1p(u.sessions_per_seat)
q1, q3 = lg.quantile([0.25, 0.75])
iqr = q3 - q1
lo, hi = np.expm1(q1 - 1.5 * iqr), np.expm1(q3 + 1.5 * iqr)
u["is_outlier"] = ~u.sessions_per_seat.between(lo, hi)
z = np.abs(stats.zscore(u.sessions_per_seat))
fig, ax = plt.subplots(figsize=(8, 3.8))
order = ["Starter", "Pro", "Business"]
data = [u.loc[u.plan_name == p, "sessions_per_seat"] for p in order]
bp = ax.boxplot(data, orientation="horizontal", tick_labels=order, widths=0.5, patch_artist=True,
                flierprops=dict(marker="o", markersize=3, markerfacecolor=vs.NEUTRAL, markeredgewidth=0, alpha=0.5),
                medianprops=dict(color=vs.TEXT, linewidth=1.5))
for patch, p in zip(bp["boxes"], order):
    patch.set_facecolor(vs.PLAN_COLORS[p])
    patch.set_alpha(0.85)
ax.axvline(lo, color=vs.TEXT_2, ls=":", lw=1)
ax.text(lo, 3.45, " IQR lower fence", fontsize=8, color=vs.TEXT_2)
ax.grid(axis="y", visible=False)
ax.grid(axis="x", visible=True)
ax.set_xlabel("Sessions per active seat in the month")
low_out = int((u.sessions_per_seat < lo).sum())
ax.set_title(f"{u.is_outlier.mean():.1%} of account-months are usage outliers; "
             f"{low_out / max(u.is_outlier.sum(), 1):.0%} of them are near-zero usage")
vs.subtitle(ax, "Are there abnormal usage values? (IQR rule on log scale) Outliers are kept: low usage is a churn signal")
vs.footnote(fig)
vs.save(fig, "02_outliers_sessions_per_seat", "eda")
low_churn = u[u.sessions_per_seat < lo].merge(acc[["account_id", "lifecycle_status"]], on="account_id").lifecycle_status.eq("churned").mean()
F.append(("Outliers", f"IQR fences for sessions/seat are {lo:.1f}-{hi:.1f}; {u.is_outlier.sum():,} account-months "
          f"({u.is_outlier.mean():.1%}) fall outside, {low_out:,} of them on the low side; |z|>3 flags {int((z > 3).sum()):,}. "
          f"{low_churn:.0%} of accounts behind low-usage outlier months later churned, so outliers are kept as signal rather than removed."))

# =====================================================================================
# 2. Univariate
# =====================================================================================
payers = acc[acc.is_paying_customer].copy()
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
ax = axes[0]
sz = acc[acc.company_size != "Unknown"].company_size.value_counts().reindex(["1-10", "11-50", "51-200", "201+"])
ax.bar(sz.index, sz.values, color=vs.SERIES[0], width=0.6)
for i, v in enumerate(sz.values):
    ax.text(i, v, f"{v / sz.sum():.0%}", ha="center", va="bottom", fontsize=9)
ax.set_title(f"{(acc.company_size == '1-10').mean():.0%} of signups are micro-businesses (1-10)")
vs.subtitle(ax, "Who signs up? Accounts by company size (employees)")
ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x / 1000:.0f}K"))
ax = axes[1]
bins = np.arange(0, payers.tenure_months.max() + 2) - 0.5
for status, color, lab in [("active", vs.SERIES[0], "Active"), ("churned", vs.SERIES[1], "Churned")]:
    ax.hist(payers.loc[payers.lifecycle_status == status, "tenure_months"], bins=bins, color=color,
            alpha=0.85, label=lab, histtype="stepfilled", edgecolor="white", linewidth=0.5)
ax.legend()
ax.set_xlabel("Tenure (months since first payment)")
ax.set_title("Churn clusters in the first months of tenure")
vs.subtitle(ax, "How long do paying customers stay?")
vs.footnote(fig)
vs.save(fig, "03_univariate_size_and_tenure", "eda")
churned = payers[payers.lifecycle_status == "churned"]
F.append(("Univariate", f"{(acc.company_size == '1-10').mean():.0%} of signups are 1-10-employee companies. "
          f"Median tenure of churned customers is {churned.tenure_months.median():.0f} months; "
          f"{(churned.tenure_months <= 2).mean():.0%} of churners leave within their first 2 months."))

# =====================================================================================
# 3. Acquisition trends
# =====================================================================================
sm = acc.assign(m=acc.signup_date.dt.to_period("M").dt.to_timestamp()).groupby(["m", "acquisition_channel"]).size().unstack()
fig, ax = plt.subplots(figsize=(10, 4.2))
for c in sm.columns:
    ax.plot(sm.index, sm[c], color=vs.CHANNEL_COLORS[c], label=vs.LABEL[c])
ax.set_xlim(sm.index[0], sm.index[-1] + pd.Timedelta(days=70))
vs.end_labels(ax, sm.index[-1] + pd.Timedelta(days=8), {vs.LABEL[c]: sm[c].iloc[-1] for c in sm.columns})
ax.legend(ncol=3, loc="upper left", fontsize=8.5)
ax.set_ylabel("Signups per month")
growth = sm.sum(axis=1)
yoy = growth["2025"].sum() / growth["2024"].sum() - 1
ax.set_title(f"Signups grew {yoy:+.0%} year over year; organic and paid search drive volume")
vs.subtitle(ax, "Where do new accounts come from, and how is acquisition trending? (Dec dip = seasonality)")
vs.footnote(fig)
vs.save(fig, "04_signups_by_channel_trend", "eda")
F.append(("Acquisition", f"Signups: {growth['2024'].sum():,.0f} in 2024 vs {growth['2025'].sum():,.0f} in 2025 ({yoy:+.1%}). "
          f"Organic is the largest source ({(acc.acquisition_channel == 'organic').mean():.0%} of signups), "
          f"then paid search ({(acc.acquisition_channel == 'paid_search').mean():.0%})."))

# =====================================================================================
# 4. Revenue trends: MRR and the bridge
# =====================================================================================
fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [1, 1.1]})
ax = axes[0]
ax.plot(kpi.month, kpi.mrr, color=vs.NAVY, lw=2.4)
ax.fill_between(kpi.month, kpi.mrr, color=vs.SERIES[0], alpha=0.08)
ax.yaxis.set_major_formatter(FuncFormatter(vs.money))
last = kpi.iloc[-1]
ax.annotate(f"{vs.money(last.mrr)} MRR\n{vs.money(last.arr)} ARR", (last.month, last.mrr), xytext=(-90, -5),
            textcoords="offset points", fontsize=9, color=vs.TEXT, ha="right",
            arrowprops=dict(arrowstyle="-", color=vs.TEXT_2))
ax.set_title(f"MRR reached {vs.money(last.mrr)} but monthly growth slowed to {last.mrr_growth_rate:.1%}")
vs.subtitle(ax, "How fast is recurring revenue growing?")
ax = axes[1]
w = 20
parts = [("new_mrr", "New", vs.SERIES[0]), ("expansion_mrr", "Expansion", vs.SERIES[2]),
         ("contraction_mrr", "Contraction", vs.SERIES[3]), ("churned_mrr", "Churned", vs.SERIES[1])]
pos = np.zeros(len(kpi))
neg = np.zeros(len(kpi))
for col, lab, colr in parts:
    v = kpi[col].values
    base = np.where(v >= 0, pos, neg)
    ax.bar(kpi.month, v, bottom=base, width=w, color=colr, label=lab, edgecolor="white", linewidth=0.6)
    pos = pos + np.where(v >= 0, v, 0)
    neg = neg + np.where(v < 0, v, 0)
ax.plot(kpi.month, kpi.net_new_mrr, color=vs.TEXT, marker="o", markersize=4, lw=1.4, label="Net new MRR")
ax.axhline(0, color=vs.TEXT_2, lw=0.8)
ax.yaxis.set_major_formatter(FuncFormatter(vs.money))
ax.legend(ncol=5, loc="upper left", fontsize=8.5)
lost_share = -(kpi.churned_mrr + kpi.contraction_mrr).tail(6).sum() / kpi.new_mrr.tail(6).sum()
ax.set_title(f"Churn and contraction now erase {lost_share:.0%} of new MRR")
vs.subtitle(ax, "Why did MRR move each month? (MRR bridge; reconciles to closing MRR every month)")
vs.footnote(fig)
vs.save(fig, "05_mrr_trend_and_bridge", "eda")
F.append(("Revenue", f"MRR {vs.money(kpi.mrr.iloc[11])} (Dec-2024) -> {vs.money(last.mrr)} (Dec-2025); ARR {vs.money(last.arr)}. "
          f"Month-over-month growth fell from {kpi.mrr_growth_rate.iloc[12]:.1%} (Jan-2025) to {last.mrr_growth_rate:.1%} (Dec-2025). "
          f"Over the last 6 months churned + contraction MRR equalled {lost_share:.0%} of new MRR."))

# =====================================================================================
# 5. Retention: cohort heatmap + curves by channel
# =====================================================================================
mat = (cohort.groupby(["cohort_month", "months_since_start"])[["retained_customers", "cohort_customers"]].sum()
       .assign(r=lambda d: d.retained_customers / d.cohort_customers).r.unstack())
mat.to_csv(vs.TABLES / "eda_cohort_retention_matrix.csv")
fig, ax = plt.subplots(figsize=(10, 7))
im = ax.imshow(mat.values, cmap=vs.SEQ_BLUE, vmin=0.5, vmax=1, aspect="auto")
for i in range(mat.shape[0]):
    for j in range(mat.shape[1]):
        v = mat.values[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=7, color="white" if v > 0.8 else vs.TEXT)
ax.set_xticks(range(mat.shape[1]), [f"M{k}" for k in mat.columns])
ax.set_yticks(range(mat.shape[0]), [d.strftime("%b %Y") for d in mat.index])
ax.grid(False)
cb = fig.colorbar(im, ax=ax, fraction=0.03, format=PercentFormatter(1.0))
cb.outline.set_visible(False)
m12 = cohort[cohort.months_since_start == 12]
m12r = m12.retained_customers.sum() / m12.cohort_customers.sum()
ax.set_title(f"About {m12r:.0%} of customers are still paying after 12 months")
vs.subtitle(ax, "Which cohorts retain best? Logo retention by month of first payment (blank = cohort too young)")
vs.footnote(fig)
vs.save(fig, "06_cohort_retention_heatmap", "eda")

curve = (cohort.groupby(["acquisition_channel", "months_since_start"])[["retained_customers", "cohort_customers"]].sum()
         .assign(r=lambda d: d.retained_customers / d.cohort_customers).r.unstack(0))
fig, ax = plt.subplots(figsize=(9, 4.4))
for c in curve.columns:
    ax.plot(curve.index, curve[c], color=vs.CHANNEL_COLORS[c], marker="o", markersize=3.5, label=vs.LABEL[c])
vs.end_labels(ax, 12.25, {vs.LABEL[c]: curve[c].iloc[-1] for c in curve.columns}, fmt=lambda k, v: f"{k} {v:.0%}")
ax.set_xlim(0, 14.2)
ax.yaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlabel("Months since first payment")
ax.legend(ncol=6, loc="lower left", fontsize=8)
best, worst = curve.iloc[-1].idxmax(), curve.iloc[-1].idxmin()
ax.set_title(f"{vs.LABEL[best]} customers retain best, {vs.LABEL[worst]} worst "
             f"({curve[best].iloc[-1]:.0%} vs {curve[worst].iloc[-1]:.0%} at M12)")
vs.subtitle(ax, "Does acquisition channel change retention? Logo retention curve, all cohorts weighted")
vs.footnote(fig)
vs.save(fig, "07_retention_curve_by_channel", "eda")
F.append(("Retention", f"Weighted Month-12 logo retention is {m12r:.1%}. Best channel: {vs.LABEL[best]} "
          f"({curve[best].iloc[-1]:.1%}); worst: {vs.LABEL[worst]} ({curve[worst].iloc[-1]:.1%})."))

# =====================================================================================
# 6. Channel performance: CAC vs LTV
# =====================================================================================
paid = chan[chan.cac.notna()].sort_values("ltv_to_cac")
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
ax = axes[0]
ax.barh([vs.LABEL[c] for c in paid.channel], paid.ltv_to_cac, color=[vs.CHANNEL_COLORS[c] for c in paid.channel], height=0.55)
for y, v in enumerate(paid.ltv_to_cac):
    ax.text(v, y, f"  {v:.1f}x", va="center", fontsize=9)
ax.axvline(3, color=vs.TEXT_2, ls="--", lw=1)
ax.text(3, -0.62, " 3x benchmark", fontsize=8, color=vs.TEXT_2, va="bottom")
ax.grid(axis="y", visible=False)
ax.grid(axis="x", visible=True)
ax.set_xlim(0, paid.ltv_to_cac.max() * 1.25)
ax.set_title(f"{vs.LABEL[paid.iloc[-1].channel]} returns the most per dollar")
vs.subtitle(ax, "Which paid channels are most efficient? LTV / CAC")
ax = axes[1]
x = np.arange(len(paid))
ax.bar(x - 0.2, paid.cac, width=0.38, color=vs.SERIES[1], label="CAC")
ax.bar(x + 0.2, paid.ltv, width=0.38, color=vs.SERIES[0], label="LTV")
ax.set_xticks(x, [vs.LABEL[c] for c in paid.channel])
ax.yaxis.set_major_formatter(FuncFormatter(vs.money))
ax.legend()
ax.set_title(f"{vs.LABEL[paid.loc[paid.cac.idxmax(), 'channel']]} has the highest CAC (${paid.cac.max():,.0f})")
vs.subtitle(ax, "CAC vs LTV by paid channel (LTV = ARPA x 80% margin / monthly churn)")
vs.footnote(fig)
vs.save(fig, "08_channel_unit_economics", "eda")
paid.to_csv(vs.TABLES / "eda_channel_unit_economics.csv", index=False)
F.append(("Channels", "LTV/CAC: " + ", ".join(f"{vs.LABEL[r.channel]} {r.ltv_to_cac:.1f}x (CAC ${r.cac:,.0f})"
                                             for r in paid.sort_values("ltv_to_cac", ascending=False).itertuples()) + "."))

# =====================================================================================
# 7. Bivariate: activation vs conversion and churn (with significance tests)
# =====================================================================================
mature = acc[acc.signup_date <= "2025-12-17"]
conv = mature.groupby("is_activated").is_paying_customer.mean()
p_ = acc[acc.is_paying_customer & (acc.first_paid_date <= "2025-06-30")]
churn_by_act = p_.groupby("is_activated").apply(lambda d: (d.lifecycle_status == "churned").mean(), include_groups=False)
ct = pd.crosstab(p_.is_activated, p_.lifecycle_status == "churned")
chi2, p_chi, _, _ = stats.chi2_contingency(ct)
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
for ax, s, ttl, sub in [(axes[0], conv, f"Activated trials convert {conv[True] / conv[False]:.1f}x more often",
                         "Does activation (inviting a teammate) predict trial-to-paid conversion?"),
                        (axes[1], churn_by_act, f"Activated customers churn less ({churn_by_act[True]:.0%} vs {churn_by_act[False]:.0%})",
                         f"Share churned by Dec-2025, customers paying since <= Jun-2025 (chi-square p = {p_chi:.1e})")]:
    ax.bar(["Not activated", "Activated"], [s[False], s[True]], color=[vs.NEUTRAL, vs.SERIES[0]], width=0.5)
    for i, v in enumerate([s[False], s[True]]):
        ax.text(i, v, f"{v:.1%}", ha="center", va="bottom", fontsize=10)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title(ttl)
    vs.subtitle(ax, sub)
vs.footnote(fig)
vs.save(fig, "09_activation_vs_conversion_and_churn", "eda")
F.append(("Bivariate", f"Signup-to-paid is {conv[True]:.1%} for activated trials vs {conv[False]:.1%} for non-activated. "
          f"Among customers paying since mid-2025 or earlier, {churn_by_act[True]:.1%} of activated vs "
          f"{churn_by_act[False]:.1%} of non-activated have churned (chi-square p = {p_chi:.1e})."))

# engagement vs churn: churn in next 3 months by engagement decile, as of 2025-06-30
base = mrr[(mrr.month == "2025-06-01") & mrr.is_active][["account_id"]]
eng = usage[(usage.usage_month >= "2025-03-01") & (usage.usage_month <= "2025-05-01")].groupby("account_id").sessions_per_seat.mean()
h = base.join(eng, on="account_id").merge(acc[["account_id", "churned_date"]], on="account_id")
h["churn_3m"] = h.churned_date.notna() & (h.churned_date <= "2025-09-30")
h = h.dropna(subset=["sessions_per_seat"])
h["decile"] = pd.qcut(h.sessions_per_seat.rank(method="first"), 10, labels=range(1, 11))
dec = h.groupby("decile", observed=True).churn_3m.mean()
mw = stats.mannwhitneyu(h.loc[h.churn_3m, "sessions_per_seat"], h.loc[~h.churn_3m, "sessions_per_seat"])
fig, ax = plt.subplots(figsize=(9, 3.8))
ax.bar(dec.index.astype(int), dec.values, color=[vs.SERIES[1] if i <= 2 else vs.SERIES[0] for i in dec.index.astype(int)], width=0.65)
for i, v in zip(dec.index.astype(int), dec.values):
    ax.text(i, v, f"{v:.0%}", ha="center", va="bottom", fontsize=8.5)
ax.set_xticks(range(1, 11), [f"D{i}" for i in range(1, 11)])
ax.set_xlabel("Engagement decile (sessions per seat, Mar-May 2025; D1 = lowest)")
ax.yaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_title(f"The least-engaged 20% churn {dec.iloc[:2].mean() / dec.iloc[2:].mean():.1f}x as often as everyone else")
vs.subtitle(ax, f"Does engagement predict churn? Churn in Jul-Sep 2025 (Mann-Whitney p = {mw.pvalue:.1e})")
vs.footnote(fig)
vs.save(fig, "10_engagement_vs_churn", "eda")
F.append(("Bivariate", f"3-month churn is {dec.iloc[0]:.1%} in the lowest engagement decile vs {dec.iloc[-1]:.1%} in the highest "
          f"(Mann-Whitney U p = {mw.pvalue:.1e})."))

# =====================================================================================
# 8. Multivariate: churn by plan x size; correlation matrix
# =====================================================================================
pay = acc[acc.is_paying_customer & (acc.company_size != "Unknown")].merge(
    plans[["plan_id", "plan_name"]], left_on="first_plan_id", right_on="plan_id")
pay["churned"] = pay.lifecycle_status == "churned"
months_obs = mrr[mrr.prev_mrr > 0].merge(pay[["account_id", "plan_name", "company_size"]], on="account_id")
hz = months_obs.groupby(["plan_name", "company_size"]).apply(
    lambda d: (d.movement_type == "churn").mean(), include_groups=False).unstack().loc[["Starter", "Pro", "Business"], ["1-10", "11-50", "51-200", "201+"]]
fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), gridspec_kw={"width_ratios": [1, 1.25]})
ax = axes[0]
im = ax.imshow(hz.values, cmap=vs.SEQ_BLUE, aspect="auto")
for i in range(hz.shape[0]):
    for j in range(hz.shape[1]):
        v = hz.values[i, j]
        ax.text(j, i, f"{v:.1%}", ha="center", va="center", fontsize=9,
                color="white" if v > np.nanpercentile(hz.values, 60) else vs.TEXT)
ax.set_xticks(range(4), hz.columns)
ax.set_yticks(range(3), [f"{p} (first plan)" for p in hz.index])
ax.set_xlabel("Company size")
ax.grid(False)
hi_cell = np.unravel_index(np.nanargmax(hz.values), hz.shape)
ax.set_title(f"{hz.index[hi_cell[0]]} plans at {hz.columns[hi_cell[1]]}-employee firms churn the most")
vs.subtitle(ax, "Monthly logo churn rate by first plan x company size")
feat = acc[acc.is_paying_customer].copy()
feat = feat.merge(usage.groupby("account_id").sessions_per_seat.mean().rename("avg_sessions_per_seat"), on="account_id", how="left")
feat = feat.merge(usage.groupby("account_id").active_seats.mean().rename("avg_seats"), on="account_id", how="left")
feat["churned"] = (feat.lifecycle_status == "churned").astype(int)
cols = {"churned": "Churned", "avg_sessions_per_seat": "Sessions/seat", "avg_seats": "Seats", "is_activated": "Activated",
        "failed_payment_attempts": "Failed payments", "support_tickets": "Support tickets", "upgrades": "Upgrades",
        "tenure_months": "Tenure", "revenue_to_date": "Revenue to date"}
corr = feat[list(cols)].astype(float).corr(method="spearman").rename(index=cols, columns=cols)
corr.to_csv(vs.TABLES / "eda_spearman_correlations.csv")
ax = axes[1]
im = ax.imshow(corr.values, cmap=vs.DIVERGING, vmin=-1, vmax=1)
for i in range(len(corr)):
    for j in range(len(corr)):
        ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center", fontsize=7.2,
                color="white" if abs(corr.values[i, j]) > 0.6 else vs.TEXT)
ax.set_xticks(range(len(corr)), corr.columns, rotation=40, ha="right")
ax.set_yticks(range(len(corr)), corr.index)
ax.grid(False)
cb = fig.colorbar(im, ax=ax, fraction=0.04)
cb.outline.set_visible(False)
ax.set_title(f"Churn correlates most with low usage (rho = {corr.loc['Churned', 'Sessions/seat']:+.2f})")
vs.subtitle(ax, "Spearman correlation between account-level features (paying customers)")
vs.footnote(fig, "Source: synthetic CloudDesk data. Tenure and revenue correlate with churn partly by construction (churners stop accruing).", y=-0.12)
vs.save(fig, "11_multivariate_churn_plan_size_and_correlations", "eda")
lo_i, hi_i = np.unravel_index(np.nanargmin(hz.values), hz.shape), np.unravel_index(np.nanargmax(hz.values), hz.shape)
F.append(("Multivariate", f"Monthly churn ranges from {np.nanmin(hz.values):.1%} ({hz.index[lo_i[0]]}, {hz.columns[lo_i[1]]} employees) to "
          f"{np.nanmax(hz.values):.1%} ({hz.index[hi_i[0]]}, {hz.columns[hi_i[1]]} employees). Spearman correlation of churn with sessions/seat is "
          f"{corr.loc['Churned', 'Sessions/seat']:+.2f}, with failed payments {corr.loc['Churned', 'Failed payments']:+.2f}, "
          f"with support tickets {corr.loc['Churned', 'Support tickets']:+.2f}."))

# =====================================================================================
# 9. Segmentation: revenue concentration and churn reasons
# =====================================================================================
s = seg.sort_values("revenue_to_date", ascending=False).reset_index(drop=True)
cum = s.revenue_to_date.cumsum() / s.revenue_to_date.sum()
xs = (np.arange(len(s)) + 1) / len(s)
top20 = cum.iloc[int(len(s) * 0.2) - 1]
reasons = acc[acc.lifecycle_status == "churned"].churn_reason.value_counts(normalize=True).sort_values()
fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.9))
fig.subplots_adjust(wspace=0.5)
ax = axes[0]
ax.plot(xs, cum, color=vs.NAVY)
ax.plot([0, 1], [0, 1], color=vs.NEUTRAL, ls=":", lw=1)
ax.scatter([0.2], [top20], color=vs.SERIES[1], zorder=3, s=40)
ax.annotate(f"Top 20% = {top20:.0%} of revenue", (0.2, top20), xytext=(12, -14), textcoords="offset points", fontsize=9)
ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.yaxis.set_major_formatter(PercentFormatter(1.0))
ax.set_xlabel("Share of active customers (ranked by revenue)")
ax.set_title(f"Top 20% of customers bring {top20:.0%} of revenue")
vs.subtitle(ax, "How concentrated is revenue? Pareto curve of collected revenue")
ax = axes[1]
ax.barh(reasons.index.str.replace("_", " "), reasons.values, color=vs.SERIES[1], height=0.55)
for y, v in enumerate(reasons.values):
    ax.text(v, y, f" {v:.0%}", va="center", fontsize=9)
ax.xaxis.set_major_formatter(PercentFormatter(1.0))
ax.grid(axis="y", visible=False)
ax.grid(axis="x", visible=True)
ax.set_xlim(0, reasons.max() * 1.25)
ax.set_title(f"Payment failure is the #{list(reasons.index[::-1]).index('payment_failure') + 1} churn reason")
vs.subtitle(ax, "Why do customers leave? Share of churned customers by reason")
vs.footnote(fig)
vs.save(fig, "12_segmentation_pareto_and_churn_reasons", "eda")
F.append(("Segmentation", f"The top 20% of active customers generate {top20:.0%} of collected revenue. Churn reasons: "
          + ", ".join(f"{k.replace('_', ' ')} {v:.0%}" for k, v in reasons.sort_values(ascending=False).items()) + "."))

# =====================================================================================
# summary
# =====================================================================================
desc = acc[["tenure_months", "revenue_to_date", "failed_payment_attempts", "support_tickets"]].describe().T
desc.to_csv(vs.TABLES / "eda_descriptive_stats_accounts.csv")
md = ["# Exploratory data analysis - findings", "",
      "> CloudDesk is a **fictional** company and all data is **synthetic**. Numbers below are computed by "
      "`analysis/eda.py` on the current pipeline run; they are not real-world benchmarks.", ""]
for sec in dict.fromkeys(s_ for s_, _ in F):
    md.append(f"## {sec}")
    md += [f"- {t}" for s_, t in F if s_ == sec]
    md.append("")
md += ["## Charts", ""] + [f"![{p.stem}](figures/eda/{p.name})" for p in sorted((vs.FIG / "eda").glob("*.png"))]
(vs.ROOT / "reports" / "eda_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print("\n".join(f"[{s_}] {t}" for s_, t in F))
print(f"\nSaved {len(list((vs.FIG / 'eda').glob('*.png')))} charts to reports/figures/eda/")
