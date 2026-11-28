select
    plan_id,
    plan_name,
    cast(monthly_price as double) as monthly_price,
    plan_tier,
    cast(max_seats as integer)    as max_seats
from {{ source('raw', 'plans') }}
