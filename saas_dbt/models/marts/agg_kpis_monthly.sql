-- One row per month with the core SaaS KPIs used across the dashboard and the business report.
with customers as (
    select
        month,
        count(case when is_active then 1 end)                        as active_customers,
        count(case when movement_type = 'new' then 1 end)            as new_customers,
        count(case when movement_type = 'churn' then 1 end)          as churned_customers,
        count(case when prev_mrr > 0 then 1 end)                     as customers_at_start,
        sum(case when is_active then active_seats end)               as active_seats,
        sum(case when is_active and active_seats is not null then mrr end) as mrr_with_known_seats
    from {{ ref('fct_mrr') }}
    group by 1
),
retention as (
    -- trailing-12-month NRR / GRR: base = accounts paying 12 months earlier
    select
        cur.month,
        sum(base.mrr)                                   as base_mrr_12m_ago,
        sum(coalesce(cur_m.mrr, 0))                     as base_cohort_mrr_now,
        sum(least(coalesce(cur_m.mrr, 0), base.mrr))    as base_cohort_mrr_now_capped
    from (select distinct month from {{ ref('fct_mrr') }}) cur
    join {{ ref('fct_mrr') }} base
      on base.month = cur.month - interval 12 month and base.mrr > 0
    left join {{ ref('fct_mrr') }} cur_m
      on cur_m.account_id = base.account_id and cur_m.month = cur.month
    group by 1
),
funnel as (
    select date_trunc('month', date) as month,
           sum(visitors) as visitors, sum(signups) as signups,
           sum(spend) as marketing_spend,
           sum(case when channel in ('paid_search', 'paid_social', 'content', 'partner') then new_customers end) as paid_channel_new_customers
    from {{ ref('fct_marketing_daily') }}
    group by 1
)
select
    b.month,
    c.active_customers,
    c.new_customers,
    c.churned_customers,
    c.churned_customers / nullif(c.customers_at_start, 0)               as logo_churn_rate,
    b.opening_mrr,
    b.new_mrr,
    b.expansion_mrr,
    b.reactivation_mrr,
    b.contraction_mrr,
    b.churned_mrr,
    b.net_new_mrr,
    b.closing_mrr                                                      as mrr,
    b.closing_mrr * 12                                                 as arr,
    b.net_new_mrr / nullif(b.opening_mrr, 0)                           as mrr_growth_rate,
    -(b.churned_mrr + b.contraction_mrr) / nullif(b.opening_mrr, 0)    as gross_mrr_churn_rate,
    b.closing_mrr / nullif(c.active_customers, 0)                      as arpa,
    c.active_seats,
    c.mrr_with_known_seats / nullif(c.active_seats, 0)                 as arpu,   -- accounts with no usage yet excluded
    r.base_cohort_mrr_now / nullif(r.base_mrr_12m_ago, 0)              as nrr_12m,
    r.base_cohort_mrr_now_capped / nullif(r.base_mrr_12m_ago, 0)       as grr_12m,
    f.visitors,
    f.signups,
    f.marketing_spend,
    f.paid_channel_new_customers,
    f.marketing_spend / nullif(c.new_customers, 0)                     as blended_cac,
    f.marketing_spend / nullif(f.paid_channel_new_customers, 0)        as paid_cac
from {{ ref('agg_mrr_bridge_monthly') }} b
join customers c using (month)
left join retention r using (month)
left join funnel f using (month)
