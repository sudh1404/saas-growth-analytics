select
    invoice_id,
    account_id,
    subscription_id,
    cast(invoice_date as date)                               as invoice_date,
    cast(date_trunc('month', cast(invoice_date as date)) as date) as invoice_month,
    cast(due_date as date)                                   as due_date,
    cast(amount as double)                                   as amount,
    status,
    status = 'paid'                                          as is_paid
from {{ source('raw', 'invoices') }}
