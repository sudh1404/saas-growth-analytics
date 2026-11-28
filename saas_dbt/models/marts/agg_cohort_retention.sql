-- Monthly acquisition cohorts (cohort = month of first payment), Month 0..12, by acquisition channel.
-- Logo retention = retained_customers / cohort_customers; revenue retention = retained_mrr / cohort_start_mrr.
-- Sum numerators and denominators across channels to get the all-channel figure.
with activity as (
    select m.account_id, m.cohort_month, a.acquisition_channel, m.months_since_start, m.mrr
    from {{ ref('fct_mrr') }} m
    join {{ ref('dim_accounts') }} a using (account_id)
    where m.is_active and m.months_since_start <= 12
),
cohorts as (
    select cohort_month, acquisition_channel,
           count(*) as cohort_customers, sum(mrr) as cohort_start_mrr
    from activity where months_since_start = 0
    group by 1, 2
),
grid as (
    select c.*, k.months_since_start
    from cohorts c
    cross join generate_series(0, 12) k(months_since_start)
    where c.cohort_month + to_months(k.months_since_start) <= date_trunc('month', date '{{ var("snapshot_date") }}')
)
select
    g.cohort_month,
    g.acquisition_channel,
    g.months_since_start,
    g.cohort_customers,
    g.cohort_start_mrr,
    count(a.account_id)          as retained_customers,
    coalesce(sum(a.mrr), 0)      as retained_mrr,
    count(a.account_id) / g.cohort_customers        as logo_retention,
    coalesce(sum(a.mrr), 0) / g.cohort_start_mrr    as revenue_retention
from grid g
left join activity a
       on a.cohort_month = g.cohort_month
      and a.acquisition_channel = g.acquisition_channel
      and a.months_since_start = g.months_since_start
group by 1, 2, 3, 4, 5
