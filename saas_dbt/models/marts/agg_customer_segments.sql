-- Snapshot segmentation of every customer active at the snapshot date.
-- Engagement and trend use the last 3 *complete* usage months; the in-progress snapshot month is excluded.
{% set snap = "date '" ~ var("snapshot_date") ~ "'" %}
with active as (
    select * from {{ ref('dim_accounts') }} where lifecycle_status = 'active'
),
usage as (
    select account_id,
           avg(case when usage_month >  {{ snap }} - interval 4 month then sessions_per_seat end) as sps_recent,
           avg(case when usage_month <= {{ snap }} - interval 4 month
                     and usage_month >  {{ snap }} - interval 7 month then sessions_per_seat end) as sps_prior
    from {{ ref('fct_usage_monthly') }}
    group by 1
),
recent_payments as (
    select account_id, count(*) as failed_attempts_90d
    from {{ ref('fct_payments') }}
    where not is_success and attempted_at > {{ snap }} - interval 90 day
    group by 1
),
recent_tickets as (
    select account_id, count(*) as tickets_90d
    from {{ ref('fct_product_events') }}
    where event_name = 'support_ticket_opened' and event_ts > {{ snap }} - interval 90 day
    group by 1
),
base as (
    select
        a.account_id, a.acquisition_channel, a.country, a.company_size, a.customer_segment,
        a.current_plan_id, p.plan_name as current_plan, a.current_mrr, a.revenue_to_date,
        a.tenure_months, a.is_activated,
        u.sps_recent                                            as sessions_per_seat_3m,
        u.sps_recent / nullif(u.sps_prior, 0)                   as usage_trend,
        coalesce(rp.failed_attempts_90d, 0)                     as failed_payment_attempts_90d,
        coalesce(rt.tickets_90d, 0)                             as support_tickets_90d
    from active a
    left join {{ ref('dim_plans') }} p on p.plan_id = a.current_plan_id
    left join usage u using (account_id)
    left join recent_payments rp using (account_id)
    left join recent_tickets rt using (account_id)
),
scored as (
    select
        *,
        ntile(4) over (order by revenue_to_date desc, account_id)    as revenue_quartile,
        ntile(3) over (order by coalesce(sessions_per_seat_3m, 0), account_id) as engagement_tercile,
        sum(revenue_to_date) over (order by revenue_to_date desc, account_id rows unbounded preceding)
            / sum(revenue_to_date) over ()                           as cumulative_revenue_share,
          (case when coalesce(usage_trend, 1) < 0.7 then 2 else 0 end)
        + (case when failed_payment_attempts_90d > 0 then 2 else 0 end)
        + (case when support_tickets_90d >= 2 then 1 else 0 end)
        + (case when not is_activated then 1 else 0 end)
        + (case when tenure_months < 3 then 1 else 0 end)           as rule_risk_score
    from base
)
select
    *,
    case revenue_quartile when 1 then 'Q1 Top 25%' when 2 then 'Q2' when 3 then 'Q3' else 'Q4 Bottom 25%' end as revenue_segment,
    case engagement_tercile when 3 then 'High' when 2 then 'Medium' else 'Low' end                       as engagement_segment,
    case when tenure_months < 3 then '0-2 months' when tenure_months < 6 then '3-5 months'
         when tenure_months < 12 then '6-11 months' else '12+ months' end                                as tenure_band,
    case when rule_risk_score >= 4 then 'High' when rule_risk_score >= 2 then 'Medium' else 'Low' end    as rule_based_risk
from scored
