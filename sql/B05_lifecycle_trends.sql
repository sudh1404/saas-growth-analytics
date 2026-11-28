-- B05 | Customer lifecycle trend: active, new, churned and net-added customers each month, with churn reasons.
select
    k.month,
    k.active_customers,
    k.new_customers,
    k.churned_customers,
    k.new_customers - k.churned_customers                         as net_customer_adds,
    round(100 * k.logo_churn_rate, 2)                             as logo_churn_pct,
    round(100 * avg(k.logo_churn_rate) over (order by k.month rows 2 preceding), 2) as logo_churn_pct_3m_avg,
    c.voluntary_churn,
    c.involuntary_churn
from marts.agg_kpis_monthly k
left join (
    select date_trunc('month', churned_date) as month,   -- matches fct_mrr: churn month = month containing end_date
           count(*) filter (where churn_type = 'voluntary')   as voluntary_churn,
           count(*) filter (where churn_type = 'involuntary') as involuntary_churn
    from marts.dim_accounts where churned_date is not null group by 1
) c using (month)
order by k.month;
