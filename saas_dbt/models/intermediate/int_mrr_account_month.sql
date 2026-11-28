-- One row per paying account per month (first paid month -> snapshot month) with MRR active at month end.
-- Months after churn carry mrr = 0 so churn can be detected downstream.
with months as (
    select cast(m as date) as month_start,
           cast(m + interval 1 month - interval 1 day as date) as month_end
    from generate_series(date '2024-01-01',
                         date_trunc('month', date '{{ var("snapshot_date") }}'),
                         interval 1 month) t(m)
),
first_paid as (
    select account_id, date_trunc('month', min(start_date)) as first_month
    from {{ ref('stg_subscriptions') }}
    group by 1
),
spine as (
    select f.account_id, m.month_start, m.month_end
    from first_paid f
    join months m on m.month_start >= f.first_month
)
select
    s.account_id,
    s.month_start                 as month,
    coalesce(sum(sub.mrr), 0)     as mrr,
    max(sub.plan_id)              as plan_id
from spine s
left join {{ ref('stg_subscriptions') }} sub
       on sub.account_id = s.account_id
      and sub.start_date <= s.month_end
      and (sub.end_date is null or sub.end_date > s.month_end)
group by 1, 2
