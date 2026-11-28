-- B02 | Average retention curve across cohorts (logo and revenue) and the implied month-over-month churn.
-- Each month-k figure uses only cohorts old enough to have reached month k.
with r as (
    select months_since_start,
           sum(retained_customers) as retained, sum(cohort_customers) as cohort_size,
           sum(retained_mrr) as retained_mrr, sum(cohort_start_mrr) as start_mrr,
           count(distinct cohort_month) as cohorts_observed
    from marts.agg_cohort_retention
    group by 1
)
select
    months_since_start,
    cohorts_observed,
    round(100.0 * retained / cohort_size, 1)                    as logo_retention_pct,
    round(100.0 * retained_mrr / start_mrr, 1)                  as revenue_retention_pct,
    round(100.0 * (1 - (retained * 1.0 / cohort_size)
          / lag(retained * 1.0 / cohort_size) over (order by months_since_start)), 2) as implied_monthly_churn_pct
from r
order by months_since_start;
