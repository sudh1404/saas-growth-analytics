-- One row per account: when (if ever) it reached each funnel step.
-- Activation ("aha moment") = inviting a teammate.
select
    a.account_id,
    min(case when e.event_name = 'signed_up'            then e.event_ts end) as signed_up_at,
    min(case when e.event_name = 'onboarding_completed' then e.event_ts end) as onboarded_at,
    min(case when e.event_name = 'project_created'      then e.event_ts end) as project_created_at,
    min(case when e.event_name = 'teammate_invited'     then e.event_ts end) as activated_at,
    min(case when e.event_name = 'subscription_started' then e.event_ts end) as paid_at,
    count(case when e.event_name = 'support_ticket_opened' then 1 end)       as support_tickets
from {{ ref('stg_accounts') }} a
left join {{ ref('stg_events') }} e using (account_id)
group by 1
