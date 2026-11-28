-- Monthly product usage. Sessions are NULL for a March-2025 tracking outage: kept as NULL (unknown), not zero.
select
    account_id,
    cast(usage_month as date)                          as usage_month,
    active_seats,
    cast(sessions as integer)                          as sessions,
    cast(sessions as double) / nullif(active_seats, 0) as sessions_per_seat
from {{ source('raw', 'usage_monthly') }}
