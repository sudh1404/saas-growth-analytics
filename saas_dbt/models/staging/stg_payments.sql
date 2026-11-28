select
    payment_id,
    invoice_id,
    account_id,
    attempt_number,
    cast(attempted_at as timestamp) as attempted_at,
    cast(amount as double)          as amount,
    status,
    cast(failure_reason as varchar) as failure_reason,
    status = 'succeeded'            as is_success
from {{ source('raw', 'payments') }}
