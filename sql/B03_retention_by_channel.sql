-- B03 | Retention by acquisition channel at Month 1, 3, 6 and 12 (weighted across cohorts).
with r as (
    select acquisition_channel, months_since_start,
           sum(retained_customers) * 1.0 / sum(cohort_customers) as logo_ret,
           sum(retained_mrr) / sum(cohort_start_mrr)            as rev_ret
    from marts.agg_cohort_retention
    group by 1, 2
)
select
    acquisition_channel,
    round(100 * max(case when months_since_start = 1  then logo_ret end), 1) as m1_logo_pct,
    round(100 * max(case when months_since_start = 3  then logo_ret end), 1) as m3_logo_pct,
    round(100 * max(case when months_since_start = 6  then logo_ret end), 1) as m6_logo_pct,
    round(100 * max(case when months_since_start = 12 then logo_ret end), 1) as m12_logo_pct,
    round(100 * max(case when months_since_start = 12 then rev_ret end), 1)  as m12_revenue_pct,
    rank() over (order by max(case when months_since_start = 12 then logo_ret end) desc) as rank_m12
from r
group by 1
order by rank_m12;
