-- Product/funnel events, de-duplicated: double-fired tracking events share account, name and timestamp.
with ranked as (
    select
        event_id,
        account_id,
        event_name,
        cast(event_ts as timestamp) as event_ts,
        row_number() over (partition by account_id, event_name, event_ts order by event_id) as rn
    from {{ source('raw', 'events') }}
)
select
    event_id,
    account_id,
    event_name,
    event_ts,
    cast(event_ts as date)                              as event_date,
    cast(date_trunc('month', event_ts) as date)         as event_month
from ranked
where rn = 1
