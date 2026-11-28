-- A02 | Strict (closed) funnel: steps must be reached in order, with payment within 30 days of signup.
-- An account counts at a step only if it reached every earlier step, in order. Compared with A01 this shows
-- how many payers skipped activation.
select
    count(*)                                                                         as signed_up,
    count(*) filter (where onboarded_at is not null)                                 as onboarded,
    count(*) filter (where project_created_at > onboarded_at)                        as created_project,
    count(*) filter (where activated_at > project_created_at
                       and project_created_at > onboarded_at)                        as activated,
    count(*) filter (where paid_at > activated_at
                       and activated_at > project_created_at
                       and project_created_at > onboarded_at
                       and paid_at <= signed_up_at + interval 30 day)                as became_paying,
    count(*) filter (where paid_at is not null and activated_at is null)             as paid_without_activation
from intermediate.int_account_funnel
where cast(signed_up_at as date) <= date '2025-12-17';
