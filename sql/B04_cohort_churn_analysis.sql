-- B04 | Churn by acquisition cohort (quarter of first payment): churn type, reasons and time-to-churn.
select
    year(cohort_month) || '-Q' || quarter(cohort_month)                             as cohort_quarter,
    count(*)                                                                        as customers,
    count(*) filter (where lifecycle_status = 'churned')                            as churned,
    round(100.0 * count(*) filter (where lifecycle_status = 'churned') / count(*), 1) as churned_pct,
    count(*) filter (where churn_type = 'voluntary')                                as voluntary,
    count(*) filter (where churn_type = 'involuntary')                              as involuntary,
    mode(churn_reason)                                                              as top_churn_reason,
    round(avg(tenure_months) filter (where lifecycle_status = 'churned'), 1)        as avg_months_to_churn,
    round(100.0 * count(*) filter (where lifecycle_status = 'churned' and tenure_months <= 2)
          / nullif(count(*) filter (where lifecycle_status = 'churned'), 0), 1)     as pct_churn_in_first_2_months
from marts.dim_accounts
where is_paying_customer
group by 1
order by 1;
