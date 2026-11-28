-- E03 | Engagement and tenure segments of active customers, and historical churn by engagement band.
-- Part 1: current mix. Part 2: churn in the following 3 months for customers active at 2025-06-30,
-- grouped by their engagement tercile at that time (shows engagement is predictive).
with hist as (
    select m.account_id,
           ntile(3) over (order by coalesce(u.sps, 0), m.account_id) as tercile,
           (a.churned_date is not null and a.churned_date <= date '2025-09-30')::int as churned_next_3m
    from marts.fct_mrr m
    join marts.dim_accounts a using (account_id)
    left join (select account_id, avg(sessions_per_seat) as sps
               from marts.fct_usage_monthly
               where usage_month between date '2025-03-01' and date '2025-05-01'
               group by 1) u using (account_id)
    where m.month = date '2025-06-01' and m.is_active
)
select 'current_mix' as part, engagement_segment as segment, tenure_band as sub_segment,
       count(*) as customers, round(avg(current_mrr), 1) as avg_mrr, null::double as churn_next_3m_pct
from marts.agg_customer_segments group by 1, 2, 3
union all
select 'historical_churn_by_engagement',
       case tercile when 3 then 'High' when 2 then 'Medium' else 'Low' end, 'customers active Jun-2025',
       count(*), null, round(100.0 * avg(churned_next_3m), 1)
from hist group by 1, 2, 3
order by part, segment, sub_segment;
