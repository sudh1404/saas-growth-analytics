-- Payment health per account: failed attempts, unpaid invoices and recovered (dunning) invoices.
with inv as (
    select
        i.account_id,
        i.invoice_id,
        i.is_paid,
        i.amount,
        count(p.payment_id)                                  as attempts,
        count(case when not p.is_success then 1 end)         as failed_attempts
    from {{ ref('stg_invoices') }} i
    join {{ ref('stg_payments') }} p using (invoice_id)
    group by 1, 2, 3, 4
)
select
    account_id,
    count(*)                                                  as invoices,
    sum(failed_attempts)                                      as failed_payment_attempts,
    count(case when not is_paid then 1 end)                   as unpaid_invoices,
    count(case when is_paid and failed_attempts > 0 then 1 end) as recovered_invoices,
    sum(case when is_paid then amount else 0 end)             as revenue_collected,
    sum(case when not is_paid then amount else 0 end)         as revenue_uncollected
from inv
group by 1
