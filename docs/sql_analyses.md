# SQL analyses

> 22 queries in `sql/`, written for DuckDB against the dbt marts. Run them all with
> `python scripts/run_sql_analyses.py` (results saved to `reports/sql_results/<name>.csv`) or one at a time with
> `python scripts/run_query.py sql/<file>.sql`. CloudDesk is fictional; data is synthetic.

Techniques used: CTEs, window functions (`LAG`, `RANK`, `NTILE`, running `SUM`, `FIRST_VALUE` style maxima over windows),
`FILTER` aggregates, `PIVOT`, `UNION ALL` long-format reshaping, `ASOF` joins (in dbt), date spines with `generate_series`.

| Section | File | Business question | Output rows |
|---|---|---|---:|
| A. Acquisition & funnel | [`A01_funnel_overall.sql`](../sql/A01_funnel_overall.sql) | Acquisition funnel: visitors -> signups -> onboarded -> project -> activated -> paid | 6 |
| A. Acquisition & funnel | [`A02_funnel_closed_strict.sql`](../sql/A02_funnel_closed_strict.sql) | Strict (closed) funnel: an account counts at a step only if it reached every earlier step, in order, | 1 |
| A. Acquisition & funnel | [`A03_funnel_by_channel.sql`](../sql/A03_funnel_by_channel.sql) | Funnel conversion by acquisition channel (mature signups only), including visit -> signup. | 6 |
| A. Acquisition & funnel | [`A04_funnel_by_segment.sql`](../sql/A04_funnel_by_segment.sql) | Funnel conversion by country, company size and customer segment (mature signups only). | 13 |
| A. Acquisition & funnel | [`A05_funnel_leakage.sql`](../sql/A05_funnel_leakage.sql) | Funnel leakage: for every channel, which stage loses the most prospects (absolute and relative)? | 30 |
| B. Cohorts & retention | [`B01_cohort_retention_matrix.sql`](../sql/B01_cohort_retention_matrix.sql) | Logo retention matrix by monthly acquisition cohort (cohort = month of first payment), Month 0..12. | 24 |
| B. Cohorts & retention | [`B02_retention_curve_and_churn.sql`](../sql/B02_retention_curve_and_churn.sql) | Average retention curve across cohorts (logo and revenue) and the implied month-over-month churn. | 13 |
| B. Cohorts & retention | [`B03_retention_by_channel.sql`](../sql/B03_retention_by_channel.sql) | Retention by acquisition channel at Month 1, 3, 6 and 12 (weighted across cohorts). | 6 |
| B. Cohorts & retention | [`B04_cohort_churn_analysis.sql`](../sql/B04_cohort_churn_analysis.sql) | Churn by acquisition cohort (quarter of first payment): churn type, reasons and time-to-churn. | 8 |
| B. Cohorts & retention | [`B05_lifecycle_trends.sql`](../sql/B05_lifecycle_trends.sql) | Customer lifecycle trend: active, new, churned and net-added customers each month, with churn reasons. | 24 |
| C. Revenue | [`C01_mrr_bridge.sql`](../sql/C01_mrr_bridge.sql) | MRR bridge with ARR, Net New MRR and growth rate, plus an explicit reconciliation check. | 24 |
| C. Revenue | [`C02_arpa_arpu.sql`](../sql/C02_arpa_arpu.sql) | ARPA (MRR per paying account) and ARPU (MRR per active seat), monthly and by plan at the snapshot. | 27 |
| C. Revenue | [`C03_nrr_grr.sql`](../sql/C03_nrr_grr.sql) | Net and Gross Revenue Retention, trailing 12 months. | 13 |
| C. Revenue | [`C04_revenue_by_plan.sql`](../sql/C04_revenue_by_plan.sql) | MRR, customers and revenue share by subscription plan each quarter-end month, plus plan mix of new customers. | 24 |
| D. Acquisition cost & profitability | [`D01_cac_by_channel.sql`](../sql/D01_cac_by_channel.sql) | CAC by channel: full period and by quarter. | 37 |
| D. Acquisition cost & profitability | [`D02_ltv_cac_payback.sql`](../sql/D02_ltv_cac_payback.sql) | Unit economics by channel: CAC, ARPA, monthly logo churn, LTV, LTV:CAC and CAC payback. | 6 |
| D. Acquisition cost & profitability | [`D03_marketing_efficiency.sql`](../sql/D03_marketing_efficiency.sql) | Marketing spend efficiency by campaign: CPM, CPC, CTR, cost per signup and cost per new customer. | 9 |
| D. Acquisition cost & profitability | [`D04_revenue_contribution_by_channel.sql`](../sql/D04_revenue_contribution_by_channel.sql) | Revenue contribution by acquisition channel: current MRR, share, collected revenue and return on spend. | 6 |
| E. Segmentation | [`E01_revenue_concentration.sql`](../sql/E01_revenue_concentration.sql) | Revenue concentration (Pareto) of active customers: share of collected revenue by revenue quartile, | 4 |
| E. Segmentation | [`E02_segments_plan_size.sql`](../sql/E02_segments_plan_size.sql) | Active customers and MRR by subscription plan x company size (with row/column shares via window functions). | 15 |
| E. Segmentation | [`E03_engagement_tenure.sql`](../sql/E03_engagement_tenure.sql) | Engagement and tenure segments of active customers, and historical churn by engagement band. | 15 |
| E. Segmentation | [`E04_churn_risk_segments.sql`](../sql/E04_churn_risk_segments.sql) | Rule-based churn-risk segments of active customers: size, MRR at risk and the drivers present. | 3 |

## Validation

- **Reconciliation:** `C01` returns `reconciliation_diff` for every month; it is 0 (also enforced by the dbt test `assert_mrr_bridge_reconciles`).
- **Cross-checks:** `C03` recomputes NRR/GRR from scratch for Dec-2025 and returns it beside the dbt KPI mart value; they match.
- **Mature cohorts:** funnel queries only count signups on or before 2025-12-17 so open trials do not depress conversion.
- **Right-censoring:** cohort cells for months a cohort has not reached are NULL (B01) and excluded from averages (B02).


Metric definitions: [`docs/metric_definitions.md`](metric_definitions.md).
