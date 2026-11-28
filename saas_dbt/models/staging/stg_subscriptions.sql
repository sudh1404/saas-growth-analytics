select
    subscription_id,
    account_id,
    plan_id,
    cast(start_date as date)     as start_date,
    cast(end_date as date)       as end_date,
    cast(mrr as double)          as mrr,
    start_reason,
    end_reason,
    cast(churn_reason as varchar) as churn_reason,
    case
        when end_reason <> 'churned' or end_reason is null then null
        when churn_reason = 'payment_failure'                then 'involuntary'
        else 'voluntary'
    end                          as churn_type,
    end_date is null             as is_active
from {{ source('raw', 'subscriptions') }}
