-- C03 | Net and Gross Revenue Retention, trailing 12 months.
-- Base = accounts paying 12 months earlier. NRR includes their expansion; GRR caps each account at its starting MRR.
-- Part 1: computed from scratch at the snapshot month (Dec-2025 vs Dec-2024), as a transparent check.
-- Part 2: the monthly series from the KPI mart (must match Part 1 for 2025-12).
with start_base as (
    select account_id, mrr as start_mrr
    from marts.fct_mrr where month = date '2024-12-01' and mrr > 0
),
now as (
    select account_id, mrr as end_mrr from marts.fct_mrr where month = date '2025-12-01'
),
snapshot as (
    select
        date '2025-12-01'                                                              as month,
        count(*)                                                                       as base_customers,
        sum(start_mrr)                                                                 as start_mrr,
        sum(coalesce(end_mrr, 0))                                                      as end_mrr_same_customers,
        round(100.0 * sum(coalesce(end_mrr, 0)) / sum(start_mrr), 1)                   as nrr_pct,
        round(100.0 * sum(least(coalesce(end_mrr, 0), start_mrr)) / sum(start_mrr), 1) as grr_pct,
        count(*) filter (where coalesce(end_mrr, 0) = 0)                               as churned_customers,
        count(*) filter (where end_mrr > start_mrr)                                    as expanded_customers,
        count(*) filter (where end_mrr < start_mrr and end_mrr > 0)                    as contracted_customers
    from start_base left join now using (account_id)
)
select 'snapshot_check' as source, * from snapshot
union all by name
select 'kpi_mart' as source, month, round(100 * nrr_12m, 1) as nrr_pct, round(100 * grr_12m, 1) as grr_pct
from marts.agg_kpis_monthly where nrr_12m is not null
order by source desc, month;
