"""
Leadership report: answers the ten business questions with numbers computed on the current pipeline run.

Inputs : warehouse marts + reports/{ab_test,churn_model,forecast}/*.json produced earlier in the pipeline.
Output : reports/business_insights_report.md
Nothing in the report is typed by hand: every figure is a variable computed below.
"""
import json

import duckdb
import pandas as pd

import viz_style as vs

R = vs.ROOT / "reports"
con = duckdb.connect(str(vs.DB), read_only=True)
q = lambda s: con.sql(s).df()
L = vs.LABEL
money, pct = (lambda v: f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}"), (lambda v, d=1: f"{v:.{d}%}")

ab = json.loads((R / "ab_test" / "ab_test_results.json").read_text(encoding="utf-8"))
cm = json.loads((R / "churn_model" / "churn_model_results.json").read_text(encoding="utf-8"))
fc = json.loads((R / "forecast" / "forecast_results.json").read_text(encoding="utf-8"))

kpi = q("select * from marts.agg_kpis_monthly order by month")
last, dec24 = kpi.iloc[-1], kpi[kpi.month == pd.Timestamp("2024-12-01")].iloc[0]
perf = q("select * from marts.agg_channel_performance order by channel")
mature = "signup_date <= date '2025-12-17'"

# ---------------------------------------------------------------- Q1 / Q2 channels: volume and conversion
ch = q(f"""
    select acquisition_channel as channel, count(*) as signups,
           count(*) filter (where is_paying_customer) as customers,
           avg(is_paying_customer::int) as signup_to_paid, avg(is_activated::int) as activation
    from marts.dim_accounts where {mature} group by 1 order by customers desc""").merge(
    perf[["channel", "visitors", "visit_to_signup_rate"]], on="channel")
ch["visit_to_paid"] = ch.customers / ch.visitors
top_vol = ch.iloc[0]
best_conv = ch.sort_values("signup_to_paid", ascending=False).iloc[0]
worst_conv = ch.sort_values("signup_to_paid").iloc[0]
onb = q(f"select acquisition_channel channel, avg(is_onboarded::int) r from marts.dim_accounts where {mature} group by 1 order by r")
worst_onb = onb.iloc[0]
onb_note = (f"{L[worst_conv.channel]} also has the lowest onboarding rate ({pct(worst_onb.r, 0)} vs "
            f"{pct(onb.r.median(), 0)} median), so its traffic is lower-intent - paying for clicks that never activate."
            if worst_onb.channel == worst_conv.channel else
            f"{L[worst_conv.channel]} loses more prospects after signup than other channels; its lowest onboarding rate belongs to "
            f"{L[worst_onb.channel]} ({pct(worst_onb.r, 0)}).")
best_v2p = ch.sort_values("visit_to_paid", ascending=False).iloc[0]

# ---------------------------------------------------------------- Q3 funnel
f = q(f"""
    select count(*) s, count(*) filter (where is_onboarded) o, count(*) filter (where has_created_project) p,
           count(*) filter (where is_activated) a, count(*) filter (where is_paying_customer) c,
           count(*) filter (where is_activated and is_paying_customer) ac,
           count(*) filter (where not is_activated and is_paying_customer) nac
    from marts.dim_accounts where {mature}""").iloc[0]
visitors = q(f"select sum(visitors) v from marts.fct_marketing_daily where date <= date '2025-12-17'").v[0]
steps = {"Signup -> Onboarded": 1 - f.o / f.s, "Onboarded -> Project": 1 - f.p / f.o,
         "Project -> Activated": 1 - f.a / f.p}
worst_step = max(steps, key=steps.get)
act_conv, nonact_conv = f.ac / f.a, f.nac / (f.s - f.a)
extra_customers = 0.05 * f.p * (act_conv - (f.c - f.ac) / (f.s - f.a))   # +5pp project->activation
arpa_new = q("select avg(mrr) v from marts.fct_mrr where movement_type = 'new'").v[0]

# ---------------------------------------------------------------- Q4 cohorts
coh = q("""select cohort_month, sum(retained_customers)::double / sum(cohort_customers) r,
                  sum(retained_mrr) / sum(cohort_start_mrr) rr, sum(cohort_customers) n
           from marts.agg_cohort_retention where months_since_start = 6 group by 1 order by r desc""")
m12 = q("""select sum(retained_customers)::double / sum(cohort_customers) r, sum(retained_mrr) / sum(cohort_start_mrr) rr
           from marts.agg_cohort_retention where months_since_start = 12""").iloc[0]
by_ch = q("""select acquisition_channel channel, sum(retained_customers)::double / sum(cohort_customers) r
             from marts.agg_cohort_retention where months_since_start = 12 group by 1 order by r desc""")
best_coh, worst_coh = coh.iloc[0], coh.iloc[-1]

# ---------------------------------------------------------------- Q5 churn drivers
reasons = q("""select churn_reason, count(*) n from marts.dim_accounts where lifecycle_status = 'churned'
               group by 1 order by n desc""")
reasons["share"] = reasons.n / reasons.n.sum()
invol_share = reasons.loc[reasons.churn_reason == "payment_failure", "share"].sum()
plan_churn = q("""select p.plan_name, count(*) filter (where m.movement_type = 'churn')::double
                         / count(*) filter (where m.prev_mrr > 0) r
                  from marts.fct_mrr m join marts.dim_accounts a using (account_id)
                  join marts.dim_plans p on p.plan_id = a.first_plan_id group by 1 order by r desc""")
early = q("""select avg((tenure_months <= 2)::int) v from marts.dim_accounts where lifecycle_status = 'churned'""").v[0]
imp = pd.Series(cm["permutation_importance"]).sort_values(ascending=False)
nice = {"tickets_90d": "support tickets in the last 90 days", "sessions_per_seat_3m": "sessions per seat (engagement)",
        "failed_attempts_90d": "recent failed payments", "tenure_months": "tenure", "mrr": "MRR / plan level",
        "usage_trend": "usage trend", "acquisition_channel": "acquisition channel", "is_activated": "activation"}
top_drivers = [nice.get(k, k.replace("_", " ")) for k in imp.index[:4]]
churned_mrr_2025 = -kpi[kpi.month.dt.year == 2025].churned_mrr.sum()

# ---------------------------------------------------------------- Q6 plans
plans = q("""select p.plan_name, count(*) customers, sum(m.mrr) mrr from marts.fct_mrr m
             join marts.dim_plans p using (plan_id) where m.month = date '2025-12-01' and m.is_active
             group by 1 order by mrr desc""")
plans["share"] = plans.mrr / plans.mrr.sum()
plans["cust_share"] = plans.customers / plans.customers.sum()
top_plan = plans.iloc[0]

# ---------------------------------------------------------------- Q7 new vs existing
y25 = kpi[kpi.month.dt.year == 2025]
new25, exp25, con25, chn25 = y25.new_mrr.sum(), y25.expansion_mrr.sum(), y25.contraction_mrr.sum(), y25.churned_mrr.sum()
existing_net = exp25 + con25 + chn25
growth25 = last.mrr - dec24.mrr

# ---------------------------------------------------------------- Q8 unit economics
paid = perf[perf.cac.notna()].sort_values("ltv_to_cac", ascending=False)
best_ue, worst_ue = paid.iloc[0], paid.iloc[-1]
blended_paid_cac = paid.spend.sum() / paid.new_customers.sum()

# ---------------------------------------------------------------- Q9 forecast
fcst = pd.DataFrame(fc["forecast"])
end = fcst.iloc[-1]
best_model = fc["selected_model"]
mape = fc["scores"][best_model]["MAPE"]

# ---------------------------------------------------------------- scenario sizing for recommendations
invol_mrr_2025 = q("""select sum(m.prev_mrr) v from marts.fct_mrr m join marts.dim_accounts a using (account_id)
                      where m.movement_type = 'churn' and a.churn_type = 'involuntary' and year(m.month) = 2025""").v[0]
high = next(t for t in cm["scored_tiers"] if t["risk_tier"] == "High")
P = ab["primary"]
realloc = 0.2 * worst_ue.spend / 24 * 12            # 20% of the worst channel's annualised spend

md = f"""# CloudDesk - Growth & Profitability Review (FY2024-FY2025)

> **CloudDesk is a fictional company and all data is synthetic**, generated by `scripts/generate_data.py`
> (seed 42). Every number in this report is computed by `analysis/business_insights.py` from the warehouse built in the
> same pipeline run; none is typed by hand. Use it to demonstrate method, not as industry benchmarks.

## Executive summary
- **Growth is strong but decelerating.** MRR grew from {money(dec24.mrr)} to **{money(last.mrr)}** in 2025
  ({last.mrr / dec24.mrr - 1:+.0%}); ARR run-rate **{money(last.arr)}**. Month-over-month growth slowed from
  {pct(kpi.mrr_growth_rate.iloc[12])} (Jan) to {pct(last.mrr_growth_rate)} (Dec).
- **Retention is the main constraint.** Trailing-12-month NRR is **{pct(last.nrr_12m, 0)}** and GRR **{pct(last.grr_12m, 0)}**;
  in 2025 churn and contraction removed {money(-(chn25 + con25))} of MRR, equal to {-(chn25 + con25) / new25:.0%} of new MRR.
- **Activation is the biggest funnel lever.** {pct(steps[worst_step], 0)} of accounts that create a project never invite a teammate;
  activated trials convert at {pct(act_conv, 0)} vs {pct(nonact_conv, 0)} for the rest.
- **{invol_share:.0%} of churn is involuntary (failed payments)** - the cheapest churn to fix.
- **Unit economics are healthy overall** (paid CAC {money(blended_paid_cac)}); {L[best_ue.channel]} is the most efficient channel
  ({best_ue.ltv_to_cac:.1f}x LTV/CAC) and {L[worst_ue.channel]} the least ({worst_ue.ltv_to_cac:.1f}x).
- **Outlook:** MRR is forecast to reach **{money(end['mrr_forecast'])}** by June 2026 (80% interval {money(end['lower_80'])}-{money(end['upper_80'])}).

---

## 1. Which acquisition channels bring the most customers?
- **Finding:** {L[top_vol.channel]} brings the most paying customers ({int(top_vol.customers):,}, {top_vol.customers / ch.customers.sum():.0%} of all),
  followed by {L[ch.iloc[1].channel]} ({int(ch.iloc[1].customers):,}).
- **Metric:** paying customers from signups up to 17 Dec 2025 - """ + ", ".join(
    f"{L[r.channel]} {int(r.customers):,}" for r in ch.itertuples()) + f""".
- **Why it matters:** {L[top_vol.channel]} has no media cost, so the business depends on SEO/brand for its largest source;
  paid search is the largest *paid* engine and the most exposed to CPC inflation.
- **Action:** protect organic (content/SEO investment, brand); diversify paid volume so no paid channel exceeds ~40% of paid customers.

## 2. Which channels generate the best conversion rates?
- **Finding:** {L[best_conv.channel]} converts best signup-to-paid ({pct(best_conv.signup_to_paid)}), {L[worst_conv.channel]} worst
  ({pct(worst_conv.signup_to_paid)}). From the very top of the funnel, {L[best_v2p.channel]} has the best visit-to-paid rate ({pct(best_v2p.visit_to_paid, 2)}).
- **Metric:** signup -> paid: """ + ", ".join(f"{L[r.channel]} {pct(r.signup_to_paid)}" for r in ch.sort_values("signup_to_paid", ascending=False).itertuples()) + f""".
- **Why it matters:** {onb_note}
- **Action:** launch a structured referral programme (credit for referrer and referee); tighten {L[worst_conv.channel]} targeting
  and send its signups to a guided onboarding path.

## 3. Where are customers dropping out of the funnel?
- **Finding:** the largest in-product leak is **{worst_step}** ({pct(steps[worst_step], 0)} lost). Before that, {pct(steps['Signup -> Onboarded'], 0)} of signups never finish onboarding.
- **Metric:** {visitors:,.0f} visitors -> {int(f.s):,} signups ({f.s / visitors:.2%}) -> {int(f.o):,} onboarded -> {int(f.p):,} created a project
  -> {int(f.a):,} activated -> {int(f.c):,} paying. {f.nac / f.c:.0%} of payers never activated.
- **Why it matters:** activation is the strongest conversion predictor ({pct(act_conv, 0)} vs {pct(nonact_conv, 0)}) and also lowers churn.
- **Action:** add an "invite your team" step into project creation, templates that require collaboration, and a day-3 nudge.
  *Scenario:* +5 points of project->activation would add ~{extra_customers:,.0f} paying customers over the period
  (~{money(extra_customers * arpa_new)} MRR) at today's conversion rates.

## 4. Which customer cohorts retain the best?
- **Finding:** the best Month-6 cohort is {pd.Timestamp(best_coh.cohort_month):%b %Y} ({pct(best_coh.r)} still paying), the weakest
  {pd.Timestamp(worst_coh.cohort_month):%b %Y} ({pct(worst_coh.r)}). Across cohorts, Month-12 logo retention is **{pct(m12.r)}**
  and Month-12 revenue retention **{pct(m12.rr)}** (expansion partly offsets lost logos).
- **Metric:** Month-12 logo retention by channel - """ + ", ".join(f"{L[r.channel]} {pct(r.r)}" for r in by_ch.itertuples()) + f""".
- **Why it matters:** channel quality differs after the sale too: {L[by_ch.iloc[0].channel]} customers retain
  {(by_ch.iloc[0].r - by_ch.iloc[-1].r) * 100:.0f} points better than {L[by_ch.iloc[-1].channel]} customers at Month 12.
- **Action:** judge channels on retained revenue, not first-month conversions; feed cohort retention into bidding (value-based bidding).

## 5. What are the main drivers of churn?
- **Finding:** churn is concentrated early ({early:.0%} of churners leave within 2 months) and on the entry plan
  (customers who started on {plan_churn.iloc[0].plan_name} churn {pct(plan_churn.iloc[0].r, 2)} per month vs {pct(plan_churn.iloc[-1].r, 2)} for {plan_churn.iloc[-1].plan_name}).
  The churn model's strongest signals are {', '.join(top_drivers[:-1])} and {top_drivers[-1]}.
- **Metric:** churn reasons - """ + ", ".join(f"{r.churn_reason.replace('_', ' ')} {r.share:.0%}" for r in reasons.itertuples()) + f""".
  2025 churned MRR: {money(churned_mrr_2025)}. Model (out-of-time test): ROC-AUC {cm['test'][cm['selected_model']]['roc_auc']:.2f},
  PR-AUC {cm['test'][cm['selected_model']]['pr_auc']:.2f} vs a {cm['splits']['test']['churn_rate']:.1%} base rate.
- **Why it matters:** {high['customers']:,} active customers are High risk today ({money(high['mrr'])} MRR); these are identifiable before they leave.
- **Action:** dunning upgrade for payment failures; CSM playbook triggered by support-ticket spikes and usage drops; first-90-days onboarding programme.

## 6. Which subscription plans contribute most to revenue?
- **Finding:** **{top_plan.plan_name}** contributes {pct(top_plan.share, 0)} of MRR from {pct(top_plan.cust_share, 0)} of customers.
- **Metric:** Dec-2025 MRR - """ + ", ".join(f"{r.plan_name} {money(r.mrr)} ({r.share:.0%} of MRR, {r.customers:,} customers)" for r in plans.itertuples()) + f""".
- **Why it matters:** revenue is weighted to higher tiers, which also churn least - upgrades are worth more than extra Starter logos.
- **Action:** make the Starter -> Pro upgrade path explicit (seat limits, usage prompts); annual pricing on Pro/Business (the A/B test supports an annual-discount message).

## 7. Is revenue growth driven by new customers or existing customers?
- **Finding:** growth is **driven by new customers**. In 2025, new MRR was {money(new25)} while the existing base contributed a *net*
  {money(existing_net)} (expansion {money(exp25)}, contraction {money(con25)}, churn {money(chn25)}).
- **Metric:** net MRR added in 2025 = {money(growth25)} = new MRR {money(new25)} {'minus' if existing_net < 0 else 'plus'} {money(abs(existing_net))} from the existing base
  ({abs(existing_net) / new25:.0%} of new MRR {'lost' if existing_net < 0 else 'added'} by existing customers on net); NRR {pct(last.nrr_12m, 0)}.
- **Why it matters:** with NRR below 100%, the company must out-acquire its own churn every month; as the base grows, the same churn rate erases more new MRR.
- **Action:** set an NRR target (>= 95% next year) owned by Customer Success; launch expansion motions (seat-based add-ons, Business tier features).

## 8. Which channels have the best LTV/CAC?
- **Finding:** {L[best_ue.channel]} {best_ue.ltv_to_cac:.1f}x (CAC {money(best_ue.cac)}, payback {best_ue.cac_payback_months:.1f} months) is best;
  {L[worst_ue.channel]} {worst_ue.ltv_to_cac:.1f}x (CAC {money(worst_ue.cac)}, payback {worst_ue.cac_payback_months:.1f} months) is weakest.
- **Metric:** """ + ", ".join(f"{L[r.channel]} {r.ltv_to_cac:.1f}x / CAC {money(r.cac)}" for r in paid.itertuples()) + f""".
  LTV = ARPA x 80% gross margin / monthly logo churn (assumptions in `docs/metric_definitions.md`).
- **Why it matters:** all paid channels clear the 3x rule of thumb, but marginal dollars should go where payback is shortest.
- **Action:** shift budget toward {L[best_ue.channel]} until its marginal CAC rises; renegotiate {L[worst_ue.channel]} terms or cap spend.
  *Scenario:* moving 20% of {L[worst_ue.channel]}'s annual spend (~{money(realloc)}) to {L[best_ue.channel]} at its current CAC would buy
  ~{realloc / best_ue.cac:,.0f} customers instead of ~{realloc / worst_ue.cac:,.0f} (assumes constant CAC - verify with incremental tests).

## 9. What is the projected revenue trajectory?
- **Finding:** MRR is projected at **{money(end['mrr_forecast'])}** in June 2026 ({end['mrr_forecast'] / last.mrr - 1:+.0%} vs Dec 2025),
  ARR run-rate {money(end['arr_forecast'])}.
- **Metric:** model `{best_model}` selected by rolling-origin backtest (MAPE {pct(mape)}); 80% interval {money(end['lower_80'])}-{money(end['upper_80'])}.
- **Why it matters:** the forecast assumes current retention persists; each point of monthly churn removed compounds directly into this line.
- **Action:** use the 80% lower bound for hiring/spend commitments; track actuals monthly against the band.

## 10. What actions should the company take?
| # | Action | Owner | Evidence | Sized impact (illustrative) |
|---|---|---|---|---|
| 1 | Fix involuntary churn: card updater, pre-expiry emails, smarter retries, grace period | Finance / Billing | {invol_share:.0%} of churn is payment failure | Halving it would have kept ~{money(invol_mrr_2025 / 2)} of MRR lost in 2025 |
| 2 | Ship the pricing-page annual-discount banner (A/B: **{ab['decision']['recommendation']}**) | Growth | lift {P['rel_lift']:+.1%}, p = {P['p_value']:.3f}, guardrails OK | {money(ab['impact']['ci95'][0])}-{money(ab['impact']['ci95'][1])} new MRR per month (95% CI) |
| 3 | Activation programme: teammate-invite step, templates, nudges | Product | {pct(steps[worst_step], 0)} leak at project -> activation | +5pp activation ~ {extra_customers:,.0f} more customers |
| 4 | Risk-based Customer Success outreach using churn scores | Customer Success | {high['customers']:,} High-risk customers, {money(high['mrr'])} MRR | Measure with a 10-20% holdout before scaling |
| 5 | Re-allocate paid budget toward {L[best_ue.channel]} and referral | Marketing | LTV/CAC {best_ue.ltv_to_cac:.1f}x vs {worst_ue.ltv_to_cac:.1f}x | ~{realloc / best_ue.cac - realloc / worst_ue.cac:,.0f} more customers/yr for the same spend |
| 6 | Expansion motions and an NRR target (>= 95%) | CS / Product | NRR {pct(last.nrr_12m, 0)}, GRR {pct(last.grr_12m, 0)} | Every +1pt of NRR ~ {money(last.mrr * 0.01 * 12)} ARR |

## Limitations
- Synthetic data: relationships (e.g. activation -> conversion, tickets -> churn) were designed into the generator, so the analysis
  recovers them cleanly; real data will be noisier.
- No cost data beyond paid media (no sales salaries, tooling, COGS), so CAC and LTV are marketing-only and margin is assumed at 80%.
- Scenario impacts assume other rates stay constant; validate each action with an experiment before booking the benefit.
"""
(R / "business_insights_report.md").write_text(md, encoding="utf-8")
print(md[:2500])
print("...\nwrote reports/business_insights_report.md")
