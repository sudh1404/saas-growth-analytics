-- One row per paying account per month with the MRR movement that explains the change.
-- Grain: account_id x month (month = first day of month; MRR measured at month end).
with base as (
    select
        m.account_id,
        m.month,
        m.mrr,
        m.plan_id,
        coalesce(lag(m.mrr) over (partition by m.account_id order by m.month), 0) as prev_mrr,
        min(m.month) over (partition by m.account_id)                             as first_month
    from {{ ref('int_mrr_account_month') }} m
),
classified as (
    select
        *,
        mrr - prev_mrr as mrr_change,
        case
            when prev_mrr = 0 and mrr > 0 and month = first_month then 'new'
            when prev_mrr = 0 and mrr > 0 then 'reactivation'
            when prev_mrr > 0 and mrr = 0 then 'churn'
            when mrr > prev_mrr           then 'expansion'
            when mrr < prev_mrr           then 'contraction'
            when mrr > 0                  then 'retained'
            else 'inactive'
        end as movement_type
    from base
),
seats as (
    select account_id, usage_month, active_seats from {{ ref('stg_usage_monthly') }}
)
select
    c.account_id,
    c.month,
    c.plan_id,
    c.mrr,
    c.prev_mrr,
    c.mrr_change,
    c.movement_type,
    c.first_month                                   as cohort_month,
    datediff('month', c.first_month, c.month)       as months_since_start,
    c.mrr > 0                                       as is_active,
    -- latest known seat count (as-of join) for ARPU; zero once churned
    case when c.mrr > 0 then s.active_seats else 0 end as active_seats
from classified c
asof left join seats s
       on s.account_id = c.account_id
      and c.month >= s.usage_month
where c.movement_type <> 'inactive'      -- drop months after churn
