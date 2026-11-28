-- Closing MRR at the snapshot month must equal the sum of MRR on subscriptions still active at the snapshot.
with bridge as (
    select closing_mrr from {{ ref('agg_mrr_bridge_monthly') }}
    where month = date_trunc('month', date '{{ var("snapshot_date") }}')
),
subs as (
    select sum(mrr) as active_mrr from {{ ref('stg_subscriptions') }}
    where start_date <= date '{{ var("snapshot_date") }}'
      and (end_date is null or end_date > date '{{ var("snapshot_date") }}')
)
select * from bridge, subs where abs(closing_mrr - active_mrr) > 0.01
