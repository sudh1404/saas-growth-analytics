-- B01 | Logo retention matrix by monthly acquisition cohort (cohort = month of first payment), Month 0..12.
-- Cells are NULL where the cohort is not yet old enough (right-censored), not 0.
with r as (
    select cohort_month, months_since_start,
           sum(retained_customers) as retained, sum(cohort_customers) as cohort_size
    from marts.agg_cohort_retention
    group by 1, 2
)
pivot (select cohort_month, max(cohort_size) over (partition by cohort_month) as customers,
              'M' || lpad(months_since_start::varchar, 2, '0') as m,
              round(100.0 * retained / cohort_size, 1) as pct from r)
on m
using first(pct)
order by cohort_month;
