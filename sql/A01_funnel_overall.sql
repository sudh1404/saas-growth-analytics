-- A01 | Acquisition funnel: visitors -> signups -> onboarded -> project -> activated -> paid
-- Business question: how many prospects reach each stage, and where is the biggest leak?
-- Definitions
--   * Only signups on or before 2025-12-17 are counted, so every account has finished its 14-day trial.
--   * Visitors come from web analytics (channel x day), so they cannot be broken down by account attributes.
--   * "Open" funnel: an account counts at a step if it ever reached it (see A02 for the strict, ordered version).
with mature as (
    select * from marts.dim_accounts where signup_date <= date '2025-12-17'
),
stages as (
    select 0 as stage_order, 'Website visitors' as stage, sum(visitors) as accounts
    from marts.fct_marketing_daily where date <= date '2025-12-17'
    union all select 1, 'Signed up',                    count(*)                                   from mature
    union all select 2, 'Onboarded',                    count(*) filter (where is_onboarded)       from mature
    union all select 3, 'Created project',              count(*) filter (where has_created_project) from mature
    union all select 4, 'Activated (invited teammate)', count(*) filter (where is_activated)       from mature
    union all select 5, 'Became paying (any path)',     count(*) filter (where is_paying_customer) from mature   -- incl. payers who skipped activation
)
select
    stage_order,
    stage,
    accounts,
    lag(accounts) over (order by stage_order) - accounts                                   as dropped_from_previous,
    round(100.0 * accounts / lag(accounts) over (order by stage_order), 2)                 as step_conversion_pct,
    round(100.0 - 100.0 * accounts / lag(accounts) over (order by stage_order), 2)         as step_drop_off_pct,
    case when stage_order >= 1 then round(100.0 * accounts / max(case when stage_order = 1 then accounts end) over (), 2) end as pct_of_signups,
    round(100.0 * accounts / max(case when stage_order = 0 then accounts end) over (), 3)  as pct_of_visitors
from stages
order by stage_order;
