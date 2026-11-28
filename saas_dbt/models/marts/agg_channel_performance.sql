-- Unit economics per acquisition channel over the full period (Jan 2024 - snapshot).
-- LTV = ARPA x gross margin / monthly logo churn rate   (simple steady-state formula; see docs/metric_definitions.md)
-- CAC = total channel spend / new paying customers acquired by that channel (unpaid channels have no CAC)
with funnel as (
    select channel,
           sum(visitors) as visitors, sum(signups) as signups,
           sum(spend) as spend, sum(new_customers) as new_customers
    from {{ ref('fct_marketing_daily') }}
    group by 1
),
revenue as (
    select a.acquisition_channel                                      as channel,
           avg(case when m.is_active then m.mrr end)                  as arpa,
           count(case when m.movement_type = 'churn' then 1 end)      as churn_events,
           count(case when m.prev_mrr > 0 then 1 end)                 as customer_months_at_risk,
           sum(case when m.month = date_trunc('month', date '{{ var("snapshot_date") }}') then m.mrr else 0 end) as current_mrr
    from {{ ref('fct_mrr') }} m
    join {{ ref('dim_accounts') }} a using (account_id)
    group by 1
),
calc as (
    select
        d.channel, d.channel_type,
        f.visitors, f.signups, f.new_customers,
        f.signups / nullif(f.visitors, 0)                              as visit_to_signup_rate,
        f.new_customers / nullif(f.signups, 0)                         as signup_to_paid_rate,
        case when d.is_paid then f.spend end                           as spend,
        case when d.is_paid then f.spend / nullif(f.new_customers, 0) end as cac,
        r.arpa,
        r.churn_events / nullif(r.customer_months_at_risk, 0)          as monthly_logo_churn,
        {{ var("gross_margin") }}                                      as gross_margin,
        r.current_mrr
    from {{ ref('dim_channel') }} d
    join funnel f using (channel)
    join revenue r using (channel)
)
select
    *,
    arpa * gross_margin / nullif(monthly_logo_churn, 0)                as ltv,
    (arpa * gross_margin / nullif(monthly_logo_churn, 0)) / nullif(cac, 0) as ltv_to_cac,
    cac / nullif(arpa * gross_margin, 0)                               as cac_payback_months,
    current_mrr / sum(current_mrr) over ()                             as share_of_current_mrr
from calc
