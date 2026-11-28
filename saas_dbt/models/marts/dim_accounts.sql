-- Customer/account dimension: attributes, funnel flags, lifecycle status, churn info, revenue and payment health.
with subs as (
    select
        account_id,
        min(start_date)                                           as first_paid_date,
        max(case when is_active then plan_id end)                 as current_plan_id,
        max(case when is_active then mrr end)                     as current_mrr,
        max(case when end_reason = 'churned' then end_date end)   as churned_date,
        max(churn_reason)                                         as churn_reason,
        max(churn_type)                                           as churn_type,
        arg_min(plan_id, start_date)                              as first_plan_id,
        count(case when start_reason = 'upgrade' then 1 end)      as upgrades,
        count(case when start_reason = 'downgrade' then 1 end)    as downgrades
    from {{ ref('stg_subscriptions') }}
    group by 1
)
select
    a.account_id,
    a.signup_date,
    a.signup_month,
    a.acquisition_channel,
    a.country,
    a.company_size,
    a.customer_segment,
    a.industry,
    a.pricing_page_variant,
    f.onboarded_at is not null                         as is_onboarded,
    f.project_created_at is not null                   as has_created_project,
    f.activated_at is not null                         as is_activated,
    s.account_id is not null                           as is_paying_customer,
    s.first_paid_date,
    cast(date_trunc('month', s.first_paid_date) as date) as cohort_month,
    s.first_plan_id,
    s.current_plan_id,
    coalesce(s.current_mrr, 0)                         as current_mrr,
    s.churned_date,
    s.churn_reason,
    s.churn_type,
    case
        when s.account_id is null   then 'never_paid'
        when s.churned_date is null then 'active'
        else 'churned'
    end                                                as lifecycle_status,
    case when s.account_id is not null
         then datediff('month', s.first_paid_date, coalesce(s.churned_date, date '{{ var("snapshot_date") }}'))
    end                                                as tenure_months,
    coalesce(s.upgrades, 0)                            as upgrades,
    coalesce(s.downgrades, 0)                          as downgrades,
    coalesce(p.revenue_collected, 0)                   as revenue_to_date,
    coalesce(p.failed_payment_attempts, 0)             as failed_payment_attempts,
    coalesce(p.unpaid_invoices, 0)                     as unpaid_invoices,
    coalesce(f.support_tickets, 0)                     as support_tickets
from {{ ref('stg_accounts') }} a
left join {{ ref('int_account_funnel') }} f using (account_id)
left join subs s using (account_id)
left join {{ ref('int_account_payments') }} p using (account_id)
