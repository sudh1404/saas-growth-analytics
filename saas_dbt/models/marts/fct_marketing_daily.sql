-- Daily funnel inputs per channel: visitors, signups, paid media and new paying customers (CAC inputs).
select * from {{ ref('int_channel_daily') }}
